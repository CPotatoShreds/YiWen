"""应用配置：所有可调参数统一走环境变量（见 .env.example）。"""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # 应用
    APP_NAME: str = "异闻录"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # 数据库（默认本地 SQLite，生产可换 PostgreSQL）
    DATABASE_URL: str = "sqlite+aiosqlite:///./ynfight.db"

    # 安全 / JWT
    SECRET_KEY: str = "dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 天

    # CORS：允许 React 开发服务器访问（localhost / 127.0.0.1 两种入口）
    CORS_ORIGINS: list[str] = ["http://localhost:5174", "http://127.0.0.1:5174"]

    # LLM 提供商（兼容 OpenAI 协议的任意服务，如 DeepSeek / 通义 / Ollama）
    LLM_PROVIDER: Literal["openai", "deepseek", "anthropic", "ollama"] = "openai"
    LLM_BASE_URL: str | None = None
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"
    # 全局在途 LLM 请求并发上限：单 worker 进程内所有 LLM 调用共享，防并发对决累积的
    # 在途请求打爆服务商 RPM/TPM（此前仅靠逐调用退避，429 风暴下多场同时失败）
    LLM_MAX_CONCURRENCY: int = 8


@lru_cache
def get_settings() -> Settings:
    """进程内缓存的配置单例。"""
    return Settings()


settings = get_settings()
