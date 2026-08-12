"""猜词三环节管道（共享）：拆分 → 配对 → 检定。真实对战（battle.py）与试验场（test_battle.py）共用。

以 battle.py 最新异步版 submit_guess 的三环节编排为唯一基准：可靠性层调用（ainvoke_with_reliability）、
并发 gather、trace_context、MAX_PAIRS 截断、FAIL_GUESS_TEXT 文案全部照搬，只在其上叠加试验场
所需的累计明细字段（rounds/verifies/cracked_round/additions）。与 deduction.py 同构：本模块只编排
「一轮猜词判定怎么跑」，不碰战斗记录生命周期与结算规则。节点构造器由调用方注入（battle 层别名 /
试验场直接 import），测试打桩同一位置。产出卡片含全部明细；真实对战落库时自行裁剪为 {matched, cracked}。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from langchain_core.runnables import Runnable

from app.services.nodes.guess_matcher import (
    GUESS_PAIR_TEMPLATE,
    GUESS_VERIFY_TEMPLATE,
    PairMatch,
    build_guess_pair_llm,
    build_guess_verify_llm,
    split_atomic_guesses,
)
from app.services.reliability import ainvoke_with_reliability

# 猜奇术规则：有限次数内逐次道出猜测，匹配片段上卡、逐卡完整覆盖核心机制/效果/限制即看破（揭示真实奇术），全破逆转
GUESS_ATTEMPTS_MAX = 5
MAX_PAIRS = 24  # 单轮配对并发上限（原子猜测 × 未看破奇术），超出截断，未覆盖条目按不匹配处理

# 全链路自动重试耗尽后的面向用户解释文本（说书语系）
FAIL_GUESS_TEXT = "奇术判定失联，请稍后重试猜奇术。"


async def run_guess_round(
    *,
    text: str,
    abilities: list[dict],
    cards: list[dict],
    round_no: int,
    trace_context: dict | None = None,
    build_pair: Callable[[], Runnable] = build_guess_pair_llm,
    build_verify: Callable[[], Runnable] = build_guess_verify_llm,
) -> list[dict]:
    """对一次猜测跑「拆分→配对→检定」三环节，就地更新传入的 cards 并返回同一列表。

    结构照搬 battle.py 最新异步版 submit_guess（可靠性层调用 / 并发 gather / MAX_PAIRS 截断 /
    trace_context / 空拆分抛 ValueError(FAIL_GUESS_TEXT)），叠加试验场所需明细：每张卡记录本轮
    rounds（原子条目 + 逐对 pairs），本轮有新增片段的卡记录 verifies 并置 cracked/cracked_round。
    真实对战落库时自行裁剪为 {matched, cracked}。
    """
    # 环节一：拆分。用户以换行分隔对各奇术的猜测，后端按换行切原子条目（取消 LLM 拆分）。
    items = split_atomic_guesses(text)
    if not items:
        raise ValueError(FAIL_GUESS_TEXT)  # 无有效原子条目 → 可重试文案，不消耗次数

    # 环节二：配对匹配。原子猜测 × 未看破奇术全组合，一次只拿一对进上下文、并发调用。
    pairs = [
        (ai, ci)
        for ai in range(len(items))
        for ci, card in enumerate(cards)
        if not card["cracked"]
    ][:MAX_PAIRS]

    async def _match_pair(ai: int, ci: int) -> tuple[int, int, PairMatch | None]:
        try:
            m = await ainvoke_with_reliability(
                build_pair(),
                GUESS_PAIR_TEMPLATE.format_messages(
                    item_text=items[ai],
                    ability=f"{abilities[ci]['name']}：{abilities[ci]['effect']}",
                    existing="\n".join(f"- {s}" for s in cards[ci]["matched"]) or "（暂无）",
                ),
                operation="guess_pair",
                trace_context=trace_context,
            )
            return ai, ci, m
        except Exception:  # noqa: BLE001 - 单对失败静默跳过，不影响其它对
            return ai, ci, None

    # 本轮每卡新增的片段（供累计描述表 + 下轮增量去重）
    additions: dict[int, list[dict]] = {ci: [] for ci in range(len(cards))}
    touched: set[int] = set()
    for ai, ci, m in await asyncio.gather(*(_match_pair(ai, ci) for ai, ci in pairs)):
        card = cards[ci]
        if m is None or not m.snippet:
            continue
        card["matched"] = list(card["matched"]) + [m.snippet]
        additions[ci].append({"item": items[ai], "snippet": m.snippet})
        touched.add(ci)

    # 每张卡都记录本轮（原子条目），供累计描述表分轮；未命中的卡该轮 pairs 为空
    for ci, card in enumerate(cards):
        card["rounds"] = list(card.get("rounds") or []) + [
            {"round": round_no, "items": items, "pairs": additions[ci]}
        ]

    # 环节三：检定。取消百分制，对本轮有新增片段的卡并发做布尔检定——核心机制/效果/限制全覆盖即看破。
    async def _verify_card(ci: int) -> tuple[int, dict]:
        try:
            v = await ainvoke_with_reliability(
                build_verify(),
                GUESS_VERIFY_TEMPLATE.format_messages(
                    matched="\n".join(f"- {s}" for s in cards[ci]["matched"]),
                    ability=f"{abilities[ci]['name']}：{abilities[ci]['effect']}",
                ),
                operation="guess_verify",
                trace_context=trace_context,
            )
            return ci, {"guessed": v.guessed, "reason": v.reason}
        except Exception:  # noqa: BLE001 - 单卡检定失败视为未猜出，不降级
            return ci, {"guessed": False, "reason": "检定调用失联，视为未看破"}

    for ci, verdict in await asyncio.gather(*(_verify_card(ci) for ci in touched)):
        cards[ci]["verifies"] = list(cards[ci].get("verifies") or []) + [
            {"round": round_no, "guessed": verdict["guessed"], "reason": verdict["reason"]}
        ]
        if verdict["guessed"]:
            cards[ci]["cracked"] = True
            cards[ci]["cracked_round"] = round_no

    return cards
