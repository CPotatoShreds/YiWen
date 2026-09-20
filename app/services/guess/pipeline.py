"""猜词管道（共享）：拆分 → 原子配对 → 检定。小天下集挑战流程使用。

一次「配对」= 用户道出猜测 → 先切分为原子条目，再将每个原子与每门未看破奇术全组合并发请求；
每个请求只输出该原子的四态判定，结果按完成顺序回调落库；不改变任何看破状态。
一次「检定」= 玩家主动发起 → 对每张未看破卡并发调用，输入该卡自己的「猜测+点评」聊天记录
（按卡过滤，避免跨卡泄露点评），返回 cracked（看破）/ missing（还缺什么），就地更新 cards
并返回同一列表；不追加聊天记录。

与落库层同构：本模块只编排「一轮猜词判定怎么跑」，不碰挑战生命周期与结算落库（那些在
scenario_domain 路由层）。节点构造器由调用方注入，测试可在同一位置打桩。产出卡片含
全部明细；挑战记录落库时自行裁剪为 {cracked, missing, cracked_round}。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from langchain_core.runnables import Runnable

from app.services.llm.reliability import ainvoke_with_reliability
from app.services.nodes.guess.matcher import (
    GUESS_PAIR_TEMPLATE,
    GUESS_VERIFY_TEMPLATE,
    PairMatch,
    build_guess_pair_llm,
    build_guess_verify_llm,
    split_atomic_guesses,
)

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


async def run_guess_split(text: str) -> list[str]:
    """环节一：按旧版规则切分原子猜测，不调用模型。"""
    items = split_atomic_guesses(text)
    if not items:
        raise ValueError("猜测不能为空")
    return items


async def run_guess_matching(
    *,
    items: list[str],
    abilities: list[dict],
    cards: list[dict],
    trace_context: dict | None = None,
    build_pair: Callable[..., Runnable] = build_guess_pair_llm,
    llm_config: dict | None = None,
    on_match: Callable[[dict], Awaitable[None]] | None = None,
) -> list[dict]:
    """环节二：每个原子猜测与每门未看破奇术一一配对并发匹配。

    返回结果按完成顺序产出；每个结果都会先通过 ``on_match`` 回调，供调用方立即落库。
    单个配对失败不会影响其它配对，失败项也会以 ``status=failed`` 回调，保证前端能看到进度。
    """
    pending_cards = [ci for ci, card in enumerate(cards) if not card.get("cracked")]
    if not items or not pending_cards:
        return []

    async def _match(atom_index: int, card_index: int) -> dict:
        result = {
            "atom_index": atom_index + 1,
            "card_index": card_index + 1,
            "status": "matching",
            "text": items[atom_index],
            "verdict": "不能确定",
            "reason": "",
        }
        try:
            out: PairMatch = await ainvoke_with_reliability(
                build_pair(llm_config=llm_config),
                GUESS_PAIR_TEMPLATE.format_messages(
                    item_text=items[atom_index],
                    ability=_ability_txt(abilities[card_index]),
                    existing="\n".join(
                        f"- {value}"
                        for value in (cards[card_index].get("matched") or [])
                    )
                    or "（暂无）",
                ),
                operation="guess_pair",
                trace_context=trace_context,
            )
            text_value = str(getattr(out, "text", "") or "").strip()
            verdict = _normalize_verdict(getattr(out, "verdict", "不能确定"))
            result.update({"status": "complete", "text": text_value or items[atom_index], "verdict": verdict, "reason": str(getattr(out, "reason", "") or "")})
        except Exception:  # noqa: BLE001 - 单配对失败不阻塞其它配对
            result["status"] = "failed"
        return result

    pairs = [(ai, ci) for ai in range(len(items)) for ci in pending_cards]
    results: list[dict] = []
    tasks = [asyncio.create_task(_match(ai, ci)) for ai, ci in pairs]
    for task in asyncio.as_completed(tasks):
        match = await task
        results.append(match)
        if on_match is not None:
            await on_match(match)
    return results


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
    on_result: Callable[[int, dict], Awaitable[None]] | None = None,
) -> list[dict]:
    """对全部未看破卡并发检定（环节三），就地更新传入的 cards 并返回同一列表。

    每张卡：看破 → cracked/cracked_round 置位、missing 置空；未看破 → missing 记「还缺什么」。
    verifies 明细供挑战详情展示。单卡调用失败 → 不判看破、missing 置可重试文案，不降级整轮。
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

    for task in asyncio.as_completed([asyncio.create_task(_verify_card(ci)) for ci in pending]):
        ci, verdict = await task
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
        if on_result is not None:
            await on_result(ci, verdict)

    return cards
