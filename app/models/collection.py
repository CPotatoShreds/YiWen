"""小天下集：卷、册、挑战与可回溯的世界线。"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CollectionVolume(Base):
    __tablename__ = "collection_volumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(80))
    introduction: Mapped[str] = mapped_column(Text)
    booklet_requirements: Mapped[str] = mapped_column(Text)
    victory_condition: Mapped[str] = mapped_column(Text)
    tianji: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CollectionBooklet(Base):
    __tablename__ = "collection_booklets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    volume_id: Mapped[int] = mapped_column(ForeignKey("collection_volumes.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    defenders: Mapped[list] = mapped_column(JSON, default=list)
    opening: Mapped[str] = mapped_column(Text)
    guardian_brief: Mapped[str] = mapped_column(Text)
    challenges_open: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), default=True)
    stats_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CollectionChallenge(Base):
    __tablename__ = "collection_challenges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    booklet_id: Mapped[int] = mapped_column(ForeignKey("collection_booklets.id"), index=True)
    challenger_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    challengers: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="active")
    derived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cracked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CollectionWorldline(Base):
    __tablename__ = "collection_worldlines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    challenge_id: Mapped[int] = mapped_column(ForeignKey("collection_challenges.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="active")
    token_budget: Mapped[int] = mapped_column(Integer, default=24000)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    derived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CollectionMessage(Base):
    __tablename__ = "collection_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    worldline_id: Mapped[int] = mapped_column(ForeignKey("collection_worldlines.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))
    challenger_text: Mapped[str] = mapped_column(Text)
    guardian_text: Mapped[str] = mapped_column(Text)
    omniscient_text: Mapped[str] = mapped_column(Text)
    tokens_input: Mapped[int] = mapped_column(Integer, default=0)
    tokens_output: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CollectionGuessProgress(Base):
    __tablename__ = "collection_guess_progress"

    challenger_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    booklet_id: Mapped[int] = mapped_column(ForeignKey("collection_booklets.id", ondelete="CASCADE"), primary_key=True)
    cards: Mapped[list] = mapped_column(JSON, default=list)
    history: Mapped[list] = mapped_column(JSON, default=list)
    comments: Mapped[list] = mapped_column(JSON, default=list)
    atom_count: Mapped[int] = mapped_column(Integer, default=0)
    verified_round: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_derived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    first_derived_worldlines: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cracked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    first_cracked_atoms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


Index(
    "uq_collection_challenges_active_challenger_booklet",
    CollectionChallenge.booklet_id,
    CollectionChallenge.challenger_id,
    unique=True,
    postgresql_where=text("status = 'active'"),
    sqlite_where=text("status = 'active'"),
)
Index(
    "uq_collection_worldlines_active_challenge",
    CollectionWorldline.challenge_id,
    unique=True,
    postgresql_where=text("status = 'active'"),
    sqlite_where=text("status = 'active'"),
)
