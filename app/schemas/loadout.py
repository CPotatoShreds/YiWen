"""奇人相关 Pydantic 模型。"""

from pydantic import BaseModel, Field

from app.schemas.ability import AbilityOut


class LoadoutSetIn(BaseModel):
    enabled: bool | None = None  # 解封：已解封 = 可主动启程，且进入台下听客
    name: str | None = Field(default=None, max_length=30, description="奇人姓名")
    style: str | None = Field(default=None, max_length=200, description="角色介绍（可选，原战斗风格）")
    tactic: str | None = Field(default=None, max_length=500, description="这位奇人会怎么打（战术描述，可选）")
    ability_ids: list[str] | None = Field(default=None, description="创建时直接装配的奇术（1-4 个；仅创建时使用）")


class LoadoutOut(BaseModel):
    id: int
    name: str = ""
    style: str = ""
    enabled: bool
    tactic: str = ""
    abilities: list[AbilityOut] = []
