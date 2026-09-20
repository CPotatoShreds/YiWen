"""健康检查接口：进程存活 + DB/Redis 分项探活（负载均衡与巡检用）。"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from sqlalchemy import text

from app.core.redis import get_redis
from app.db.base import async_session_factory

router = APIRouter()


@router.get("/health")
async def health_check() -> JSONResponse:
    db_ok = True
    try:
        async with async_session_factory() as db:
            await db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - 探活失败即不可用
        db_ok = False
    redis_ok = True
    try:
        await get_redis().ping()
    except (RedisError, OSError, TimeoutError):
        redis_ok = False
    payload = {
        "status": "ok" if db_ok else "degraded",
        "db": "ok" if db_ok else "fail",
        "redis": "ok" if redis_ok else "fail",
    }
    # DB 不可达即实例不可用（503 供负载均衡摘除）；Redis 可降级，不影响健康判定
    return JSONResponse(status_code=200 if db_ok else 503, content=payload)
