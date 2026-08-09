"""故人关系。一行表示一对关系，status: pending（待对方应帖）/ accepted。"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Friendship(Base):
    __tablename__ = "friendships"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)  # 发起方
    friend_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)  # 接收方
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
