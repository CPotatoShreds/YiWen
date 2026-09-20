"""FastAPI 应用入口。

启动：uv run uvicorn app.main:app --reload
"""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import HTMLResponse, Response
from starlette.types import Scope

from app.api.router import api_router
from app.core.config import DEV_DEFAULT_SECRET, settings
from app.core.errors import AppError
from app.core.logger import get_logger, setup_logging
from app.core.middleware import (
    RequestIdMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.ratelimit import limiter
from app.core.retention import retention_loop
from app.db.base import Base, engine
from app.services.scenario.recovery import recover_stale_challenges
from app.services.scenario.stream import start_scenario_event_relay

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()  # 先于一切：LLM 请求日志与恢复日志都落盘
    if not settings.DEBUG and settings.SECRET_KEY == DEV_DEFAULT_SECRET:
        # 生产漏配密钥等于允许伪造任意用户 token，宁可拒绝启动
        raise RuntimeError("SECRET_KEY 仍为开发默认值：非 DEBUG 模式必须通过环境变量配置强随机密钥")
    # 新库由 Alembic 建立；仅在 DEBUG 下补齐测试/开发临时库，不替代迁移。
    if settings.DEBUG:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    await recover_stale_challenges()  # 崩溃/重启遗留的僵尸挑战自愈（30 分钟阈值，多实例安全）
    relay_task = asyncio.create_task(start_scenario_event_relay())  # 跨实例 SSE 事件中转
    retention_task = asyncio.create_task(retention_loop())  # 日志/令牌保留策略（每日清理）
    logger.info("app_ready pending=%s", settings.APP_NAME)
    yield
    for task in (relay_task, retention_task):
        task.cancel()
    await asyncio.gather(relay_task, retention_task, return_exceptions=True)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# 三个中间件均纯 ASGI（SSE 流式安全）。add_middleware 后加的在外层：RequestId 最外，
# 先设 contextvar 再进流量记录与业务；RequestLogging 记录 /api 请求到 request_logs。
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RequestIdMiddleware)

# 限流：纯装饰器模式（@limiter.limit）。不用 SlowAPIMiddleware/BaseHTTPMiddleware——
# 本应用有 SSE 逐字流，BaseHTTPMiddleware 会破坏流式（见 app/core/middleware.py 说明）；
# 全局默认阈值因此不生效，改为在敏感端点（登录/注册/创建挑战）逐个收紧。
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(AppError)
async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """业务错误信封：{detail, code} + X-Error-Code 头（前端按 code 分支）。"""
    return JSONResponse(
        status_code=exc.status,
        content={"detail": exc.message, "code": exc.code},
        headers={"X-Error-Code": exc.code},
    )


app.include_router(api_router, prefix="/api")

# Prometheus 指标（/metrics，根路径、不在 /api 下；生产建议网络层限制来源）
if settings.METRICS_ENABLED:
    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator().instrument(app).expose(app, include_in_schema=False)

# ── 生产静态托管 ─────────────────────────────────────────────────────────
# 前端构建产物打进镜像 static/（见 Dockerfile）。纯后端开发时 static/ 不存在，
# 不注册静态路由，保持原有 404 行为。API 路由先注册优先匹配，挂载点只接住剩余请求。
#
# 安全边界：文件查找、越界防护、文件发送全部委托 starlette StaticFiles（realpath +
# commonpath 校验，即 CVE-2023-29159 修复后的实现），本模块不拼接、不解析任何
# 用户可控路径。SPAStaticFiles 只在 404 时按「请求形态」决定是否回退 index.html，
# 且判定只看原始请求路径本身，从不触碰文件系统。
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


class SPAStaticFiles(StaticFiles):
    """StaticFiles + SPA 回退：仅当前端路由 404 时返回 index.html。

    回退判定（_is_client_route）是白名单式的：
    - /api/** → 保持 404（API 调用方拿到 JSON 404，不是 HTML）；
    - 含 ``..``/``.`` 段、反斜杠的路径 → 保持 404（穿越与畸形请求不给 200，日志可辨）；
    - 末段带扩展名（如 /assets/xxx.js）→ 保持 404（缺失资源不该伪装成 HTML）；
    - 其余无扩展名路径（/scenarios/123 等）→ 视为前端路由，回退 index.html。
    """

    def __init__(self, *, api_prefix: str = "/api", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.api_prefix = api_prefix

    async def get_response(self, path: str, scope: Scope) -> Response:  # type: ignore[override]
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            # 只接 404；405（方法不符）等原样上抛
            if exc.status_code != 404 or not self._is_client_route(scope):
                raise
            return HTMLResponse(INDEX_HTML)

    def _is_client_route(self, scope: Scope) -> bool:
        raw = scope.get("path", "/")
        if raw.startswith(self.api_prefix):
            return False
        if "\\" in raw:
            return False
        segments = [seg for seg in raw.split("/") if seg]
        if any(seg in ("..", ".") for seg in segments):
            return False
        last = segments[-1] if segments else ""
        return "." not in last


if (STATIC_DIR / "index.html").exists():
    INDEX_HTML = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    app.mount("/", SPAStaticFiles(directory=str(STATIC_DIR), html=True), name="spa")
