"""推演链路模块：把 LLM 节点（推演者 / 转写者 / 转写质检员）编排为一场对战的完整推演。

输入：对战双方奇人名字 + 异能 + 打法；异闻师（用户）名字只用于服务端日志，**不进任何 LLM
上下文**。输出：上帝视角全文、A/B 视角全文、胜负判定。与 battle.py 解耦——battle 只管对战
的创建、结算与猜底牌，这里只负责"把一场仗打出来"。推演中一律使用奇人名字（结尾模板 /
胜负解析 / 视角转写身份 / 校验视角）。

推演方式：一次性推演。推演 LLM 以开场白开头、以三选一固定结尾句收尾，一口气输出完整
对战（不再分轮、不再由判定 LLM 裁断）；胜负从结尾句解析（解析失败保守判和局）。随后对
完整上帝叙述做一次并发转写（A/B 各一个视角分支）：转写 LLM 扮演该视角奇人，以第一人称
向自己的异闻师讲述这场战斗的经历，结果由角色自然交代（不再注入系统固定首尾）。转写后经
**校验节点**逐侧定稿：校验 → 合格直接用；不合格 → 修复一次再校验；仍不合格或修复失败 →
退回原文稿件（原文再差也是第一人称，上帝视角第三人称不作兜底；仅转写完全失败才降级上帝正文）。

SSE 进度事件沿推演链路实时外发：dueling（上帝视角生成中，前端「正在对决中」）→ recounting
（上帝视角完成、奇人回归、开始转写，前端「胜负已分，xxx回到了你的异闻录中」）→ segment
（转写正文）。

所有 LLM 调用统一走可靠性层（超时 + 指数退避重试，见 services/reliability.py）：
- 推演失败（重试耗尽）向上抛 ChainFailure，由 battle 层标记 failed 并输出解释文本；
- 转写失败降级为上帝段兜底；校验不可用（重试耗尽）保留原文、不冤枉合格叙述。
"""

from __future__ import annotations

import asyncio
import random
import re
from collections.abc import Callable
from dataclasses import dataclass

from langchain_core.runnables import Runnable

from app.core.logger import get_logger
from app.models.ability import Ability
from app.models.user import User
from app.services.nodes.deducer import OPENINGS, build_deduce_chain, build_endings
from app.services.nodes.discusser import build_discuss_llm
from app.services.nodes.transcribe_validator import build_repair_chain, build_validate_chain
from app.services.nodes.transcriber import build_transcribe_chain
from app.services.reliability import ainvoke_with_reliability

logger = get_logger("deduction")


@dataclass
class DeductionResult:
    """一场推演的产出：上帝视角全文、A/B 视角全文、胜负判定、战前讨论报告。"""

    god: str
    narration_a: str
    narration_b: str
    winner_side: str  # "A" | "B" | "draw"
    winner_id: int | None
    result: str  # 胜者奇人名字或"和局"
    discuss_report: str = ""  # 讨论节点产出（可能为空：外部未传且讨论失败降级）


def _render_ability(a: Ability) -> str:
    """单条异能渲染为推演输入文本（有值才附补充说明/理解/战术各行）。"""
    lines = [f"- {a.name}：{a.effect}"]
    if a.detail:
        lines.append(f"  补充说明：{a.detail}")
    if a.understanding:
        lines.append(f"  理解：{a.understanding}")
    if a.tactic:
        lines.append(f"  我会怎么用：{a.tactic}")
    return "\n".join(lines)


def _combat_info(
    fighter_a: str,
    fighter_b: str,
    abilities_a: list[Ability],
    abilities_b: list[Ability],
    tactic_a: str,
    tactic_b: str,
    style_a: str = "",
    style_b: str = "",
) -> str:
    """双方信息组装为模板用的完整文本（只含奇人名字，异闻师名字不进 LLM 上下文）。

    风格/战术为「解读清洗后的版本」（见 loadout_interpretation），空则（未设定）。
    """
    abs_a = "\n".join(_render_ability(a) for a in abilities_a)
    abs_b = "\n".join(_render_ability(a) for a in abilities_b)
    return (
        f"【发起方奇人：{fighter_a}】\n"
        f"战斗风格：{style_a or '（未设定）'}\n"
        f"{fighter_a}持有异能：\n{abs_a}\n"
        f"{fighter_a}的战术意图：\n{tactic_a or '（未设定）'}\n\n"
        f"【对手奇人：{fighter_b}】\n"
        f"战斗风格：{style_b or '（未设定）'}\n"
        f"{fighter_b}持有异能：\n{abs_b}\n"
        f"{fighter_b}的战术意图：\n{tactic_b or '（未设定）'}"
    )


def _pick_opening(opening: str | None = None) -> tuple[str, str]:
    """选定开场白与其地图名；未显式传入则随机。

    显式传入的文本需能在 OPENINGS 中反查到地图名（结尾/首尾要与开场同一张地图）；
    匹配不到则兜底通用说法。
    """
    if opening:
        for text, map_name in OPENINGS:
            if text == opening:
                return opening, map_name
        return opening, "这片战场"
    return random.choice(OPENINGS)


