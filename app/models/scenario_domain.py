"""官方情景、公开阵容与单次挑战域。"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base


class ScenarioState:
    DRAFT = "draft"
    PUBLISHED = "published"
    DELETED = "deleted"


class RosterState:
    DRAFT = "draft"
    PUBLISHED = "published"
    DELETED = "deleted"


class RosterKind:
    OFFICIAL = "official"
    PLAYER = "player"


class Scenario(Base):
    __tablename__ = "scenarios"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(30))
    normalized_name: Mapped[str] = mapped_column(String(30))
    summary: Mapped[str] = mapped_column(String(120))
    background: Mapped[str] = mapped_column(Text)
    victory_condition: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(16), default=ScenarioState.DRAFT, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (Index("uq_scenarios_name", "normalized_name", unique=True, postgresql_where=text("deleted_at IS NULL"), sqlite_where=text("deleted_at IS NULL")),)


class ScenarioRoster(Base):
    __tablename__ = "scenario_rosters"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    scenario_id: Mapped[UUID] = mapped_column(ForeignKey("scenarios.id", ondelete="RESTRICT"), index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default=RosterKind.PLAYER)
    name: Mapped[str] = mapped_column(String(30))
    state: Mapped[str] = mapped_column(String(16), default=RosterState.DRAFT, index=True)
    character_asset_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    character_name: Mapped[str] = mapped_column(String(30))
    character_bio: Mapped[str] = mapped_column(String(500), default="", server_default="")
    guidance: Mapped[str] = mapped_column(String(1000), default="", server_default="")
    challenge_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    completed_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    first_victory_avg_challenges: Mapped[float | None] = mapped_column(Float, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    current_revision_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    work_revision_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)


class ScenarioRosterRevision(Base):
    __tablename__ = "scenario_roster_revisions"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    roster_id: Mapped[UUID] = mapped_column(ForeignKey("scenario_rosters.id", ondelete="CASCADE"), index=True)
    revision_number: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(16), default=RosterState.DRAFT, index=True)
    character_name: Mapped[str] = mapped_column(String(30))
    character_bio: Mapped[str] = mapped_column(String(500), default="", server_default="")
    guidance: Mapped[str] = mapped_column(String(1000), default="", server_default="")
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    based_on_revision_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    __table_args__ = (UniqueConstraint("roster_id", "revision_number", name="uq_scenario_roster_revision_number"),)


class ScenarioRosterAbility(Base):
    __tablename__ = "scenario_roster_abilities"
    roster_id: Mapped[UUID] = mapped_column(ForeignKey("scenario_rosters.id", ondelete="CASCADE"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(10))
    effect: Mapped[str] = mapped_column(String(50))
    detail: Mapped[str] = mapped_column(String(500), default="", server_default="")
    __table_args__ = (UniqueConstraint("roster_id", "position", name="uq_scenario_roster_ability_position"),)


class ScenarioRosterRevisionAbility(Base):
    __tablename__ = "scenario_roster_revision_abilities"
    revision_id: Mapped[UUID] = mapped_column(ForeignKey("scenario_roster_revisions.id", ondelete="CASCADE"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(10))
    effect: Mapped[str] = mapped_column(String(50))
    detail: Mapped[str] = mapped_column(String(500), default="", server_default="")


class ScenarioChallengeRun(Base):
    __tablename__ = "scenario_challenge_runs"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    roster_id: Mapped[UUID] = mapped_column(ForeignKey("scenario_rosters.id", ondelete="RESTRICT"), index=True)
    challenger_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    is_preview: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", index=True)
    scenario_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    roster_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    challenger_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    challenge_number: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    guess_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    won: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    messages: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    guesses: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    derived: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    __table_args__ = (
        Index("ix_scenario_challenge_runs_roster_challenger_created", "roster_id", "challenger_id", text("created_at DESC")),
        Index("ix_scenario_challenge_runs_roster_created", "roster_id", text("created_at DESC")),
    )


class ScenarioRosterProgress(Base):
    __tablename__ = "scenario_roster_progress"
    roster_id: Mapped[UUID] = mapped_column(ForeignKey("scenario_rosters.id", ondelete="CASCADE"), primary_key=True)
    challenger_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    first_victory_challenges: Mapped[int | None] = mapped_column(Integer, nullable=True)
    guess_history: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    cracked_cards: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
