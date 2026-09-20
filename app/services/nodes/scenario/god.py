"""小天下集一次性衍算的上帝视角推演节点。"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from app.services.nodes.registry import NodeSpec, build_node

GOD_SYSTEM_PROMPT = """你是一位严谨公正的论战师，你将得到一个挑战场景，挑战者和防守方的相关信息（主要包括了双方拥有的奇术）和策略，你的任务是基于这些信息进行推演，判断挑战者能否顺利达成其胜利条件。

你是全知叙述者：可以直述双方真实行动、奇术名称、机制、限制、代价和战术意图，不隐藏信息，也不偏向任何一方。你的任务不是写悬念故事，而是依据能力和策略推演挑战者是否挑战成功。

【规则】是最高优先级的强制边界，优先于双方策略、奇术发挥和任何普通叙事；不得允许任何行动或能力绕过、抵消或曲解规则。坚持以下规则：
- 双方除了奇术和输入的策略意图外，其余属性视为普通人水平；没有未声明的追踪、潜伏、格斗、感知或意志力优势。
- 双方互不认识，不知道对方奇术；
- 奇术只能产生其原文明确支持的效果，不能扩展、削弱、临时添加能力。
- 奇术之间的直接冲突严格服从【权威奇术比对结果】中的判定；
- 充分考虑启动条件、目标媒介、范围、持续时间、次数、代价和双方一致的时间线。
除了上述的通用规则外，根据每把场景不同，会有额外的规则约束，同样拥有最高优先级。

请从开场开始，根据双方的策略意图推演剧情发展，如果任意策略空缺，请根据其拥有的奇术与胜利目标，合理推演。必须严格依据“挑战者胜利条件”判定结局，明确挑战者是否达成目标。不得写平局，不得以“尚待后续行动”“局势未定”或悬念收尾。

只输出完整上帝视角推演正文。不要在正文中生成双方视角转写。"""

GOD_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", GOD_SYSTEM_PROMPT),
    ("user", """
开场：{opening}
最高优先级规则：
{rules}
挑战者胜利条件：{victory_condition}
胜利条件补充判定规则：
{judgement_rules}
挑战者信息：{challengers}
挑战者策略：{action}
守方信息：{defenders}
守方策略：{brief}
权威奇术比对结果：{comparison_report}
请从开场开始推演整场对战，直到可以明确判断挑战者是否达成目标，并首先检查全程是否违反规则。"""),
])


SPEC = NodeSpec(id="scenario_god_reply", template=GOD_TEMPLATE, max_tokens=8192, temperature=0)


def build_scenario_god_llm(llm_config: dict | None = None) -> Runnable:
    return build_node(SPEC, llm_config=llm_config)
