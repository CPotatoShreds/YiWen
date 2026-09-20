"""限流：slowapi 装饰器模式（@limiter.limit）+ Redis 共享计数（多实例阈值一致）。

不用 SlowAPIMiddleware/BaseHTTPMiddleware：本应用有 SSE 逐字流，BaseHTTPMiddleware
会破坏流式（见 app/core/middleware.py 说明）。因此只有显式装饰的敏感端点受限
（登录/注册/创建挑战），无全局默认阈值。

存储在启动时静态决定：Redis 可达用 Redis（多实例共享），不可达降级为进程内存
计数（多实例下各自计数、阈值×实例数）并告警；运行中不做动态切换。
"""

import redis as sync_redis
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger("ratelimit")


def _pick_storage_uri() -> str:
    try:
        client = sync_redis.from_url(settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
        try:
            client.ping()
            return settings.REDIS_URL
        finally:
            client.close()
    except Exception as exc:  # noqa: BLE001 - 任何 Redis 故障都走内存降级
        logger.warning("Redis 不可用（%s），限流降级为进程内存计数", exc)
        return "memory://"


limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_pick_storage_uri(),
)
