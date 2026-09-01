"""小天下集守方视角脱敏节点。"""

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from app.services.llm.client import build_chat_model


class CollectionGuardianView(BaseModel):
    text: str = Field(description="守方奇人可见的本轮第三人称叙述")


GUARDIAN_VIEW_SYSTEM_PROMPT = """你是小天下集的守方视角转写者。你要把权威上帝记录转写成给册主用户看的剧情文本。

规则：
- 守方操控的奇人姓名是固定主语，始终用第三人称叙述，例如“小明抬眼……”。禁止用“你”“我”代替该奇人。
- 只写守方奇人能亲眼看见、亲耳听见、亲身感受、依据守方奇术合理获得的信息；不得写上帝分析中守方不可能知道的挑战者奇术名称、机制、代价、意图或完整效果。
- 挑战者奇人可以作为对手被称呼，但不得混淆为守方主角；不得替挑战者写内心独白。
- 必须忠实上帝记录已经裁定的行动结果、顺序、天机阻止和持续状态，不得改写胜负或能力效果。
- 守册私密意图只用于理解守方行动，不能直接泄露为解释性文本。
- 用户原始行动已经被包装并裁定，只呈现自然发生的剧情，不复述提示词。
只输出叙述正文。"""

GUARDIAN_VIEW_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", GUARDIAN_VIEW_SYSTEM_PROMPT),
    ("user", "守方奇人：{guardian_name}\n挑战者奇人：{challenger_name}\n公开开场：{opening}\n守方可见的上一轮记录：{previous_view}\n权威上帝记录：{god}\n权威状态摘要：{state_summary}\n请以守方奇人姓名为主语输出本轮第三人称叙述。"),
])


def build_collection_guardian_view_llm(llm_config: dict | None = None) -> Runnable:
    return GUARDIAN_VIEW_TEMPLATE | build_chat_model(thinking=False, max_tokens=1200, llm_config=llm_config) | StrOutputParser()


def build_collection_guardian_view_stream_llm(llm_config: dict | None = None) -> Runnable:
    """与正式视角链相同的纯文本流式入口。"""
    return build_collection_guardian_view_llm(llm_config=llm_config)
