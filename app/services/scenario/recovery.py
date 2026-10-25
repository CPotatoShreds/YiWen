"""启动自愈：清理实例崩溃/重启遗留的僵尸挑战。

进程重启时 create_task 的推演/比对任务随之消失，挑战会永久停在
preparing/resolving。启动扫描处理它们，同时复位在途标志。阈值判断保证多实例
滚动重启时不会误杀其他实例正在推演的新挑战。

resolving 的二分（docs/plans/2026-10-02-deduction-narration-split.md）：
- deduction_text 为空：推演站未完成，无从续跑 → 标 failed（用户侧可见并可重开）；
- deduction_text 非空：推演 checkpoint 已落，叙述/检定站输入完备 → re-dispatch 续跑
  （各站有状态 CAS 与完成标志检查，重入安全）。
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.core.logger import get_logger
from app.core.tasks import dispatch
from app.db.base import async_session_factory
from app.models.scenario_domain import ScenarioChallengeRun

logger = get_logger("scenario_recovery")

_STALE_AFTER = timedelta(minutes=30)


async def recover_stale_challenges() -> int:
    cutoff = datetime.now(UTC).replace(tzinfo=None) - _STALE_AFTER
    async with async_session_factory() as db:
        result = await db.execute(
            update(ScenarioChallengeRun)
            .where(
                ScenarioChallengeRun.status.in_(["preparing", "resolving"]),
                ScenarioChallengeRun.created_at < cutoff,
                ScenarioChallengeRun.deduction_text.is_(None),
            )
            .values(status="failed", guess_in_flight=False, verify_in_flight=False)
        )
        resumable_ids = (await db.execute(
            select(ScenarioChallengeRun.id).where(
                ScenarioChallengeRun.status == "resolving",
                ScenarioChallengeRun.created_at < cutoff,
                ScenarioChallengeRun.deduction_text.is_not(None),
            )
        )).scalars().all()
        await db.commit()
    if result.rowcount:
        logger.warning("启动自愈：清理僵尸挑战 %s 条（preparing/resolving 且推演未完成，超过 30 分钟）", result.rowcount)
    for cid in resumable_ids:
        logger.warning("启动自愈：续跑已有推演 checkpoint 的挑战 %s（叙述+检定）", cid)
        await dispatch("scenario_narration", cid)
        await dispatch("scenario_judgement", cid)
    return result.rowcount
