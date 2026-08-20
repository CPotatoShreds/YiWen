"""猜词管道（共享）：逐门点评 → 检定。真实对战（battle.py）与试验场（test_battle.py）共用。

一次「点评」= 用户道出完整猜测 → 按实际需要猜的门数并发发起多个 LLM 请求，一个请求只对比用户
猜测与一门实际奇术，各自输出原子判定列表；落库为 guess_history 追加原文 + comments 追加
[{index, items}]（items 元素为 {text, verdict, reason}），attempts_used +1；不改变任何看破状态。
一次「检定」= 玩家主动发起 → 对每张未看破卡并发调用，输入该卡自己的「猜测+点评」聊天记录
（按卡过滤，避免跨卡泄露点评），返回 cracked（看破）/ missing（还缺什么），就地更新 cards
并返回同一列表；不追加聊天记录。

与 deduction.py 同构：本模块只编排「一轮猜词判定怎么跑」，不碰战斗记录生命周期与结算规则。
节点构造器由调用方注入（battle 层别名 / 试验场直接 import），测试打桩同一位置。产出卡片含
全部明细；真实对战落库时自行裁剪为 {cracked, missing, cracked_round}。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from langchain_core.runnables import Runnable

from app.services.nodes.guess.matcher import (
    GUESS_COMMENTARY_TEMPLATE,
    GUESS_VERIFY_TEMPLATE,
    build_guess_commentary_llm,
    build_guess_verify_llm,
)
from app.services.llm.reliability import ainvoke_with_reliability

# 猜奇术规则：有限次数内逐次道出猜测，点评/检定都计入次数。上限 200（形同不限）——真正的结束靠
# 「收手」：次数仅作兜底与试验场打桩（测试常 patch 为 1 模拟耗尽）。
GUESS_ATTEMPTS_MAX = 200

# 检定失败时该卡的降级文案（可重试语义，不判看破）
VERIFY_FAIL_MISSING = "检定失联，请稍后重试。"


def _normalize_verdict(value: object) -> str:
    """把旧存档的“半对”统一为当前正式判定“部分是”。"""
    return "部分是" if value == "半对" else str(value or "")


def _ability_txt(ability: dict) -> str:
    return f"{ability['name']}：{ability['effect']}"


def _round_atoms(round_comments, card_index: int | None = None) -> list[dict]:
    """取一个点评轮次中某张卡（card_index，None=全部）的原子项；兼容旧版 str 点评。

    round_comments = 该轮各组列表 [{index, items}, ...]；comments 存的就是轮列表。
    """
    if isinstance(round_comments, str):
        # 旧版单文本点评：无原子结构，作为一条「部分是」叙述兜底（历史数据只进检定作弱线索）
        return [{"text": round_comments, "verdict": "部分是"}]
    atoms: list[dict] = []
    for group in round_comments or []:
        if card_index is not None and group.get("index") != card_index:
            continue
        atoms.extend({**item, "verdict": _normalize_verdict(item.get("verdict"))} for item in group.get("items") or [])
    return atoms


def strip_commentary_reason(comments: list | None) -> list[list[dict]]:
    """逐门点评序列化前剥离内部 reason（绝不进前端）。

    comments = 轮列表，每轮 = 各组 [{index, items}]；输出同构，但每组 items 只留 {text, verdict}。
    兼容旧版 str 点评：整轮降为 index=0 的单组（无卡归属的旧数据）。
    """
    out: list[list[dict]] = []
    for round_comments in comments or []:
        if isinstance(round_comments, str):
            out.append([{"index": 0, "items": [{"text": round_comments, "verdict": "部分是"}]}])
            continue
        out.append(
            [
                {
                    "index": group.get("index"),
                    "items": [
                        {"text": it.get("text", ""), "verdict": _normalize_verdict(it.get("verdict"))}
                        for it in group.get("items") or []
                    ],
                }
                for group in round_comments or []
            ]
        )
    return out


def render_commentary_text(commentary: list[dict] | None) -> str:
    """把一个点评轮次（各组 [{index, items}]）的原子判定渲染成一行文本（榜同步落库，天然剥离 reason）。"""
    lines: list[str] = []
    for group in commentary or []:
        for it in group.get("items") or []:
            lines.append(f"「{it['text']}」{_normalize_verdict(it.get('verdict'))}")
    return "；".join(lines) if lines else ""


def _chat_log(history: list[str], comments: list, card_index: int | None = None) -> str:
    """把「猜测+点评」平行列表拼成逐轮聊天记录（检定输入）。

    comments 为轮列表，每轮 = 各组 [{index, items}]；card_index 指定时只渲染该张卡自己的点评
    原子项（跨卡过滤，避免检定一卡时泄露另一卡的点评）。兼容旧版 str 点评。
    """
    lines: list[str] = []
    for i, (text, round_comments) in enumerate(zip(history, comments), start=1):
        lines.append(f"第 {i} 轮")
        lines.append(f"猜测：{text}")
        items = _round_atoms(round_comments, card_index)
        if items:
            lines.append("点评：" + "；".join(f"「{it['text']}」{it['verdict']}" for it in items))
    return "\n".join(lines)


async def run_guess_commentary(
    *,
    text: str,
    abilities: list[dict],
    cards: list[dict],
    trace_context: dict | None = None,
    build_commentary: Callable[..., Runnable] = build_guess_commentary_llm,
    llm_config: dict | None = None,
) -> list[dict]:
    """对用户一次猜测逐门并发点评（环节一）。

    对每张未看破卡发起一个独立请求（一个请求只对比用户猜测与这一门奇术），各自输出原子判定列表。
    返回 [{index: 卡序号+1, items: [{text, verdict, reason}, ...]}]，index 与前端卡序号对齐。
    单卡失败 → 该卡 items=[]；全部卡失败 → 上抛异常（整轮点评作废，不计次数，由调用方处理）。
    """
    pending = [ci for ci, card in enumerate(cards) if not card.get("cracked")]
    if not pending:
        return []

    async def _commentary_card(ci: int) -> tuple[int, list[dict]]:
        out = await ainvoke_with_reliability(
            build_commentary(llm_config=llm_config),
            GUESS_COMMENTARY_TEMPLATE.format_messages(
                text=text,
                ability=_ability_txt(abilities[ci]),
            ),
            operation="guess_commentary",
            trace_context=trace_context,
        )
        return ci, [it.model_dump() for it in (out.items or [])]

    results = await asyncio.gather(*(_commentary_card(ci) for ci in pending), return_exceptions=True)

    groups: list[dict] = []
    failed = 0
    for ci, res in zip(pending, results):
        if isinstance(res, Exception):  # noqa: PERF203 - 单卡点评失败仅该卡缺，不整轮作废
            failed += 1
            groups.append({"index": ci + 1, "items": []})
        else:
            items = res[1] or [{"text": text, "verdict": "不能确定", "reason": "模型未返回原子判定。"}]
            groups.append({"index": ci + 1, "items": items})
    if failed == len(pending):
        raise RuntimeError("所有奇术点评均失败，点评作废。")
    return groups


async def run_guess_verification(
    *,
    history: list[str],
    comments: list,
    abilities: list[dict],
    cards: list[dict],
    round_no: int,
    trace_context: dict | None = None,
    build_verify: Callable[..., Runnable] = build_guess_verify_llm,
    llm_config: dict | None = None,
) -> list[dict]:
    """对全部未看破卡并发检定（环节三），就地更新传入的 cards 并返回同一列表。

    每张卡：看破 → cracked/cracked_round 置位、missing 置空；未看破 → missing 记「还缺什么」。
    verifies 明细供试验场展示。单卡调用失败 → 不判看破、missing 置可重试文案，不降级整轮。
    检定输入为该卡自己的聊天记录（_chat_log card_index 过滤），避免跨卡点评泄露。
    """
    pending = [ci for ci, card in enumerate(cards) if not card.get("cracked")]
    if not pending:
        return cards

    async def _verify_card(ci: int) -> tuple[int, dict]:
        try:
            v = await ainvoke_with_reliability(
                build_verify(llm_config=llm_config),
                GUESS_VERIFY_TEMPLATE.format_messages(
                    history=_chat_log(history, comments, card_index=ci + 1),
                    ability=_ability_txt(abilities[ci]),
                ),
                operation="guess_verify",
                trace_context=trace_context,
            )
            return ci, {"cracked": bool(v.cracked), "missing": (v.missing or "").strip()}
        except Exception:  # noqa: BLE001 - 单卡检定失败视为未看破，不降级整轮
            return ci, {"cracked": False, "missing": VERIFY_FAIL_MISSING}

    for ci, verdict in await asyncio.gather(*(_verify_card(ci) for ci in pending)):
        card = cards[ci]
        card["verifies"] = list(card.get("verifies") or []) + [
            {"round": round_no, "cracked": verdict["cracked"], "missing": verdict["missing"]}
        ]
        if verdict["cracked"]:
            card["cracked"] = True
            card["cracked_round"] = round_no
            card["missing"] = ""
        else:
            card["missing"] = verdict["missing"]

    return cards
