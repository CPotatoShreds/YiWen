"""Private creator assets: stable identities and immutable revisions."""

from datetime import datetime
from enum import StrEnum
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


class AssetKind(StrEnum):
    ABILITY = "ability"
    CHARACTER = "character"
    ANECDOTE = "anecdote"


class RevisionStatus(StrEnum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    REJECTED = "rejected"
    PUBLISHING = "publishing"
    PUBLISH_FAILED = "publish_failed"
    PUBLISHED = "published"


class DerivationStatus(StrEnum):
    LEGACY = "legacy"
    STALE = "stale"
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class CreatorAsset(Base):
    __tablename__ = "creator_assets"
    __table_args__ = (
        Index(
            "uq_creator_asset_owner_kind_title",
            "owner_id",
            "kind",
            "normalized_title",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    current_title: Mapped[str] = mapped_column(String(50))
    normalized_title: Mapped[str] = mapped_column(String(50))
    current_published_revision_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    purge_after: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CreatorAssetRevision(Base):
    __tablename__ = "creator_asset_revisions"
    __table_args__ = (
        UniqueConstraint("asset_id", "revision_number", name="uq_creator_revision_number"),
        UniqueConstraint("id", "asset_id", name="uq_creator_revision_asset"),
        Index(
            "uq_creator_asset_work_revision",
            "asset_id",
            unique=True,
            postgresql_where=text("status IN ('draft', 'pending_review', 'publishing', 'publish_failed')"),
            sqlite_where=text("status IN ('draft', 'pending_review', 'publishing', 'publish_failed')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    asset_id: Mapped[UUID] = mapped_column(ForeignKey("creator_assets.id", ondelete="CASCADE"), index=True)
    revision_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default=RevisionStatus.DRAFT.value, index=True)
    based_on_revision_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    publish_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AbilityRevisionContent(Base):
    __tablename__ = "ability_revision_contents"
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("creator_asset_revisions.id", ondelete="CASCADE"), primary_key=True
    )
    name: Mapped[str] = mapped_column(String(10))
    effect: Mapped[str] = mapped_column(String(50))
    detail: Mapped[str] = mapped_column(String(500), server_default="")


class CharacterRevisionContent(Base):
    __tablename__ = "character_revision_contents"
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("creator_asset_revisions.id", ondelete="CASCADE"), primary_key=True
    )
    name: Mapped[str] = mapped_column(String(30), server_default="")
    bio: Mapped[str] = mapped_column(String(500), server_default="")
    # 兼容旧修订；新接口不再读写这两列
    style: Mapped[str] = mapped_column(String(200), server_default="")
    tactic: Mapped[str] = mapped_column(String(500), server_default="")


class AnecdoteRevisionContent(Base):
    __tablename__ = "anecdote_revision_contents"
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("creator_asset_revisions.id", ondelete="CASCADE"), primary_key=True
    )
    name: Mapped[str] = mapped_column(String(30))
    summary: Mapped[str] = mapped_column(String(120))
    background: Mapped[str] = mapped_column(String(1000))
    victory_condition: Mapped[str] = mapped_column(String(300))


class CharacterRevisionAbility(Base):
    __tablename__ = "character_revision_abilities"
    __table_args__ = (UniqueConstraint("revision_id", "position", name="uq_character_revision_position"),)
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("creator_asset_revisions.id", ondelete="CASCADE"), primary_key=True
    )
    ability_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("creator_asset_revisions.id", ondelete="RESTRICT"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)


class CreatorTag(Base):
    __tablename__ = "creator_tags"
    __table_args__ = (UniqueConstraint("owner_id", "normalized_name", name="uq_creator_tag_owner_name"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(30))
    normalized_name: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CreatorAssetTag(Base):
    __tablename__ = "creator_asset_tags"
    asset_id: Mapped[UUID] = mapped_column(ForeignKey("creator_assets.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[UUID] = mapped_column(ForeignKey("creator_tags.id", ondelete="CASCADE"), primary_key=True)


class AssetRevisionDerivation(Base):
    __tablename__ = "asset_revision_derivations"
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("creator_asset_revisions.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(20), default=DerivationStatus.PENDING.value)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    task_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class AssetEvent(Base):
    __tablename__ = "asset_events"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    asset_id: Mapped[UUID] = mapped_column(ForeignKey("creator_assets.id", ondelete="RESTRICT"), index=True)
    revision_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    topic: Mapped[str] = mapped_column(String(80), index=True)
    aggregate_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("owner_id", "command_key", name="uq_idempotency_owner_key"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    command_key: Mapped[str] = mapped_column(String(128))
    response_status: Mapped[int] = mapped_column(Integer)
    response_body: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
