"""数据库引擎与会话管理（SQLAlchemy 2.0 + async）。"""
from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import settings

# SQLite：写锁等待上限 30s（默认 5s，并发对决的段落落盘冲突下会提前抛 database is locked）
if settings.DATABASE_URL.startswith("sqlite"):
    _engine_kwargs: dict = {"connect_args": {"timeout": 30}}
elif settings.DATABASE_URL.startswith("postgresql"):
    # 连接池：asyncpg 连接绑定创建它的事件循环，单 worker 单 loop 下池化安全，能复用连接、
    # 免去每请求一次建连握手（建连 ~26ms 含协议处理，是接口吞吐的瓶颈，见 conftest 注释）。
    # 测试环境（pytest + TestClient）每个测试函数独立事件循环，池化连接会孤儿化
    # （Event loop is closed），由 conftest 设 DB_POOL_ENABLED=false 回退每会话新建连接。
    if settings.DB_POOL_ENABLED:
        _engine_kwargs = {
            "pool_size": settings.DB_POOL_SIZE,
            "max_overflow": settings.DB_MAX_OVERFLOW,
            "pool_pre_ping": True,
        }
    else:
        _engine_kwargs = {"poolclass": NullPool}
else:
    _engine_kwargs = {}

engine = create_async_engine(settings.DATABASE_URL, echo=False, **_engine_kwargs)

if settings.DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_wal(dbapi_connection, _connection_record) -> None:
        """SQLite 开 WAL：读写不再互斥——并发对决逐段落盘不挡 SSE/轮询读。"""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：为每个请求提供一个数据库会话。"""
    async with async_session_factory() as session:
        yield session
