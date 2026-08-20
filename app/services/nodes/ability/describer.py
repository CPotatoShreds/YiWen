"""【临时试验节点，不编排进任何链路】单条奇术的一句话描述。

接收奇术原始字段（名称/效果/补充说明，不含 AI 理解——避免预生成理解污染试验输入），
LLM 输出一句话概括。仅作试验用，不出现在推演/猜词编排中。

调用示例（等幂，需自行调用 ensure_xxx 或直接 ainvoke）：
    msgs = DESCRIBE_TEMPLATE.format_messages(
        name=ability.name, effect=ability.effect,
        detail=ability.detail,
    )
    text = await ainvoke_with_reliability(
        build_describer_llm(), msgs, operation="ability_describe",
        trace_context={"kind": "background", "trace_id": str(ability.id)},
    )
"""

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from app.services.llm.client import build_chat_model

DESCRIBE_PROMPT = """你是异能设定分析师。给定一条奇术的完整设定，用**一句简洁清晰的话**描述该能力的主要内容：核心机制、发动条件、效果与关键限制。表述严谨、精炼，使用书面语，不要口语化、不要大白话、不要寒暄铺垫。不评价强弱，只说它是什么、能做什么。

【名称】{name}
【效果】{effect}
【补充说明】{detail}"""

DESCRIBE_TEMPLATE = ChatPromptTemplate.from_messages([("system", DESCRIBE_PROMPT)])


def build_describer_llm() -> Runnable:
    """一句话描述 LLM：自由文本输出（StrOutputParser）。

    不把 DESCRIBE_TEMPLATE 用 `|` 拼进链：调用方用 DESCRIBE_TEMPLATE.format_messages(...) 生成消息后
    ainvoke，保留对 build_chat_model 的桩兼容。
    """
    return build_chat_model(thinking=False) | StrOutputParser()
