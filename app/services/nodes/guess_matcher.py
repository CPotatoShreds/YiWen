"""猜词匹配者节点：败方每次道出猜测，把猜测内容匹配到各张空白卡片并给出进度增量。结构化输出 CardMatches。

取代旧的 guess_judge.py（一次性整体打分）。提示词为用户可手调的草稿（玩法冻结后不可改）。
关键约束：snippet 只能引用败方自己的话，绝不允许泄露真实奇术名/效果——这是胜负关键。
"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from app.services.llm import build_chat_model

GUESS_MATCHER_PROMPT = """你是异能对战的说书人裁断。败方在猜对家实际使用过的奇术：对家使用过的每门奇术对应一张空白卡片，
败方多次道出猜测，每次猜测命中哪门，就把相关内容贴到哪张卡上并解锁一部分猜测条。

败方视角叙述（败方唯一的线索来源，话本各看各的）：
{narration}

对家实际使用过的奇术（仅作你判定的参考基准，**严禁**把名称、效果或任何原文泄露进输出）：
{abilities}

当前各卡已匹配内容（index 为卡片编号，1 起）：
{cards}

败方本轮新道出的猜测文本：
{text}

请逐条比对本轮猜测文本与每门奇术：猜测中提到并指向该奇术的片段，作为该卡的匹配片段输出；
同时给出进度增量 progress_delta（0-100）——本次猜测推动对该奇术理解的进展，猜得越准越高
（完全点到核心机制可到 100，模糊提及给低值，完全无关为 0）。

约束：
1. snippet 是对应奇术特征的语义转述：以奇术侧的说法描述败方本轮话中**指向该奇术**的部分
   （如败方说「无敌」、奇术含免疫伤害效果 → 可输出「该奇术有免疫伤害效果」；败方说「击掌才能发动」→
   可输出「以击掌为发动条件」）。但**只允许覆盖败方本轮已经点到的特征**，不得引入败方未提到的效果细节
   （额外效果、冷却、限制等），也不得出现奇术的真实名称——既不提前揭示答案，也不给败方新线索。
2. 只输出本轮有进展的卡片；本轮未被提到的卡片不输出（其进度保持不变）。
3. index 为该卡编号（1 起），与「当前各卡已匹配内容」的 index 对应。"""

# 猜词匹配模板：system（判定规则）+ user（占位符 {narration}/{abilities}/{cards}/{text}）
GUESS_MATCHER_TEMPLATE = ChatPromptTemplate.from_messages(
    [
        ("system", GUESS_MATCHER_PROMPT),
        ("user", "请输出本轮有进展的卡片匹配结果（index、snippet、progress_delta）。"),
    ]
)


class CardMatch(BaseModel):
    """单张卡片的匹配结果：落入该卡的内容片段与进度增量。"""

    index: int = Field(description="卡片编号（1 起）")
    snippet: str = Field(description="本轮猜测指向该奇术的语义转述（以奇术侧措辞覆盖败方点到的特征，禁止出现奇术真实名称）")
    progress_delta: int = Field(description="本轮对该奇术理解的进展增量（0-100）")


class CardMatches(BaseModel):
    """本轮有进展的卡片匹配结果列表（无进展的卡不输出）。"""

    matches: list[CardMatch] = Field(description="本轮有进展的卡片匹配结果")


def build_guess_matcher_llm() -> Runnable:
    """猜词匹配 LLM：结构化输出 CardMatches（method="function_calling"——DeepSeek 唯一可用方式）。

    不把 GUESS_MATCHER_TEMPLATE 用 `|` 拼进链：调用方用 GUESS_MATCHER_TEMPLATE.format_messages(...) 生成消息后
    ainvoke，保留对 build_chat_model 的桩兼容（`|` 组合会把 mock runnable 包成 RunnableLambda，破坏测试桩）。
    """
    return build_chat_model(thinking=False).with_structured_output(CardMatches, method="function_calling")
