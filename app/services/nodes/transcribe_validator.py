"""转写校验节点：核对视角叙述是否满足全部转写要求，输出结构化判定；附修复重写链。

转写 LLM 输出不可全信——校验节点以「质检员」身份逐条核对（第一人称视角边界、结果与
上帝视角结尾一致、对手异能保密、失忆期间禁写、上帝全局信息禁入），不通过时列出具体
违规点，供修复链按违规清单重写该侧视角。单侧链而非 A/B 并行链：修复后需对失败侧单独
再校验，并发由调用方（deduction.run_deduction）以 asyncio.gather 编排。
"""

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from app.services.llm import build_chat_model

VALIDATE_SYSTEM_PROMPT = """你是转写质检员。把一段「视角叙述」对照以下要求逐条核对，判定是否**全部满足**：
1. 第一人称、以视角人物为中心，以向自己的异闻师讲述经历的口吻，完整讲完这场对战直到胜负分明；只讲 TA 亲眼所见、亲耳所闻、亲身经历与内心判断（或其能力获取到的信息）；TA 不知道的内容一律不能写；TA 失去意识的时间段内不能写任何内容。
2. 叙述交代的结果（赢/输/平局）必须与【上帝视角全文】结尾宣布的结果一致，不能自相矛盾。
3. 严禁泄露对手异能的确切名称、具体效果、发动条件、机制原理、冷却与弱点、意图与全貌——只能通过表象间接呈现（如「对方掌心凝聚火焰」「对手身形诡异地扭曲」），不得解释原理、不得点破机制、不得出现异能名称或效果原文。
4. 严禁写入视角人物无从知晓的全局信息（对手的内心盘算、双方异能的全貌对比、场外形势），以及上帝视角独有的信息。

核对方法：以【双方信息】中对家异能、【上帝视角全文】（含结尾宣布的结果）为基准——凡视角叙述中出现视角人物本不该知道的细节（对家异能确切信息、他人内心、全貌对比等），或交代的结果与上帝视角结尾宣布的不符，即为违规。逐条核对后给出判定；违规时逐条列出具体违规原文与对应要求编号，供修复重写引用。"""

VALIDATE_USER_MSG = (
    "【双方信息】\n{info}\n\n"
    "【上帝视角全文】\n{god}\n\n"
    "【待核对视角叙述】（视角人物：{viewer_name}）\n{narration}"
)

VALIDATE_TEMPLATE = ChatPromptTemplate.from_messages(
    [
        ("system", VALIDATE_SYSTEM_PROMPT),
        ("user", VALIDATE_USER_MSG),
    ]
)


class TranscribeVerdict(BaseModel):
    """单侧视角叙述的校验判定。"""

    passes: bool = Field(description="该视角叙述是否满足全部转写要求")
    violations: list[str] = Field(
        default_factory=list,
        description="未满足的要求逐条列出（含具体违规原文/位置与要求编号）；passes 为 true 时为空列表",
    )


def build_validate_chain() -> Runnable:
    """单侧转写校验链：结构化输出 TranscribeVerdict（method="function_calling"——DeepSeek 唯一可用方式）。"""
    return VALIDATE_TEMPLATE | build_chat_model(thinking=False).with_structured_output(
        TranscribeVerdict, method="function_calling"
    )


REPAIR_SYSTEM_PROMPT = """你是转写修稿师。给定一段不合格的视角叙述与质检列出的违规点，按转写规则重写这段叙述，修正全部违规。

转写规则：
- 第一人称、以视角人物为中心，以向自己的异闻师讲述经历的口吻，完整讲完这场对战直到胜负分明；只讲 TA 亲眼所见、亲耳所闻、亲身经历与内心判断；TA 不知道的内容一律不能写；TA 失去意识的时间段内不能写任何内容。
- 交代的结果（赢/输/平局）必须与【上帝视角全文】结尾宣布的结果一致，不能自相矛盾。
- 严禁泄露对手异能的确切名称、具体效果、发动条件、机制原理、冷却与弱点、意图与全貌——只能通过表象间接呈现。
- 严禁写入视角人物无从知晓的全局信息。

只输出重写后的完整视角叙述。"""

REPAIR_USER_MSG = (
    "【双方信息】\n{info}\n\n"
    "【上帝视角全文】\n{god}\n\n"
    "【视角人物】\n{viewer_name}\n\n"
    "【不合格视角叙述】\n{narration}\n\n"
    "【质检违规点】\n{violations}\n\n"
    "请按转写规则把以上视角叙述重写为「{viewer_name}」第一人称向自己的异闻师讲述的完整经历，修正全部违规点，只输出重写后的完整视角叙述。"
)

REPAIR_TEMPLATE = ChatPromptTemplate.from_messages(
    [
        ("system", REPAIR_SYSTEM_PROMPT),
        ("user", REPAIR_USER_MSG),
    ]
)


def build_repair_chain() -> Runnable:
    """单侧修复链：按质检违规点重写视角叙述，纯文本输出。"""
    return REPAIR_TEMPLATE | build_chat_model(thinking=False) | StrOutputParser()
