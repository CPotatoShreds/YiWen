"""衍算胜利条件检定节点。"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from app.services.nodes.registry import NodeSpec, build_node


class ScenarioJudgement(BaseModel):
    achieved: bool = Field(description="挑战者是否已经达成公开的目标")
    reason: str = Field(description="根据完整剧情记录说明挑战者达成或未达成目标的判断依据")


JUDGE_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", "你是小天下集的目标检定官。只依据卷的最高优先级规则、公开的挑战者目标、判定规则和完整剧情记录判断挑战者是否达成目标。规则优先于策略与奇术发挥；不得因为堪算进度作出判断，不得降低条件，不得泄露任一方奇术或私密信息。只做目标达成检定，不裁定胜负。"),
    ("user", "卷：{volume}\n最高优先级规则：{rules}\n挑战者目标：{victory_condition}\n目标补充判定规则：{judgement_rules}\n公开开场：{opening}\n完整剧情记录：{history}\n\n请输出 achieved 与 reason：achieved 为挑战者是否已达成目标；reason 为简短、不剧透的判断依据。"),
])


SPEC = NodeSpec(id="scenario_goal_judgement", template=JUDGE_TEMPLATE, temperature=0, schema=ScenarioJudgement)


def build_scenario_judge_llm(llm_config: dict | None = None) -> Runnable:
    return build_node(SPEC, llm_config=llm_config)
