"""奇术相关 Pydantic 模型。"""

from pydantic import BaseModel, Field


class AbilitySetIn(BaseModel):
    name: str = Field(max_length=50, description="奇术名称")
    effect: str = Field(max_length=500, description="奇术效果")
    detail: str | None = Field(
        default=None,
        max_length=1000,
        description="补充说明（可选）：奇术的限制、CD、触发条件等，帮助 AI 更准确理解",
    )
    tactic: str | None = Field(default=None, max_length=500, description="我会怎么使用它（战术描述，可选）")


class AbilityOut(BaseModel):
    id: str
    name: str
    effect: str
    detail: str = ""
    tactic: str = ""
    understanding: str = ""  # 奇术理解（已停用：不再生成/使用，字段保留）

    model_config = {"from_attributes": True}
