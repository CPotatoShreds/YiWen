"""启动自愈：清理实例崩溃/重启遗留的僵尸挑战。

进程重启时 create_task 的推演/比对任务随之消失，挑战会永久停在
preparing/resolving。启动扫描把它们标记 failed（用户侧可见并可重开），
同时复位在途标志。阈值判断保证多实例滚动重启时不会误杀其他实例
正在推演的新挑战。
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from app.core.logger import get_logger
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
            )
            .values(status="failed", guess_in_flight=False, verify_in_flight=False)
        )
        await db.commit()
    if result.rowcount:
        logger.warning("启动自愈：清理僵尸挑战 %s 条（preparing/resolving 超过 30 分钟）", result.rowcount)
    return result.rowcount
