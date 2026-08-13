"""通知模型：其他玩家与你交互时产生的站内通知（铃铛）。

type 决定文案与跳转语义：board_challenge（点将挑战，跳 /board）、
battle_report（新战报，跳 /battles/{id}）、guess_progress（猜词进展，跳 /battles/{id}）。
title/body 在创建时已拼好（说书语系），actor_id 仅溯源；read_at 非空 = 已读。
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_read", "user_id", "read_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)  # 接收者
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)  # 触发者（仅溯源）
    type: Mapped[str] = mapped_column(String(20))  # board_challenge / battle_report / guess_progress
    title: Mapped[str] = mapped_column(String(80))
    body: Mapped[str] = mapped_column(Text, default="")
    ref_type: Mapped[str | None] = mapped_column(String(10), nullable=True)  # battle / board
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # null = 未读
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
