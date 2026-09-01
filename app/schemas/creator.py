from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AbilityDraftIn(BaseModel):
    name: str = Field(default="", max_length=10)
    effect: str = Field(min_length=1, max_length=50)
    detail: str = Field(default="", max_length=500)
    lock_version: int | None = Field(default=None, ge=1)
    model_config = {"extra": "ignore"}


class CharacterDraftIn(BaseModel):
    name: str = Field(default="", max_length=30)
    bio: str = Field(default="", max_length=500)
    lock_version: int | None = Field(default=None, ge=1)
    model_config = {"extra": "ignore"}


class CharacterComponentIn(CharacterDraftIn):
    ability_asset_ids: list[UUID] = Field(default_factory=list, max_length=4)


class AnecdoteDraftIn(BaseModel):
    name: str = Field(default="", max_length=30)
    summary: str = Field(min_length=1, max_length=120)
    background: str = Field(min_length=1, max_length=1000)
    victory_condition: str = Field(min_length=1, max_length=300)
    lock_version: int | None = Field(default=None, ge=1)


class AnecdoteRejectIn(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class CharacterAbilitiesIn(BaseModel):
    revision_id: UUID
    ability_revision_ids: list[UUID] = Field(max_length=4)
    lock_version: int = Field(ge=1)


class TagIn(BaseModel):
    name: str = Field(min_length=1, max_length=30)


class TagsReplaceIn(BaseModel):
    tag_ids: list[UUID] = Field(max_length=30)


class RevisionOut(BaseModel):
    id: UUID
    asset_id: UUID
    revision_number: int
    status: str
    lock_version: int
    based_on_revision_id: UUID | None = None
    publish_error: str | None = None
    review_reason: str | None = None
    submitted_at: datetime | None = None
    reviewed_at: datetime | None = None
    reviewed_by: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    published_at: datetime | None = None
    content: dict = {}
    ability_revision_ids: list[UUID] = []

    model_config = {"from_attributes": True}


class AssetOut(BaseModel):
    id: UUID
    owner_id: int
    kind: str
    current_title: str
    normalized_title: str
    current_published_revision_id: UUID | None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None
    work_revision: RevisionOut | None = None
    model_config = {"from_attributes": True}


class ComponentOut(BaseModel):
    id: UUID
    kind: str
    name: str
    content: dict
    lock_version: int
    ability_asset_ids: list[UUID] = Field(default_factory=list)
    updated_at: datetime | None = None


class CursorPage(BaseModel):
    items: list[AssetOut]
    next_cursor: str | None = None


class TagOut(BaseModel):
    id: UUID
    name: str
    normalized_name: str
    model_config = {"from_attributes": True}


class AnecdotePublicOut(BaseModel):
    id: UUID
    revision_id: UUID
    name: str
    summary: str
    background: str
    victory_condition: str
    published_at: datetime | None = None
    created_at: datetime | None = None


class AnecdotePublicPage(BaseModel):
    items: list[AnecdotePublicOut]
    next_cursor: str | None = None


class AnecdoteReviewOut(BaseModel):
    id: UUID
    owner_id: int
    revision: RevisionOut
    owner_name: str | None = None
