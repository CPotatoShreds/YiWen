"""异闻师拥有的奇术（多对多）。抽取永不重复：同一 (user, ability) 只会出现一次。"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserAbility(Base):
    __tablename__ = "user_abilities"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    ability_id: Mapped[str] = mapped_column(ForeignKey("abilities.id"), primary_key=True)
    obtained_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
