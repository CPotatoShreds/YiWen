"""用户拥有的奇人及其有序奇术绑定。"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(30), default="")
    bio: Mapped[str] = mapped_column(String(500), default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class CharacterAbility(Base):
    __tablename__ = "character_abilities"
    __table_args__ = (
        UniqueConstraint("character_id", "position", name="uq_character_ability_position"),
    )

    character_id: Mapped[UUID] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True)
    ability_id: Mapped[str] = mapped_column(ForeignKey("abilities.id", ondelete="RESTRICT"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer)
