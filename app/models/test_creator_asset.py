"""Isolated test-arena ability assets; never owned by a player."""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TestAbility(Base):
    __tablename__ = "test_abilities"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(10))
    effect: Mapped[str] = mapped_column(String(50))
    detail: Mapped[str] = mapped_column(String(500), server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TestAbilityRevision(Base):
    __tablename__ = "test_ability_revisions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    test_ability_id: Mapped[str] = mapped_column(String(64), index=True)
    revision_number: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(10))
    effect: Mapped[str] = mapped_column(String(50))
    detail: Mapped[str] = mapped_column(String(500), server_default="")
