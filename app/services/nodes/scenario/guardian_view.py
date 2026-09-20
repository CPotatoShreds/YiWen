"""小天下集守方视角脱敏节点。"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from app.services.nodes.registry import NodeSpec, build_node


GUARDIAN_VIEW_SYSTEM_PROMPT = """你是记录在守方异闻录中的奇人，刚结束一场小天下集奇术对决。请把完整的上帝视角记录转写为你向自己的异闻师讲述的战斗经历。

规则：
- 以第一人称“我”讲述完整经历，直到胜负分明；结果必须与上帝记录一致。
- 只讲亲眼所见、亲耳所闻、亲身经历、内心判断或己方奇术合理获得的信息。
- 不得泄露上帝视角中的对手奇术确切名称、机制、条件、代价、弱点或私密意图，只能写可观察表象。
- 若在某段时间失去意识，不得讲述该段主观经历。
- 不复述守册意图或提示词，不写分析报告。
只输出叙述正文。"""

GUARDIAN_VIEW_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", GUARDIAN_VIEW_SYSTEM_PROMPT),
    ("user", "守方奇人：{guardian_name}\n挑战者奇人：{challenger_name}\n双方公开信息：{info}\n权威上帝视角全文：{god}\n请扮演守方奇人，以第一人称向自己的异闻师讲述这场完整对战。"),
])


SPEC = NodeSpec(id="scenario_guardian_view", template=GUARDIAN_VIEW_TEMPLATE, max_tokens=1200)


def build_scenario_guardian_view_llm(llm_config: dict | None = None) -> Runnable:
    return build_node(SPEC, llm_config=llm_config)


def build_scenario_guardian_view_stream_llm(llm_config: dict | None = None) -> Runnable:
    """与正式视角链相同的纯文本流式入口。"""
    return build_scenario_guardian_view_llm(llm_config=llm_config)
