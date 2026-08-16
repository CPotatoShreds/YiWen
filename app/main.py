"""FastAPI 应用入口。

启动：uv run uvicorn app.main:app --reload
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import settings
from app.core.logger import get_logger, setup_logging
from app.db.base import Base, engine
from app.services.battle import recover_pending_battles
from app.services.prompt_debug import seed_prompt_schemes

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()  # 先于一切：LLM 请求日志与恢复日志都落盘
    # 新库由 Alembic 建立；仅在 DEBUG 下补齐测试/开发临时库，不替代迁移。
    if settings.DEBUG:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    await recover_pending_battles()  # 重启后补推遗留 pending，防后台任务孤儿卡死
    await seed_prompt_schemes()  # 提示词方案表空则写入种子方案（幂等）
    logger.info("app_ready pending=%s", settings.APP_NAME)
    yield


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

app.include_router(api_router, prefix="/api")

# ── 生产静态托管 ─────────────────────────────────────────────────────────
# 前端构建产物打进镜像 static/（见 Dockerfile）。纯后端开发时 static/ 不存在，
# 不注册静态路由，保持原有 404 行为。API 路由先注册优先匹配，SPA 回退不碰 /api。
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

if (STATIC_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="static_assets")

if (STATIC_DIR / "index.html").exists():
    INDEX_HTML = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    @app.get("/{full_path:path}", response_model=None)
    async def spa_fallback(full_path: str) -> FileResponse | HTMLResponse:
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = STATIC_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return HTMLResponse(INDEX_HTML)
