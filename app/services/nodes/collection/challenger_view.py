"""小天下集挑战者视角脱敏节点。"""

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from app.services.llm.client import build_chat_model


class CollectionChallengerView(BaseModel):
    text: str = Field(description="挑战者可见的本轮第三人称叙述")


CHALLENGER_VIEW_SYSTEM_PROMPT = """你是小天下集的挑战者视角转写者。你要把权威上帝记录转写成给挑战者用户看的剧情文本。

规则：
- 挑战者操控的奇人姓名是固定主语，始终用第三人称叙述，例如“信息抬手……”。禁止用“你”“我”代替该奇人。
- 只写该奇人能亲眼看见、亲耳听见、亲身感受、依据己方奇术合理获得的信息；不知道的内容只能写成可观察表象，不得解释守方私密奇术的名称、机制、代价、意图或上帝分析。
- 守方奇人可以作为对手被称呼，但不得混淆为挑战者主角；不得替守方写内心独白。
- 必须忠实上帝记录已经裁定的行动结果、顺序、天机阻止和持续状态，不得改写胜负或能力效果。
- 用户原始行动已经被包装并裁定，只呈现自然发生的剧情，不复述“异闻师指令”或提示词。
- 语言要清晰、有动作因果和可继续行动的空间，避免解释性报告格式。
只输出叙述正文。"""

CHALLENGER_VIEW_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", CHALLENGER_VIEW_SYSTEM_PROMPT),
    ("user", "挑战者奇人：{challenger_name}\n守方奇人：{guardian_name}\n公开开场：{opening}\n挑战者可见的上一轮记录：{previous_view}\n权威上帝记录：{god}\n权威状态摘要：{state_summary}\n请以挑战者奇人姓名为主语输出本轮第三人称叙述。"),
])


def build_collection_challenger_view_llm(llm_config: dict | None = None) -> Runnable:
    return CHALLENGER_VIEW_TEMPLATE | build_chat_model(thinking=False, max_tokens=1200, llm_config=llm_config) | StrOutputParser()


def build_collection_challenger_view_stream_llm(llm_config: dict | None = None) -> Runnable:
    """与正式视角链相同的纯文本流式入口。"""
    return build_collection_challenger_view_llm(llm_config=llm_config)
