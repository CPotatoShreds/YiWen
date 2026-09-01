"""衍算胜利条件检定节点。"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from app.services.llm.client import build_chat_model


class CollectionJudgement(BaseModel):
    achieved: bool = Field(description="挑战者是否已满足卷公开的胜利条件")
    note: str = Field(default="", description="不剧透的简短理由")


JUDGE_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", "你是小天下集的衍算检定官。只依据卷公开的挑战者胜利条件和完整剧情记录判断是否达成。不得因为堪算进度作出判断，不得降低条件，不得泄露任一方奇术或私密信息。"),
    ("user", "卷：{volume}\n挑战者胜利条件：{victory_condition}\n公开天机：{tianji}\n公开开场：{opening}\n完整剧情记录：{history}"),
])


def build_collection_judge_llm(llm_config: dict | None = None) -> Runnable:
    return build_chat_model(thinking=False, temperature=0, llm_config=llm_config).with_structured_output(
        CollectionJudgement, method="function_calling"
    )
