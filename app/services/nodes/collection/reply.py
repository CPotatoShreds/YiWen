"""挑战者行动后的守方代演与三视角叙事节点。"""

import re

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from app.services.llm.client import build_chat_model


class CollectionReply(BaseModel):
    omniscient_view: str = Field(description="完整局面记录，仅管理员与后续模型上下文可见")
    challenger_view: str = Field(description="挑战者可见的回应，不泄露守方奇术原文、守册意图或私密信息")
    guardian_view: str = Field(description="册主可见的守方记录，不泄露挑战者奇术原文或私密信息")


REPLY_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", "你是小天下集的守方代演者。根据卷规则、天机、冻结阵容与守册意图回应挑战者行动并推进故事。天机是公开世界铁律：任何奇术都不得直接改变、伤害、移动、窥探或操纵其中指明的事物；触犯时必须在剧情中明确受阻。不得泄露任何一方未公开奇术名称、效果原文或私密意图。为支持流式输出，严格按以下标签顺序输出纯文本：<omniscient_view>完整记录</omniscient_view><challenger_view>挑战者视角</challenger_view><guardian_view>守方视角</guardian_view>。标签必须闭合。"),
    ("user", "卷：{volume}\n入卷标准：{requirements}\n挑战者胜利条件：{victory_condition}\n公开天机：{tianji}\n公开开场：{opening}\n守册意图（私密）：{brief}\n守方阵容：{defenders}\n挑战者阵容：{challengers}\n上帝记录：{history}\n挑战者行动：{action}\n剩余额度：{remaining}"),
])


def build_collection_reply_llm(llm_config: dict | None = None) -> Runnable:
    return REPLY_TEMPLATE | build_chat_model(thinking=False, max_tokens=1600, llm_config=llm_config) | StrOutputParser()


def parse_collection_reply(raw: str) -> CollectionReply:
    values = {}
    for field in ("omniscient_view", "challenger_view", "guardian_view"):
        match = re.search(rf"<{field}>\s*(.*?)\s*</{field}>", raw, flags=re.DOTALL | re.IGNORECASE)
        if match:
            values[field] = match.group(1).strip()
    if len(values) != 3:
        raise ValueError("单节点回复缺少完整标签字段")
    return CollectionReply(**values)
