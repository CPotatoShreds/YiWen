"""小天下集 API 模型。"""

from datetime import datetime

from pydantic import BaseModel, Field


class TemporaryAbilityIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    effect: str = Field(min_length=1, max_length=1200)
    detail: str = Field(default="", max_length=1200)
    understanding: str = Field(default="", max_length=4000)


class CollectionRosterMemberIn(BaseModel):
    loadout_id: int | None = None
    name: str = Field(default="", max_length=80)
    style: str = Field(default="", max_length=240)
    tactic: str = Field(default="", max_length=1200)
    abilities: list[TemporaryAbilityIn] = Field(default_factory=list, max_length=4)


class TianjiIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=800)


class TianjiOut(TianjiIn):
    pass


class VolumeIn(BaseModel):
    title: str = Field(max_length=80)
    introduction: str = Field(max_length=1200)
    booklet_requirements: str = Field(max_length=1200)
    victory_condition: str = Field(max_length=1200)
    tianji: list[TianjiIn] = Field(min_length=1, max_length=12)


class BookletIn(BaseModel):
    defenders: list[CollectionRosterMemberIn] = Field(min_length=1, max_length=3)
    opening: str = Field(max_length=1200)
    guardian_brief: str = Field(max_length=1200)


class ChallengeIn(BaseModel):
    challengers: list[CollectionRosterMemberIn] = Field(min_length=1, max_length=3)


class ActionIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class GuessIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class CollectionAbilityOut(BaseModel):
    name: str
    effect: str
    detail: str = ""
    understanding: str = ""


class CollectionParticipantOut(BaseModel):
    name: str
    style: str = ""
    tactic: str = ""
    abilities: list[CollectionAbilityOut]


class CollectionStatsOut(BaseModel):
    challenge_count: int = 0
    derived_count: int = 0
    cracked_count: int = 0
    avg_worldlines_to_derive: float | None = None
    avg_atoms_to_crack: float | None = None


class VolumeOut(BaseModel):
    id: int
    title: str
    introduction: str
    booklet_requirements: str
    victory_condition: str
    tianji: list[TianjiOut] = []
    author: str
    mine: bool = False
    can_manage: bool = False
    booklet_count: int = 0
    created_at: datetime


class ChallengeSummaryOut(BaseModel):
    id: int
    status: str
    derived: bool
    cracked: bool
    worldline_count: int
    created_at: datetime


class BookletOut(BaseModel):
    id: int
    volume_id: int
    author: str
    defenders: list[CollectionParticipantOut] = []
    defender_people: int
    defender_ability_count: int
    opening: str
    challenges_open: bool
    mine: bool = False
    can_manage: bool = False
    stats: CollectionStatsOut = CollectionStatsOut()
    history: list[ChallengeSummaryOut] = []
    created_at: datetime


class VolumeDetailOut(VolumeOut):
    booklets: list[BookletOut] = []


class CollectionMessageOut(BaseModel):
    id: int
    sequence: int
    role: str
    text: str
    omniscient_text: str | None = None
    created_at: datetime


class CollectionGuessOut(BaseModel):
    total: int
    cards: list[dict]
    history: list[str]
    comments: list[list[dict]]
    atom_count: int
    can_verify: bool
    cracked: bool


class WorldlineOut(BaseModel):
    id: int
    sequence: int
    status: str
    token_budget: int
    tokens_used: int
    derived: bool
    messages: list[CollectionMessageOut] = []
    guess: CollectionGuessOut | None = None
    created_at: datetime


class ChallengeOut(BaseModel):
    id: int
    booklet_id: int
    opening: str
    challenger: str
    challengers: list[CollectionParticipantOut] = []
    status: str
    derived: bool
    cracked: bool
    worldlines: list[WorldlineOut] = []
    created_at: datetime
