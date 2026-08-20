"""推演链路模块：把 LLM 节点（对比者 / 推演者 / 转写者 / 转写质检员）编排为一场对战的完整推演。

输入：对战双方奇人名字 + 异能 + 打法；异闻师（用户）名字只用于服务端日志，**不进任何 LLM
上下文**。输出：上帝视角全文、A/B 视角全文、胜负判定。与 battle.py 解耦——battle 只管对战
的创建、结算与猜底牌，这里只负责"把一场仗打出来"。推演中一律使用奇人名字（结尾模板 /
胜负解析 / 视角转写身份 / 校验视角）。

推演方式：一次性推演。推演 LLM 以开场白开头、以三选一固定结尾句收尾，一口气输出完整
对战（不再分轮、不再由判定 LLM 裁断）；胜负从结尾句解析（解析失败保守判和局）。推演前由
**能力对比节点**把双方各至多四门奇术全量跨边配对（最多 16 对），逐对并发判断冲突、依三相
共鸣理论分判高下，汇总为对比报告作为推演输入（暂时替代讨论节点）。随后对完整上帝叙述做
**逐字流式**双视角转写（A/B 各一个视角分支并发）：转写 LLM 扮演该视角奇人，以第一人称向
自己的异闻师讲述这场战斗的经历，结果由角色自然交代。流式输出经**流内审查**遮蔽对家异能名
逐字上屏；全文流完后经**校验节点**逐侧定稿：校验 → 合格直接用；不合格 → 修复一次再校验；
仍不合格或修复失败 → 退回原文稿件（原文再差也是第一人称，上帝视角第三人称不作兜底；仅
转写完全失败才降级上帝正文）。

SSE 进度事件沿推演链路实时外发：compare（奇术对比中）→ dueling（上帝视角生成中，前端
「正在对决中」，**已看破场景逐字流式上帝正文**）→ recounting（上帝视角完成、奇人回归、开始
转写，前端「胜负已分，xxx回到了你的异闻录中」）→ narration_chunk（转写逐字流）→ segment
（定稿正文）。

所有 LLM 调用统一走可靠性层（超时 + 指数退避重试，见 services/reliability.py）：
- 推演失败（重试耗尽）向上抛 ChainFailure，由 battle 层标记 failed 并输出解释文本；
- 转写失败降级为上帝段兜底；校验不可用（重试耗尽）保留原文、不冤枉合格叙述。
"""

from __future__ import annotations

import asyncio
import random
import re
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

from langchain_core.runnables import Runnable

from app.core.logger import get_logger
from app.models.ability import Ability
from app.models.loadout import MAX_LOADOUT_ABILITIES
from app.models.user import User
from app.services.nodes.ability.pair_judge import PairVerdict, build_pair_judge_chain, render_pair_report
from app.services.nodes.battle.deducer import OPENINGS, build_deduce_chain, build_endings
from app.services.nodes.battle.leak_filter import build_denylist, mask_stream_chunks
from app.services.nodes.battle.transcribe_validator import build_repair_chain, build_validate_chain
from app.services.nodes.battle.transcriber import build_transcribe_side_chain
from app.services.llm.reliability import ainvoke_with_reliability, astream_with_reliability

logger = get_logger("deduction")


@dataclass
class DeductionResult:
    """一场推演的产出：上帝视角全文、A/B 视角全文、胜负判定、战前分析报告。"""

    god: str
    narration_a: str
    narration_b: str
    winner_side: str  # "A" | "B" | "draw"
    winner_id: int | None
    result: str  # 胜者奇人名字或"和局"
    discuss_report: str = ""  # 能力对比报告（可能为空：外部未传且对比失败降级）


