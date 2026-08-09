"""FastAPI 应用入口。

启动：uv run uvicorn app.main:app --reload
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.logger import get_logger, setup_logging
from app.db.base import Base, engine
from app.services.battle import recover_pending_battles

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()  # 先于一切：LLM 请求日志与恢复日志都落盘
    # 新库由 Alembic 建立；仅在 DEBUG 下补齐测试/开发临时库，不替代迁移。
    if settings.DEBUG:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    await recover_pending_battles()  # 重启后补推遗留 pending，防后台任务孤儿卡死
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
