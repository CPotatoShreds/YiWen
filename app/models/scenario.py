"""扁平异闻组合与挑战快照域。"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    DateTime,
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


class ScenarioStatus:
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    PUBLISHED = "published"
    REJECTED = "rejected"


class CreatorScenario(Base):
    __tablename__ = "creator_scenarios"
    __table_args__ = (
        Index("uq_creator_scenario_owner_name", "owner_id", "normalized_name", unique=True, postgresql_where=text("deleted_at IS NULL"), sqlite_where=text("deleted_at IS NULL")),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    normalized_name: Mapped[str] = mapped_column(String(30))
    current_revision_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    work_revision_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    challenge_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    purge_after: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ScenarioRevision(Base):
    __tablename__ = "scenario_revisions"
    __table_args__ = (UniqueConstraint("scenario_id", "revision_number", name="uq_scenario_revision_number"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    scenario_id: Mapped[UUID] = mapped_column(ForeignKey("creator_scenarios.id", ondelete="CASCADE"), index=True)
    revision_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default=ScenarioStatus.DRAFT, index=True)
    lock_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    based_on_revision_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ScenarioRevisionStory(Base):
    __tablename__ = "scenario_revision_stories"
    revision_id: Mapped[UUID] = mapped_column(ForeignKey("scenario_revisions.id", ondelete="CASCADE"), primary_key=True)
    name: Mapped[str] = mapped_column(String(30))
    summary: Mapped[str] = mapped_column(String(120))
    background: Mapped[str] = mapped_column(String(1000))
    victory_condition: Mapped[str] = mapped_column(String(300))
    guidance: Mapped[str] = mapped_column(String(1000), default="", server_default="")


class ScenarioRevisionGuardian(Base):
    __tablename__ = "scenario_revision_guardians"
    revision_id: Mapped[UUID] = mapped_column(ForeignKey("scenario_revisions.id", ondelete="CASCADE"), primary_key=True)
    name: Mapped[str] = mapped_column(String(30))
    style: Mapped[str] = mapped_column(String(200), default="", server_default="")
    tactic: Mapped[str] = mapped_column(String(500), default="", server_default="")


class ScenarioRevisionAbility(Base):
    __tablename__ = "scenario_revision_abilities"
    __table_args__ = (UniqueConstraint("revision_id", "position", name="uq_scenario_revision_ability_position"),)
    revision_id: Mapped[UUID] = mapped_column(ForeignKey("scenario_revisions.id", ondelete="CASCADE"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(10))
    effect: Mapped[str] = mapped_column(String(50))
    detail: Mapped[str] = mapped_column(String(500), default="", server_default="")


class ScenarioChallenge(Base):
    __tablename__ = "scenario_challenges"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scenario_revision_id: Mapped[UUID] = mapped_column(ForeignKey("scenario_revisions.id", ondelete="RESTRICT"), index=True)
    challenger_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    scenario_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    challenger_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active")
    derived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cracked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ScenarioWorldline(Base):
    __tablename__ = "scenario_worldlines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    challenge_id: Mapped[int] = mapped_column(ForeignKey("scenario_challenges.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="active")
    token_budget: Mapped[int] = mapped_column(Integer, default=24000, server_default="24000")
    tokens_used: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    derived: Mapped[bool] = mapped_column(default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ScenarioMessage(Base):
    __tablename__ = "scenario_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    worldline_id: Mapped[int] = mapped_column(ForeignKey("scenario_worldlines.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))
    challenger_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    guardian_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    omniscient_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ScenarioGuessProgress(Base):
    __tablename__ = "scenario_guess_progress"
    challenger_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    challenge_id: Mapped[int] = mapped_column(ForeignKey("scenario_challenges.id", ondelete="CASCADE"), primary_key=True)
    cards: Mapped[list] = mapped_column(JSON, default=list)
    history: Mapped[list] = mapped_column(JSON, default=list)
    comments: Mapped[list] = mapped_column(JSON, default=list)
    atom_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    verified_round: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cracked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


Index("uq_scenario_active_challenge", ScenarioChallenge.scenario_revision_id, ScenarioChallenge.challenger_id, unique=True, postgresql_where=text("status = 'active'"), sqlite_where=text("status = 'active'"))
Index("uq_scenario_active_worldline", ScenarioWorldline.challenge_id, unique=True, postgresql_where=text("status = 'active'"), sqlite_where=text("status = 'active'"))
