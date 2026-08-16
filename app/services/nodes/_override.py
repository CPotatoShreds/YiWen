"""提示词方案调试的 system 指令覆盖缝：临时构造「system 被覆盖」的新模板。

不改任何冻结提示词常量——覆盖模板在调用时临时构造；system_prompt 为 None/空时原样
返回原模板，生产默认路径逐字节不变。
"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.prompts.chat import SystemMessagePromptTemplate


def with_system_override(template: ChatPromptTemplate, system_prompt: str | None) -> ChatPromptTemplate:
    """system 指令段被 system_prompt 覆盖的新模板；未给覆盖时原样返回冻结模板。

    仅替换首条消息的指令文本：推演段模板首条为 system 指令，usage/猜词模板首条为
    user 指令（整段即指令）——一律保留原角色，只换文本。覆盖文本必须保留原模板的
    数据槽（{info}/{god}/{viewer_name} 等），否则格式化阶段报错并落入调试记录。
    """
    if not system_prompt:
        return template
    msgs = list(template.messages)
    if msgs:
        role = "system" if isinstance(msgs[0], SystemMessagePromptTemplate) else "user"
        msgs[0] = (role, system_prompt)
    return ChatPromptTemplate.from_messages(msgs)
