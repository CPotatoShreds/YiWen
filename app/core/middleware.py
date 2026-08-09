"""请求流量中间件：记录每次 /api 请求到 request_logs，供管理员流量面板使用。

**必须用纯 ASGI**：应用有 SSE 战斗流（text/event-stream），BaseHTTPMiddleware 会
把响应包成 StreamingResponse 缓冲，破坏逐段转写。这里只包装 send 观察
http.response.start 拿状态码，不触碰 body，SSE 原样透传。

写入时机：在响应体完全发出后、中间件返回前 **await** 落库（而非 fire-and-forget）。
- 不阻塞首字节（耗时在 response.start 处取 TTFB）；
- 必在事件循环关闭前完成 → 无悬挂写事务，测试的 TestClient 生命周期下不会残留 WAL 锁。
"""

from __future__ import annotations

import time

import jwt

from app.core.config import settings
from app.core.logger import get_logger
from app.db.base import async_session_factory
from app.models.request_log import RequestLog

logger = get_logger("middleware")

# 不记录的健康/文档轮询路径（health 轮询会淹没接口 TOP；/api/admin/* 计入审计）
_SKIP_PREFIXES = ("/api/health", "/api/docs", "/api/openapi.json", "/api/redoc")


def _decode_user_id(authorization: bytes | None) -> int | None:
    """从 Authorization 头解出 user_id（轻量、不查库）；失败返回 None。"""
    if not authorization:
        return None
    try:
        scheme, _, token = authorization.decode().partition(" ")
        if scheme.lower() != "bearer" or not token:
            return None
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return int(payload.get("sub"))
    except (jwt.PyJWTError, ValueError, TypeError):
        return None


async def _write_log(path: str, method: str, status_code: int, duration_ms: int, user_id: int | None) -> None:
    """独立 session 插入一条请求日志；失败只告警，绝不抛出影响请求。"""
    try:
        async with async_session_factory() as db:
            db.add(
                RequestLog(
                    method=method,
                    path=path,
                    status_code=status_code,
                    duration_ms=duration_ms,
                    user_id=user_id,
                )
            )
            await db.commit()
    except Exception:
        logger.warning("request_log insert failed path=%s", path, exc_info=True)


class RequestLoggingMiddleware:
    """纯 ASGI 中间件：首字节耗时（TTFB）记入 request_logs。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if not path.startswith("/api") or path.startswith(_SKIP_PREFIXES):
            await self.app(scope, receive, send)
            return

        start = time.perf_counter_ns()
        headers = dict(scope.get("headers") or {})
        user_id = _decode_user_id(headers.get(b"authorization"))
        status_code: int | None = None
        duration_ms = 0

        async def send_wrapper(message: dict) -> None:
            nonlocal status_code, duration_ms
            if message["type"] == "http.response.start":
                status_code = message["status"]
                duration_ms = (time.perf_counter_ns() - start) // 1_000_000  # TTFB
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except BaseException:
            # 应用在发出 response.start 前就抛错（如路由内部 500）：补记一条
            if status_code is None:
                status_code = 500
                duration_ms = (time.perf_counter_ns() - start) // 1_000_000
            raise
        finally:
            # 响应体已完整发出：await 落库（不 fire-and-forget，防悬挂写事务）
            await _write_log(path, scope.get("method", ""), status_code or 500, duration_ms, user_id)
