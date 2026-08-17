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
    detail: Mapped[str] = mapped_column(Text, server_default="")  # 详细解释：机制、限制、CD、触发条件（供 AI 忠实解析因果槽位）
    understanding: Mapped[str] = mapped_column(Text, server_default="")  # 因果槽位（时序三相因果守恒律的 JSON 解析，推演主要依据，用户可见）
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
