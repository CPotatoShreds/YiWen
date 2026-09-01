from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ScenarioAbilityIn(BaseModel):
    name: str = Field(min_length=1, max_length=10)
    effect: str = Field(min_length=1, max_length=50)
    detail: str = Field(default="", max_length=500)


class ScenarioDraftIn(BaseModel):
    name: str = Field(min_length=1, max_length=30)
    summary: str = Field(min_length=1, max_length=120)
    background: str = Field(min_length=1, max_length=1000)
    victory_condition: str = Field(min_length=1, max_length=300)
    guidance: str = Field(default="", max_length=1000)
    guardian_name: str = Field(default="", max_length=30)
    guardian_style: str = Field(default="", max_length=200)
    guardian_tactic: str = Field(default="", max_length=500)
    guardian_abilities: list[ScenarioAbilityIn] = Field(default_factory=list, max_length=4)
    guardian_character_asset_id: UUID | None = None
    lock_version: int | None = Field(default=None, ge=1)


class ScenarioPublicOut(BaseModel):
    id: UUID
    revision_id: UUID
    name: str
    summary: str
    background: str
    victory_condition: str
    guardian_name: str
    guardian_ability_count: int
    challenge_count: int
    published_at: datetime | None = None


class ScenarioPage(BaseModel):
    items: list[ScenarioPublicOut]
    next_cursor: str | None = None


class ScenarioRevisionOut(BaseModel):
    id: UUID
    scenario_id: UUID
    revision_number: int
    status: str
    lock_version: int
    review_reason: str | None = None
    content: dict
    created_at: datetime | None = None
    published_at: datetime | None = None


class ScenarioOut(BaseModel):
    id: UUID
    owner_id: int
    current_revision_id: UUID | None
    work_revision: ScenarioRevisionOut | None = None
    challenge_count: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ScenarioChallengeIn(BaseModel):
    character_asset_id: UUID | None = None
    character_name: str = Field(default="", max_length=30)
    character_style: str = Field(default="", max_length=200)
    character_tactic: str = Field(default="", max_length=500)
    abilities: list[ScenarioAbilityIn] = Field(default_factory=list, max_length=4)


class ScenarioChallengeOut(BaseModel):
    id: int
    scenario_id: UUID
    status: str
    opening: str
    worldline_id: int
    created_at: datetime | None = None


class ScenarioMessageOut(BaseModel):
    id: int
    sequence: int
    role: str
    text: str
    created_at: datetime | None = None


class ScenarioWorldlineOut(BaseModel):
    id: int
    sequence: int
    status: str
    tokens_used: int
    messages: list[ScenarioMessageOut] = []
