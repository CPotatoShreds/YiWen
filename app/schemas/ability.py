"""奇术相关 Pydantic 模型。"""

from pydantic import BaseModel, Field


class AbilitySetIn(BaseModel):
    name: str = Field(max_length=10, description="奇术名称")
    effect: str = Field(max_length=50, description="奇术效果")
    detail: str | None = Field(
        default=None,
        max_length=500,
        description="详细解释（可选）：奇术的机制、限制、CD、触发条件等，帮助 AI 忠实解析因果槽位",
    )


class AbilityOut(BaseModel):
    id: str
    name: str
    effect: str
    detail: str = ""
    understanding: str = ""  # 因果槽位（时序三相因果守恒律的 JSON 结构化解析，用户可见，推演主要依据）

    model_config = {"from_attributes": True}
