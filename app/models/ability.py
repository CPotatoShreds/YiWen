"""奇术数据模型。"""

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Ability(Base):
    __tablename__ = "abilities"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256(user_id:name:effect) 前 16 位，去重依据
    name: Mapped[str] = mapped_column(String(50))
    effect: Mapped[str] = mapped_column(Text)
    detail: Mapped[str] = mapped_column(Text, server_default="")  # 补充说明：限制/CD/触发条件（供 LLM 准确理解）
    tactic: Mapped[str] = mapped_column(Text, server_default="")  # 我会怎么使用它（推演时指导行动风格）
    understanding: Mapped[str] = mapped_column(Text, server_default="")  # 奇术理解（已停用：不再生成/使用，字段保留）
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
