"""应用配置：所有可调参数统一走环境变量（见 .env.example）。"""
from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 开发默认密钥哨兵：非 DEBUG 启动时若 SECRET_KEY 仍是该值则拒绝启动（见 app/main.py）
DEV_DEFAULT_SECRET = "dev-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # .env 中的未知/已废弃键（如已删除的 LLM_PROVIDER）静默忽略，不让残留行炸掉启动
    )

    # 应用
    APP_NAME: str = "异闻录"
    APP_VERSION: str = "0.2.0"
    DEBUG: bool = False

    # 数据库（默认本地 Docker PostgreSQL，见 docker-compose.yml；测试用独立临时库）
    DATABASE_URL: str = "postgresql+asyncpg://ynfight:ynfight@localhost:5432/ynfight"
    # 连接池：生产默认开启（asyncpg 连接绑定事件循环，单 worker 单 loop 下池化安全）。
    # 测试用 TestClient 每个测试函数独立事件循环，池化连接会孤儿化，conftest 设 false 回退
    # 每会话新建连接（NullPool）。
    DB_POOL_ENABLED: bool = True
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 60  # 池满后可临时超出到 pool_size + max_overflow（受 PG max_connections 约束）

    # Redis（缓存：奇术逐对比对结果；LRU 淘汰，见 docker-compose.yml）
    REDIS_URL: str = "redis://localhost:6380/0"

    # 安全 / JWT
    SECRET_KEY: str = DEV_DEFAULT_SECRET
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120  # 2 小时：短时 access 配合 refresh 旋转，缩小泄露窗口
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    AUTH_COOKIE_NAME: str = "ynfight_session"
    AUTH_REFRESH_COOKIE_NAME: str = "ynfight_refresh"  # 限路径 /api/auth，仅认证端点携带
    AUTH_COOKIE_SECURE: bool | None = None  # 未显式设置时按 DEBUG 推导

    # 限流（slowapi 装饰器模式，Redis 共享计数；登录/注册/创建挑战三个敏感端点）
    RATELIMIT_LOGIN: str = "5/minute"
    RATELIMIT_REGISTER: str = "10/minute"
    RATELIMIT_CHALLENGE: str = "30/minute"

    # 日志：LOG_JSON=true 输出结构化 JSON（生产日志采集用），默认人类可读文本
    LOG_JSON: bool = False

    # 邮件（密码找回/邮箱验证）：console=写日志（开发/测试零配置），smtp=真实发送
    EMAIL_PROVIDER: Literal["console", "smtp"] = "console"
    EMAIL_FROM: str = "异闻录 <no-reply@example.com>"
    SMTP_HOST: str = "smtpdm.aliyun.com"  # 阿里云邮件推送 SMTP 端点
    SMTP_PORT: int = 465
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    PUBLIC_FRONTEND_URL: str = "http://localhost:5174"  # 邮件里的重置/验证链接指向前端

    # Metrics（/metrics 根路径；生产建议网络层限制来源）
    METRICS_ENABLED: bool = True

    # 后台任务派发：inline=进程内 create_task（默认，行为同旧版）；arq=独立 worker（重试+崩溃恢复，
    # 需另起 `uv run arq app.worker.WorkerSettings`）
    TASK_QUEUE_MODE: Literal["inline", "arq"] = "inline"

    # 数据保留：日志类数据滚动清理（0=永久保留）
    LLM_TRACE_RETENTION_DAYS: int = 90
    REQUEST_LOG_RETENTION_DAYS: int = 30

    # CORS：允许 React 开发服务器访问（localhost / 127.0.0.1 两种入口）
    CORS_ORIGINS: list[str] = ["http://localhost:5174", "http://127.0.0.1:5174"]

    # LLM 提供商（兼容 OpenAI 协议的任意服务，如 DeepSeek / 通义 / Ollama）
    LLM_BASE_URL: str | None = "https://ws-mfxldgdpk6czro89.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "qwen3.7-flash"
    # 全局在途 LLM 请求并发上限：单 worker 进程内所有 LLM 调用共享，防并发对决累积的
    # 在途请求打爆服务商 RPM/TPM（此前仅靠逐调用退避，429 风暴下多场同时失败）
    LLM_MAX_CONCURRENCY: int = 1000

    # LLM 自配方案的传输/落库密钥：不配则首次使用时自动生成到 app/data/llm_profile_keys.json。
    # 生产与 Docker 部署建议显式配置（换新会导致既有方案密文不可解）；PEM 里的换行可写作字面 \n。
    LLM_PROFILE_PRIVATE_KEY: str = ""
    LLM_PROFILE_STORAGE_KEY: str = ""

    @property
    def auth_cookie_secure(self) -> bool:
        return not self.DEBUG if self.AUTH_COOKIE_SECURE is None else self.AUTH_COOKIE_SECURE

    @model_validator(mode="after")
    def validate_security(self) -> "Settings":
        if not self.DEBUG and self.SECRET_KEY == DEV_DEFAULT_SECRET:
            raise ValueError("生产环境必须设置 SECRET_KEY")
        if self.ACCESS_TOKEN_EXPIRE_MINUTES <= 0:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES 必须大于 0")
        return self


@lru_cache
def get_settings() -> Settings:
    """进程内缓存的配置单例。"""
    return Settings()


settings = get_settings()
