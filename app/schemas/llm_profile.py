"""用户自配 LLM 方案相关 Pydantic 模型。"""

from datetime import datetime

from pydantic import BaseModel, Field


class LlmProfileCreate(BaseModel):
    label: str = Field(min_length=1, max_length=50, description="方案名称")
    provider: str = Field(default="openai", max_length=50, description="预设标签（仅展示/填 base_url）")
    base_url: str = Field(min_length=1, max_length=500, description="OpenAI 兼容端点")
    api_key: str = Field(min_length=1, description="API 密钥")
    model: str = Field(min_length=1, max_length=100, description="默认模型")


class LlmProfileUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=50)
    provider: str | None = Field(default=None, max_length=50)
    base_url: str | None = Field(default=None, min_length=1, max_length=500)
    api_key: str | None = Field(default=None, description="留空/None 表示保留原值")
    model: str | None = Field(default=None, min_length=1, max_length=100)

    model_config = {"extra": "forbid"}  # 别把空 api_key 误当成清除原值


class LlmProfileOut(BaseModel):
    id: int
    label: str
    provider: str
    base_url: str
    model: str
    has_api_key: bool  # 明文永不回传，只给布尔
    is_active: bool  # 当前是否为本用户激活方案
    created_at: datetime
