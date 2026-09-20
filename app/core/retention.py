"""数据保留策略：日志类数据滚动清理（P2.5）。

retention_loop 随 lifespan 常驻，每日执行一次；清理范围：
- llm_traces：默认保留 90 天（LLM_TRACE_RETENTION_DAYS）
- request_logs：默认保留 30 天（REQUEST_LOG_RETENTION_DAYS）
- refresh_tokens：已过期或已吊销超过 7 天的行
阈值配 0 表示该类数据永久保留。
"""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from app.core.config import settings
from app.core.logger import get_logger
from app.db.base import async_session_factory
from app.models.llm_trace import LlmTrace
from app.models.refresh_token import RefreshToken
from app.models.request_log import RequestLog

logger = get_logger("retention")

_INTERVAL = timedelta(days=1)
_REVOKED_GRACE = timedelta(days=7)  # 已吊销令牌保留 7 天，供复用检测审计


def _cutoff(days: int, now):
    return None if days <= 0 else now - timedelta(days=days)


async def purge_expired(now) -> dict[str, int]:
    """执行一轮清理，返回各类删除行数（单事务）。"""
    async with async_session_factory() as db:
        counts: dict[str, int] = {}
        llm_cutoff = _cutoff(settings.LLM_TRACE_RETENTION_DAYS, now)
        if llm_cutoff is not None:
            result = await db.execute(delete(LlmTrace).where(LlmTrace.created_at < llm_cutoff))
            counts["llm_traces"] = result.rowcount  # type: ignore[attr-defined]
        log_cutoff = _cutoff(settings.REQUEST_LOG_RETENTION_DAYS, now)
        if log_cutoff is not None:
            result = await db.execute(delete(RequestLog).where(RequestLog.created_at < log_cutoff))
            counts["request_logs"] = result.rowcount  # type: ignore[attr-defined]
        result = await db.execute(
            delete(RefreshToken).where(
                (RefreshToken.expires_at < now - _REVOKED_GRACE)
                | (RefreshToken.revoked_at < now - _REVOKED_GRACE)
            )
        )
        counts["refresh_tokens"] = result.rowcount  # type: ignore[attr-defined]
        await db.commit()
    if any(counts.values()):
        logger.warning("保留策略清理：%s", counts)
    return counts


async def retention_loop() -> None:
    while True:
        try:
            now = datetime.now(UTC).replace(tzinfo=None)
            await purge_expired(now)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - 清理失败不影响业务，下轮再试
            logger.warning("保留策略清理失败：%s", exc)
        await asyncio.sleep(_INTERVAL.total_seconds())
