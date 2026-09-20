from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field


class ScenarioIn(BaseModel):
    name: str = Field(min_length=1, max_length=30)
    subtitle: str = Field(min_length=1, max_length=60)
    introduction: str = Field(min_length=1, max_length=120)
    background: str = Field(min_length=1, max_length=2000)
    rules: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(min_length=1, max_length=20)
    victory_condition: str = Field(min_length=1, max_length=300)
    judgement_rules: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(min_length=1, max_length=20)


class ScenarioOut(ScenarioIn):
    id: UUID
    slug: str
    status: str
    created_by: int
    published_at: datetime | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class RosterIn(BaseModel):
    character_id: UUID
    guidance: str = Field(default="", max_length=1000)


class RosterOut(BaseModel):
    id: UUID
    scenario_id: UUID
    owner_id: int
    owner_name: str
    name: str
    character_name: str
    character_bio: str
    guidance: str
    ability_count: int
    challenge_count: int
    challenger_win_rate: float | None = None
    first_victory_avg_challenges: float | None = None
    state: str
    published_at: datetime | None = None


class ChallengeIn(BaseModel):
    character_id: UUID


class ChallengeOut(BaseModel):
    id: UUID
    roster_id: UUID
    scenario_id: UUID
    status: str
    challenge_number: int
    is_preview: bool = False
    created_at: datetime | None = None


class ScenarioRosterProgressOut(BaseModel):
    roster_id: UUID
    challenger_id: int
    attempts: int
    first_victory_challenges: int | None = None
    cracked_cards: list[dict] = Field(default_factory=list)
    guess_count: int = 0
    guess_credits: int = 0
    guess_rounds: list[dict] = Field(default_factory=list)
    updated_at: datetime | None = None


class ScenarioChallengeHistoryOut(BaseModel):
    id: UUID
    status: str
    challenge_number: int
    is_preview: bool = False
    won: bool | None = None
    guess_attempts: int = 0
    created_at: datetime | None = None
    finished_at: datetime | None = None
    challenger_character_name: str | None = None
    challenger_character_id: UUID | None = None
    strategy: str = ""


class ScenarioOwnerChallengeOut(ScenarioChallengeHistoryOut):
    challenger_id: int
    challenger_name: str


class ScenarioRosterDetailOut(BaseModel):
    scenario: ScenarioOut
    roster: RosterOut
    viewer_role: str
    my_progress: ScenarioRosterProgressOut | None = None
    my_challenges: list[ScenarioChallengeHistoryOut] = Field(default_factory=list)
    owner_challenges: list[ScenarioOwnerChallengeOut] = Field(default_factory=list)
    next_cursor: str | None = None