def _parse_winner(out: str, endings: dict[str, str], name_a: str, name_b: str) -> str | None:
    """从推演输出末尾解析胜负。

    优先三句结尾的尾部精确匹配（.strip() 后 endswith），失败则对末 200 字符正则
    「胜者：X」/「平局」并与用户名比对。返回 "A"/"B"/"draw"，解析不到返回 None
    （调用方保守判和局）。
    """
    tail = out.strip()
    for side in ("A", "B", "draw"):
        if tail.endswith(endings[side]):
            return side
    near = tail[-200:]
    if "平局" in near:
        return "draw"
    m = re.search(r"胜者[:：]\s*([^\s，。！？、]+)", near)
    if not m:
        return None
    name = m.group(1).strip()
    if name == name_a:
        return "A"
    if name == name_b:
        return "B"
    return None


async def _safe_validate(
    build_validate: Callable[[], Runnable],
    info: str,
    god: str,
    viewer_name: str,
    narration: str,
    trace_context: dict | None = None,
) -> object | None:
    """调用单侧校验链；可靠性层重试耗尽（或结构化输出失败）→ None，视为"无法判定"。"""
    try:
        return await ainvoke_with_reliability(
            build_validate(),
            {"info": info, "god": god, "viewer_name": viewer_name, "narration": narration},
            operation="validate",
            trace_context=trace_context,
        )
    except Exception:  # noqa: BLE001 - 可靠性层已记异常日志；无法判定时保留原文，不冤枉合格叙述
        logger.warning("validate_unavailable viewer=%s", viewer_name)
        return None


async def _safe_repair(
    build_repair: Callable[[], Runnable],
    info: str,
    god: str,
    viewer_name: str,
    narration: str,
    violations: list[str],
    trace_context: dict | None = None,
) -> str | None:
    """调用单侧修复链按质检违规点重写；失败 → None（调用方兜底上帝正文）。"""
    try:
        return await ainvoke_with_reliability(
            build_repair(),
            {
                "info": info,
                "god": god,
                "viewer_name": viewer_name,
                "narration": narration,
                "violations": "\n".join(f"- {v}" for v in violations),
            },
            operation="repair",
            trace_context=trace_context,
        )
    except Exception:  # noqa: BLE001 - 可靠性层已记异常日志；兜底上帝正文
        logger.warning("repair_unavailable viewer=%s", viewer_name)
        return None


async def _settle_side(
    *,
    build_validate: Callable[[], Runnable],
    build_repair: Callable[[], Runnable],
    info: str,
    god: str,
    viewer_name: str,
    narration: str,
    trace_context: dict | None = None,
) -> str:
    """单侧视角定稿：校验 → 合格直接用；不合格 → 修复一次再校验；仍不合格/修复失败 → 原文稿件兜底。

    校验不可用（重试耗尽）视为"无判定"、保留原文。校验明确判不合格时修复一次；修复仍无法
    通过校验则退回原文稿件——原文再差也是该视角奇人的第一人称讲述，上帝视角为全知第三人称、
    读者体验断裂更严重，不作兜底。
    """
    if narration == god:
        return narration  # 转写失败已降级为上帝正文，无可修的原文稿件，原样返回
    verdict = await _safe_validate(build_validate, info, god, viewer_name, narration, trace_context=trace_context)
    if verdict is None:
        return narration  # 无法判定：保留原文
    if verdict.passes:
        return narration
    repaired = await _safe_repair(
        build_repair, info, god, viewer_name, narration, list(verdict.violations), trace_context=trace_context
    )
    if repaired is None or not repaired.strip():
        logger.warning("repair_unavailable viewer=%s -> keep original", viewer_name)
        return narration
    re_verdict = await _safe_validate(build_validate, info, god, viewer_name, repaired, trace_context=trace_context)
    if re_verdict is not None and re_verdict.passes:
        return repaired
    logger.warning("narration_failed_validation viewer=%s -> keep original", viewer_name)
    return narration


