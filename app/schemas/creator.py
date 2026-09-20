"""用户奇人、奇术编辑接口。"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class AbilityCreate(BaseModel):
    name: str = Field(max_length=10)
    effect: str = Field(min_length=1, max_length=50)
    detail: str = Field(default="", max_length=500)

    @field_validator("name", "effect", "detail")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("name")
    @classmethod
    def require_name(cls, value: str) -> str:
        if not value:
            raise ValueError("名称不能为空")
        return value

    @field_validator("effect")
    @classmethod
    def require_effect(cls, value: str) -> str:
        if not value:
            raise ValueError("效果不能为空")
        return value

class AbilityOut(BaseModel):
    id: str
    owner_id: int
    name: str
    effect: str
    detail: str
    understanding: str
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}

class CharacterCreate(BaseModel):
    name: str = Field(max_length=30)
    bio: str = Field(default="", max_length=500)
    ability_ids: list[str] = Field(default_factory=list, max_length=4)

    @field_validator("name", "bio")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("name")
    @classmethod
    def require_name(cls, value: str) -> str:
        if not value:
            raise ValueError("名称不能为空")
        return value

class CharacterOut(BaseModel):
    id: UUID
    owner_id: int
    name: str
    bio: str
    ability_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

class CharacterDetailOut(CharacterOut):
    abilities: list[AbilityOut] = Field(default_factory=list)
