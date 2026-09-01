"""小天下集衍算的上帝视角推演节点。"""

import re

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from app.services.llm.client import build_chat_model


class CollectionGodReply(BaseModel):
    omniscient_view: str = Field(description="本轮完整的上帝视角记录，明确双方真实行动、能力触发、冲突结果和局面变化")
    state_summary: str = Field(description="供下一轮推演使用的简明权威状态，不写视角叙述，不遗漏持续中的能力与限制")
    action_result: str = Field(description="本轮挑战者行动的实际结果：生效、被阻止、部分生效或造成的状态变化")


GOD_SYSTEM_PROMPT = """你是小天下集的上帝视角推演者，负责维护唯一权威的全局战斗状态。

你必须依据卷规则、公开天机、冻结阵容、守册意图和历史状态推进当前回合。你知道双方全部真实信息，可以直述能力名称、机制、意图和冲突，但不得为了戏剧性削弱、拓展或临时添加能力。天机是公开世界铁律：任何奇术都不得直接改变、伤害、移动、窥探或操纵天机指明的事物；触犯时必须明确判定为受阻。

挑战者的原始短句已经由服务端包装为“异闻师指引下的行动意图”。你要把它解释为该奇人在当前场景中的自然行动，不能凭短句凭空增加未声明的奇术、目标、装备或效果。

每轮必须：
1. 先复核上一轮持续状态，再解析本轮行动；
2. 说明双方实际看见、发动、抵抗或受到的能力效果；
3. 明确天机约束、三相机制和直接冲突如何影响结果；
4. 保持角色行动顺序和因果自洽；
5. 输出可供下一轮继续推演的权威状态摘要。

不要生成挑战者或守方脱敏叙述。为了支持流式输出，严格按以下标签顺序输出纯文本：
<omniscient_view>本轮完整的上帝视角记录</omniscient_view>
<state_summary>供下一轮使用的简明权威状态</state_summary>
<action_result>本轮行动的实际结果</action_result>
标签必须完整闭合，标签之外不要输出任何内容。"""

GOD_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", GOD_SYSTEM_PROMPT),
    ("user", """卷：{volume}
入卷标准：{requirements}
挑战者胜利条件：{victory_condition}
公开天机：{tianji}
公开开场：{opening}
守册私密意图：{brief}
守方冻结阵容：{defenders}
挑战者冻结阵容：{challengers}
最近全局记录：{history}
本轮行动事实：{action}
剩余额度：{remaining}

请先完成全局裁定，再按指定标签输出本轮完整记录、状态摘要和行动结果。"""),
])


def build_collection_god_llm(llm_config: dict | None = None) -> Runnable:
    return GOD_TEMPLATE | build_chat_model(thinking=False, max_tokens=1800, llm_config=llm_config) | StrOutputParser()


def parse_collection_god_reply(raw: str) -> CollectionGodReply:
    """从流式纯文本中确定性提取三段上帝记录。"""
    values = {}
    for field in ("omniscient_view", "state_summary", "action_result"):
        match = re.search(rf"<{field}>\s*(.*?)\s*</{field}>", raw, flags=re.DOTALL | re.IGNORECASE)
        if match:
            values[field] = match.group(1).strip()
    if len(values) != 3:
        raise ValueError("上帝节点缺少完整标签字段")
    return CollectionGodReply(**values)