def _render_ability(a: Ability) -> str:
    """单条异能渲染为推演输入文本（有值才附详细解释/因果槽位）。"""
    lines = [f"- {a.name}：{a.effect}"]
    if a.detail:
        lines.append(f"  详细解释：{a.detail}")
    if a.understanding:
        lines.append(f"  因果槽位：{a.understanding}")
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
    build_validate: Callable[..., Runnable],
    info: str,
    god: str,
    viewer_name: str,
    narration: str,
    llm_config: dict | None = None,
    trace_context: dict | None = None,
) -> object | None:
    """调用单侧校验链；可靠性层重试耗尽（或结构化输出失败）→ None，视为"无法判定"。"""
    try:
        return await ainvoke_with_reliability(
            build_validate(llm_config=llm_config),
            {"info": info, "god": god, "viewer_name": viewer_name, "narration": narration},
            operation="validate",
            trace_context=trace_context,
        )
    except Exception:  # noqa: BLE001 - 可靠性层已记异常日志；无法判定时保留原文，不冤枉合格叙述
        logger.warning("validate_unavailable viewer=%s", viewer_name)
        return None


async def _safe_repair(
    build_repair: Callable[..., Runnable],
    info: str,
    god: str,
    viewer_name: str,
    narration: str,
    violations: list[str],
    llm_config: dict | None = None,
    trace_context: dict | None = None,
) -> str | None:
    """调用单侧修复链按质检违规点重写；失败 → None（调用方兜底上帝正文）。"""
    try:
        return await ainvoke_with_reliability(
            build_repair(llm_config=llm_config),
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
    build_validate: Callable[..., Runnable],
    build_repair: Callable[..., Runnable],
    info: str,
    god: str,
    viewer_name: str,
    narration: str,
    llm_config: dict | None = None,
    trace_context: dict | None = None,
) -> str:
    """单侧视角定稿：校验 → 合格直接用；不合格 → 修复一次再校验；仍不合格/修复失败 → 原文稿件兜底。

    校验不可用（重试耗尽）视为"无判定"、保留原文。校验明确判不合格时修复一次；修复仍无法
    通过校验则退回原文稿件——原文再差也是该视角奇人的第一人称讲述，上帝视角为全知第三人称、
    读者体验断裂更严重，不作兜底。
    """
    if narration == god:
        return narration  # 转写失败已降级为上帝正文，无可修的原文稿件，原样返回
    verdict = await _safe_validate(
        build_validate, info, god, viewer_name, narration, llm_config=llm_config, trace_context=trace_context
    )
    if verdict is None:
        return narration  # 无法判定：保留原文
    if verdict.passes:
        return narration
    repaired = await _safe_repair(
        build_repair, info, god, viewer_name, narration, list(verdict.violations),
        llm_config=llm_config, trace_context=trace_context,
    )
    if repaired is None or not repaired.strip():
        logger.warning("repair_unavailable viewer=%s -> keep original", viewer_name)
        return narration
    re_verdict = await _safe_validate(
        build_validate, info, god, viewer_name, repaired, llm_config=llm_config, trace_context=trace_context
    )
    if re_verdict is not None and re_verdict.passes:
        return repaired
    logger.warning("narration_failed_validation viewer=%s -> keep original", viewer_name)
    return narration


