"""用户自配 LLM 方案模型：provider/base_url/api_key/model 的一套配置，一用户可有多套，激活一套生效。

api_key 明文落库（与参考项目一致），API 层永不回传明文，只给 has_api_key 布尔。
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LlmProfile(Base):
    __tablename__ = "llm_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(100))  # 方案名称
    provider: Mapped[str] = mapped_column(String(50), default="openai")  # 预设标签（仅展示/填 base_url）
    base_url: Mapped[str] = mapped_column(String(500))  # OpenAI 兼容端点
    api_key: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
