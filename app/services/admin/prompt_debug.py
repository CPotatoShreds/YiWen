"""提示词方案调试服务：管理员对某场真实行迹用不同提示词方案重跑推演段，产出独立调试记录。

- _scheme_builders(scheme)：按方案把 5 个推演段节点构建器包成「套好 system 覆盖」的闭包；
  覆盖为空 = 直接透传冻结默认构建器，生产路径逐字节不变。
- rerun_battle(db, battle_id, scheme_id)：建 pending 调试记录并后台重跑（对齐
  _resolve_battle 的「短连接读输入 → run_deduction 无连接 → 短连接写回」模式），接口即返。
- seed_prompt_schemes()：启动时 PromptScheme 空则写入种子方案（幂等）。

v1 边界：只重跑推演段（讨论/上帝/双视角）。usage/猜词三节点不在 run_deduction 内、模板在
调用方（battle.py/guess.py）构造，暂不支持方案覆盖——scheme 里对应列仅存储，
v2 用原场猜词历史重放时启用。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable

from langchain_core.runnables import Runnable
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.db.base import async_session_factory
from app.models.battle import Battle
from app.models.llm_profile import LlmProfile
from app.models.llm_trace import LlmTrace
from app.models.prompt_debug import PromptDebugRun, PromptScheme
from app.models.user import User
from app.services.battle.lifecycle import _resolve_loadout_inputs
from app.services.battle.deduction import run_deduction
from app.services.llm.client import profile_to_llm_config
from app.services.nodes.ability.pair_judge import build_pair_judge_chain
from app.services.nodes.battle.deducer import build_deduce_chain
from app.services.nodes.battle.transcribe_validator import build_repair_chain, build_validate_chain
from app.services.nodes.battle.transcriber import build_transcribe_side_chain

logger = get_logger("prompt_debug")

_background_tasks: set[asyncio.Task] = set()

# 推演段构建器按方案套覆盖：与 run_deduction 的 5 个 builder 参数一一对应。
# 值存「模块属性名」，_scheme_builders 运行时经 globals() 解析——测试可直接
# patch 本模块的节点构建器（对齐 battle.py 的 _build_* 打桩缝）。
# usage/guess_pair/guess_verify 不在内（模板在调用方构造，v1 仅存储）。
# "discuss" 槽现指向能力对比节点构建器（分析节点暂时替代讨论节点），字段名保持
# discuss_prompt 不迁移 schema，语义转为「对比/分析节点提示词」。
_DEDUCE_STAGES: dict[str, tuple[str, str]] = {
    "discuss": ("build_pair_judge_chain", "discuss_prompt"),
    "deduce": ("build_deduce_chain", "deduce_prompt"),
    "transcribe": ("build_transcribe_side_chain", "transcribe_prompt"),
    "validate": ("build_validate_chain", "validate_prompt"),
    "repair": ("build_repair_chain", "repair_prompt"),
}


def _stage_builder(stage: str) -> Callable[..., Runnable]:
    """当前模块命名空间里的节点构建器（动态解析，patch 模块属性即生效）。"""
    return globals()[_DEDUCE_STAGES[stage][0]]


def _scheme_builders(scheme: PromptScheme) -> dict[str, Callable[..., Runnable]]:
    """按方案构造 5 个推演段构建器：覆盖非空套 system_prompt，空覆盖直通冻结默认。"""
    builders: dict[str, Callable[..., Runnable]] = {}
    for stage, (_, attr) in _DEDUCE_STAGES.items():
        override = getattr(scheme, attr)
        if override:
            builder = _stage_builder(stage)
            builders[stage] = lambda *, _b=builder, _o=override, llm_config=None: _b(
                llm_config=llm_config, system_prompt=_o
            )
        else:
            builders[stage] = _stage_builder(stage)
    return builders


class _Collector:
    """本地 SSE 事件收集器：重跑不触碰全局事件总线（同 test_battle）。"""

    def __init__(self) -> None:
        self.events: list[dict] = []

    async def publish(self, event: dict, replay: bool = True) -> None:
        self.events.append(event)

    async def close(self) -> None:
        pass


async def _original_opening(db: AsyncSession, battle_id: int) -> str | None:
    """尽力取原场 deduce trace 的开场白（保持场景一致，让提示词成为唯一变量）；无记录则 None。"""
    result = await db.execute(
        select(LlmTrace)
        .where(
            LlmTrace.kind == "battle",
            LlmTrace.trace_id == str(battle_id),
            LlmTrace.operation == "deduce",
        )
        .order_by(LlmTrace.id.desc())
        .limit(5)
    )
    for t in result.scalars().all():
        opening = (t.request_json or {}).get("opening")
        if opening:
            return opening
    return None


async def rerun_battle(db: AsyncSession, battle_id: int, scheme_id: int) -> PromptDebugRun:
    """创建 pending 调试记录并后台启动重跑，返回该记录（接口立即返回 pending）。"""
    run = PromptDebugRun(battle_id=battle_id, scheme_id=scheme_id, status="pending")
    db.add(run)
    await db.commit()
    await db.refresh(run)

    task = asyncio.create_task(_do_rerun(run.id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return run


async def _do_rerun(run_id: int) -> None:
    """后台重跑一场：读输入（短连接）→ run_deduction（无连接）→ 写回调试记录。"""
    try:
        async with async_session_factory() as db:
            run = await db.get(PromptDebugRun, run_id)
            if run is None:
                return
            battle = await db.get(Battle, run.battle_id)
            if battle is None:
                run.status = "failed"
                run.error = "行迹不存在"
                await db.commit()
                return
            user_a = await db.get(User, battle.user_a_id)
            user_b = await db.get(User, battle.user_b_id)
            if user_a is None or user_b is None:
                run.status = "failed"
                run.error = "对决用户缺失"
                await db.commit()
                return
            inputs = await _resolve_loadout_inputs(db, battle, user_a, user_b)
            if inputs is None:
                run.status = "failed"
                run.error = "对决奇人缺失"
                await db.commit()
                return
            abilities_a, abilities_b, fighter_a, fighter_b, tactic_a, tactic_b, style_a, style_b = inputs
            # 推演 LLM 配置：发起方（user_a）的激活方案，未配回退服务器默认（同 _resolve_battle）
            profile = await db.get(LlmProfile, user_a.active_profile_id) if user_a.active_profile_id else None
            llm_config = profile_to_llm_config(profile)
            scheme = await db.get(PromptScheme, run.scheme_id)
            builders = (
                _scheme_builders(scheme)
                if scheme
                else {stage: _stage_builder(stage) for stage in _DEDUCE_STAGES}
            )
            opening = await _original_opening(db, battle.id)

        r = await run_deduction(
            stream=_Collector(),
            user_a=user_a,
            user_b=user_b,
            fighter_a=fighter_a,
            fighter_b=fighter_b,
            abilities_a=abilities_a,
            abilities_b=abilities_b,
            tactic_a=tactic_a,
            tactic_b=tactic_b,
            style_a=style_a,
            style_b=style_b,
            build_pair_judge=builders["discuss"],
            build_deduce=builders["deduce"],
            build_transcribe_side=builders["transcribe"],
            build_validate=builders["validate"],
            build_repair=builders["repair"],
            opening=opening,
            llm_config=llm_config,
            trace_context={"kind": "debug_rerun", "trace_id": str(run_id)},
        )

        async with async_session_factory() as db:
            run = await db.get(PromptDebugRun, run_id)
            if run is None:
                return
            run.status = "done"
            run.winner_side = r.winner_side
            run.discuss_report = r.discuss_report
            run.story = json.dumps(
                {
                    "narration": r.god,
                    "narration_a": r.narration_a,
                    "narration_b": r.narration_b,
                },
                ensure_ascii=False,
            )
            await db.commit()
    except Exception as e:  # noqa: BLE001 - 记录到调试记录，由管理员在界面查看
        logger.exception("rerun_failed run=%s", run_id)
        async with async_session_factory() as db:
            run = await db.get(PromptDebugRun, run_id)
            if run is not None:
                run.status = "failed"
                run.error = str(e)[:500]
                await db.commit()


def _seed_schemes() -> list[PromptScheme]:
    """种子方案：原版（全空=冻结默认，对照基准）+ 两套单环节实验变体（管理员改提示词的起点）。"""
    return [
        PromptScheme(name="原版", description="各环节全部使用冻结默认提示词（基准对照）"),
        PromptScheme(
            name="简洁奇术比对",
            description="实验变体：奇术比对环节换用精简系统指令（覆盖 discuss_prompt）",
            discuss_prompt=(
                "你是一名严谨的奇术比对分析师。只比较输入的两门奇术，按三相共鸣理论判断是否"
                "存在直接冲突，并必须分出一门占优奇术。不得使用 A/B 代称，不得判定平局。"
            ),
        ),
        PromptScheme(
            name="简版转写",
            description="实验变体：转写环节换用精简系统指令（覆盖 transcribe_prompt）",
            transcribe_prompt=(
                "你是一名刚打完奇术对决的奇人，现在向自己的异闻师讲述这场战斗的经历。"
                "以第一人称（「我」）完整讲完这场对战的经过，直到胜负分明，结果照实交代。"
                "只讲你知道的内容，不知道的一律不写；不得泄露对手异能的确切名称与机制。"
                "只输出讲述正文。"
            ),
        ),
    ]


async def seed_prompt_schemes() -> None:
    """启动时若 PromptScheme 空则写入种子方案（幂等：重复启动不重复写）。"""
    async with async_session_factory() as db:
        count = await db.scalar(select(func.count()).select_from(PromptScheme))
        if count:
            return
        db.add_all(_seed_schemes())
        await db.commit()
        logger.info("seeded prompt schemes")