async def _run_pair_analysis(
    abilities_a: list[Ability],
    abilities_b: list[Ability],
    build_pair_judge: Callable[..., Runnable],
    llm_config: dict | None = None,
    trace_context: dict | None = None,
) -> str:
    """能力对比节点：双方各至多四门奇术全量跨边配对，天然最多 16 对。
    每对只传两门奇术完整信息，并发判断冲突与依三相理论分出的占优奇术，汇总为对比报告。

    专用 asyncio.Semaphore(4) 限流（对比对本身很多，全局 LLM 信号量管在途总量、这里管这一节点的
    并发，避免一次性打爆服务商配额）。单对失败跳过；全部失败返回空报告，推演照旧（对比是增强、
    不是必需，同讨论节点降级语义）。
    """
    pairs = [
        (a, b) for a in abilities_a[:MAX_LOADOUT_ABILITIES] for b in abilities_b[:MAX_LOADOUT_ABILITIES]
    ]
    if not pairs:
        return ""
    judge = build_pair_judge(llm_config=llm_config)
    sem = asyncio.Semaphore(4)

    async def _judge(a: Ability, b: Ability) -> PairVerdict | None:
        try:
            async with sem:
                return await ainvoke_with_reliability(
                    judge,
                    {"ability_a": _render_ability(a), "ability_b": _render_ability(b)},
                    operation="ability_pair",
                    trace_context=trace_context,
                )
        except Exception:  # noqa: BLE001 - 单对失败跳过，不因对比废掉整场
            return None

    verdicts = await asyncio.gather(*(_judge(a, b) for a, b in pairs))
    verdicts = [v for v in verdicts if v is not None]
    if not verdicts:
        logger.warning("pair_analysis_unavailable -> fallback to direct deduce")
        return ""
    return render_pair_report(verdicts)