async def run_deduction(
    *,
    stream,
    user_a: User,
    user_b: User,
    fighter_a: str,
    fighter_b: str,
    abilities_a: list[Ability],
    abilities_b: list[Ability],
    tactic_a: str,
    tactic_b: str,
    style_a: str = "",
    style_b: str = "",
    build_discuss: Callable[[], Runnable] = build_discuss_llm,
    build_deduce: Callable[[], Runnable] = build_deduce_chain,
    build_transcribe: Callable[[], Runnable] = build_transcribe_chain,
    build_validate: Callable[[], Runnable] = build_validate_chain,
    build_repair: Callable[[], Runnable] = build_repair_chain,
    opening: str | None = None,
    discuss_report: str = "",
    trace_context: dict | None = None,
) -> DeductionResult:
    """一次性推演一场对战并转写双视角，转写经校验节点定稿。

    流程：选开场（随机或显式）→ 建三选一结尾模板（奇人名字）→ **讨论节点先对双方异能与战术
    做分析报告**（能力理论模拟 + 实战拉片式推演，失败降级跳过，推演照旧）→ 推演 LLM 以
    「双方信息 + 讨论报告」为输入一口气输出完整对战（含结尾句）→ 解析胜负 → 对完整上帝叙述
    做一次并发转写（转写 LLM 扮演该视角奇人、第一人称向自己异闻师讲述经历，结果由角色自然
    交代）→ 校验节点逐侧定稿（校验 → 修复一次 → 再校验 → 原文稿件兜底）→ 发布单条 SSE
    segment。推演 LLM 重试耗尽抛 ChainFailure 向上，由调用方标记 failed；讨论/转写失败降级
    不废场。

    推演过程沿 SSE 实时推送进度：dueling（上帝视角生成中）→ recounting（上帝视角完成、
    奇人回归、开始转写）→ segment（转写正文）。讨论在后台进行，不占用 SSE 事件面。LLM 上下文
    只含奇人名字，异闻师名字仅服务端日志。
    """
    opening, map_name = _pick_opening(opening)
    info = _combat_info(
        fighter_a, fighter_b, abilities_a, abilities_b, tactic_a, tactic_b, style_a, style_b,
    )
    endings = build_endings(map_name, fighter_a, fighter_b)

    deduce_llm = build_deduce()
    transcribe_chain = build_transcribe()

    # 讨论节点：推演前先产出双方异能/战术分析报告（能力理论模拟 + 实战拉片），作为推演输入。
    # 报告由外部传入（discuss_report）时直接复用；否则调讨论 LLM 生成。失败降级为仅用 info
    # 推演（讨论是增强、不是必需），绝不因讨论失败废掉整场对决。
    if not discuss_report:
        try:
            discuss_report = str(
                await ainvoke_with_reliability(
                    build_discuss(),
                    {"info": info},
                    operation="discuss",
                    trace_context=trace_context,
                )
            )
        except Exception:  # noqa: BLE001 - 讨论失败降级：推演照旧用双方信息
            logger.warning("discuss_unavailable -> fallback to direct deduce")
            discuss_report = ""

    logger.info(
        "battle_start a=%s(%s) b=%s(%s) abilities=%d/%d",
        fighter_a,
        user_a.username,
        fighter_b,
        user_b.username,
        len(abilities_a),
        len(abilities_b),
    )
    # SSE 进度：上帝视角生成中（前端「正在对决中」）
    await stream.publish({"type": "stage", "stage": "dueling"})
    seg = await ainvoke_with_reliability(
        deduce_llm,
        {
            "info": info,
            "discuss_report": discuss_report,
            "opening": opening,
            "ending_a": endings["A"],
            "ending_b": endings["B"],
            "ending_draw": endings["draw"],
        },
        operation="deduce",
        trace_context=trace_context,
    )
    # 上帝视角 = 模型完整输出：开场白已由模型按模板输出，服务端不再前置（避免开场白重复）。
    # 模型偶发未输出开场白时，上帝视角以模型输出为准（不展示给玩家，仅存储/试验场可见）。
    god = seg.strip()

    # 胜负从结尾句解析；解析不到（LLM 未按模板收尾）保守判和局
    winner_side = _parse_winner(seg, endings, fighter_a, fighter_b) or "draw"
    if winner_side == "A":
        winner_id, result = user_a.id, fighter_a
    elif winner_side == "B":
        winner_id, result = user_b.id, fighter_b
    else:
        winner_id, result = None, "和局"

    # SSE 进度：上帝视角完成，奇人回归、开始转写视角讲述（前端「胜负已分，xxx回到了你的异闻录中」）
    await stream.publish({"type": "stage", "stage": "recounting", "fighter_a": fighter_a, "fighter_b": fighter_b})
    logger.info("god_done winner=%s god_len=%d", winner_side, len(god))
    try:
        tr = await ainvoke_with_reliability(
            transcribe_chain,
            {
                "info": info,
                "god": god,
                "viewer_name_a": fighter_a,
                "viewer_name_b": fighter_b,
            },
            operation="transcribe",
            trace_context=trace_context,
        )
    except Exception:  # noqa: BLE001 - 转写失败（已重试耗尽）：两侧降级为上帝正文兜底
        tr = None
    raw_a = (tr or {}).get("narration_a") or god
    raw_b = (tr or {}).get("narration_b") or god
    # 校验节点逐侧定稿（A/B 并发）：校验 → 修复一次 → 再校验 → 原文稿件兜底
    nar_a, nar_b = await asyncio.gather(
        _settle_side(
            build_validate=build_validate,
            build_repair=build_repair,
            info=info,
            god=god,
            viewer_name=fighter_a,
            narration=raw_a,
            trace_context=trace_context,
        ),
        _settle_side(
            build_validate=build_validate,
            build_repair=build_repair,
            info=info,
            god=god,
            viewer_name=fighter_b,
            narration=raw_b,
            trace_context=trace_context,
        ),
    )

    await stream.publish({"type": "segment", "round": 0, "narration_a": nar_a, "narration_b": nar_b})
    logger.info("battle_done winner=%s", winner_side)
    return DeductionResult(
        god=god,
        narration_a=nar_a,
        narration_b=nar_b,
        winner_side=winner_side,
        winner_id=winner_id,
        result=result,
        discuss_report=discuss_report,
    )