async def _stream_transcribe_side(
    *,
    stream,
    side: str,
    info: str,
    god: str,
    viewer_name: str,
    opponent_abilities: list[Ability],
    transcribe_side_chain: Runnable,
    build_validate: Callable[..., Runnable],
    build_repair: Callable[..., Runnable],
    llm_config: dict | None = None,
    trace_context: dict | None = None,
) -> str:
    """单侧转写逐字流：转写 LLM 流式讲述该视角经历，流内经审查遮蔽对家异能名逐字上屏
    （narration_chunk，replay=False），全文流完后按**未遮蔽原文**进校验节点定稿。

    流失败（重试耗尽）降级为上帝正文兜底（同现状）。发布的 narration_chunk 用遮蔽文本，落库/
    定稿用原文——遮蔽只影响上屏瞬间，事后校验修复的是权威正文。
    """
    raw_parts: list[str] = []

    async def _collect_raw() -> AsyncIterator[str]:
        async for chunk in astream_with_reliability(
            transcribe_side_chain,
            {"info": info, "god": god, "viewer_name": viewer_name},
            operation=f"transcribe_{side}",
            trace_context=trace_context,
        ):
            raw_parts.append(chunk)
            yield chunk

    try:
        async for masked in mask_stream_chunks(_collect_raw(), build_denylist(opponent_abilities)):
            await stream.publish({"type": "narration_chunk", "side": side, "text": masked}, replay=False)
    except Exception:  # noqa: BLE001 - 转写失败（已重试耗尽）：降级为上帝正文兜底
        logger.warning("transcribe_unavailable side=%s -> fallback to god", side)
        return god
    raw = "".join(raw_parts).strip() or god
    return await _settle_side(
        build_validate=build_validate,
        build_repair=build_repair,
        info=info,
        god=god,
        viewer_name=viewer_name,
        narration=raw,
        llm_config=llm_config,
        trace_context=trace_context,
    )


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
    build_pair_judge: Callable[..., Runnable] = build_pair_judge_chain,
    build_deduce: Callable[..., Runnable] = build_deduce_chain,
    build_transcribe_side: Callable[..., Runnable] = build_transcribe_side_chain,
    build_validate: Callable[..., Runnable] = build_validate_chain,
    build_repair: Callable[..., Runnable] = build_repair_chain,
    opening: str | None = None,
    discuss_report: str = "",
    llm_config: dict | None = None,
    trace_context: dict | None = None,
) -> DeductionResult:
    """一次性推演一场对战并逐字流式转写双视角，转写经校验节点定稿。

    流程：选开场（随机或显式）→ 建三选一结尾模板（奇人名字）→ **能力对比节点先把双方奇术
    两两配对做对比报告**（冲突判定 + 三相共鸣理论分判高下，失败降级跳过，推演照旧）→ 推演 LLM
    以「双方信息 + 对比报告」为输入流式输出完整对战（含结尾句，上帝正文逐字流给已看破者）→
    解析胜负 → 对完整上帝叙述做逐字流式双视角转写（转写 LLM 扮演该视角奇人、第一人称向自己
    异闻师讲述经历，结果由角色自然交代；流内经审查遮蔽对家异能名逐字上屏）→ 校验节点逐侧
    定稿（校验 → 修复一次 → 再校验 → 原文稿件兜底）→ 发布单条 SSE segment。推演 LLM 重试耗尽
    抛 ChainFailure 向上，由调用方标记 failed；对比/转写失败降级不废场。

    推演过程沿 SSE 实时推送进度：compare（奇术对比中）→ dueling（上帝视角生成中，已看破者
    收 god_chunk 逐字流）→ recounting（上帝视角完成、奇人回归、开始转写）→ narration_chunk
    （转写逐字流）→ segment（定稿正文）。LLM 上下文只含奇人名字，异闻师名字仅服务端日志。
    """
    opening, map_name = _pick_opening(opening)
    info = _combat_info(
        fighter_a, fighter_b, abilities_a, abilities_b, tactic_a, tactic_b, style_a, style_b,
    )
    endings = build_endings(map_name, fighter_a, fighter_b)

    deduce_llm = build_deduce(llm_config=llm_config)
    transcribe_side_chain = build_transcribe_side(llm_config=llm_config)

    # 能力对比节点：推演前先把双方奇术两两配对（并发）判断冲突、依三相共鸣理论分判高下，
    # 汇总为对比报告作为推演输入。报告由外部传入（discuss_report）时直接复用；否则跑对比。
    # 失败降级为仅用 info 推演（对比是增强、不是必需），绝不因对比失败废掉整场对决。
    if not discuss_report:
        await stream.publish({"type": "stage", "stage": "compare"})
        discuss_report = await _run_pair_analysis(
            abilities_a, abilities_b, build_pair_judge,
            llm_config=llm_config, trace_context=trace_context,
        )

    logger.info(
        "battle_start a=%s(%s) b=%s(%s) abilities=%d/%d",
        fighter_a,
        user_a.username,
        fighter_b,
        user_b.username,
        len(abilities_a),
        len(abilities_b),
    )
    # SSE 进度：上帝视角生成中（前端「正在对决中」）；看破者逐字流收 god_chunk。
    await stream.publish({"type": "stage", "stage": "dueling"})
    seg_parts: list[str] = []
    async for chunk in astream_with_reliability(
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
        max_retries=2,
        trace_context=trace_context,
    ):
        seg_parts.append(chunk)
        await stream.publish({"type": "god_chunk", "text": chunk}, replay=False)
    # 上帝视角 = 模型完整输出：开场白已由模型按模板输出，服务端不再前置（避免开场白重复）。
    # 模型偶发未输出开场白时，上帝视角以模型输出为准（不展示给玩家，仅存储/试验场可见）。
    seg = "".join(seg_parts).strip()
    god = seg

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
    # 转写改为双单侧逐字流（A/B 并发）：转写 LLM 流式讲述该视角经历，流内经审查遮蔽对家异能名
    # 逐字上屏（narration_chunk），全文流完后逐侧进校验节点定稿（校验 → 修复一次 → 再校验 →
    # 原文稿件兜底）
    nar_a, nar_b = await asyncio.gather(
        _stream_transcribe_side(
            stream=stream,
            side="a",
            info=info,
            god=god,
            viewer_name=fighter_a,
            opponent_abilities=abilities_b,
            transcribe_side_chain=transcribe_side_chain,
            build_validate=build_validate,
            build_repair=build_repair,
            llm_config=llm_config,
            trace_context=trace_context,
        ),
        _stream_transcribe_side(
            stream=stream,
            side="b",
            info=info,
            god=god,
            viewer_name=fighter_b,
            opponent_abilities=abilities_a,
            transcribe_side_chain=transcribe_side_chain,
            build_validate=build_validate,
            build_repair=build_repair,
            llm_config=llm_config,
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
