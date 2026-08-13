"""【临时试验节点，不编排进任何链路】用户猜测 vs 核心一句话描述的比对检定。

承接 ability_describer：奇术 → 核心一句话描述，猜词只需命中这句即可算成功。
本节点接收「用户猜测 + 核心一句话描述（+ 完整奇术作参考）」，直接判定用户说对了哪些部分、
说错了哪些部分、漏了哪些关键特征，并给出是否命中核心（hit_core 即猜词成功）。

调用示例：
    out = await ainvoke_with_reliability(
        build_core_judge_llm(),
        GUESS_CORE_JUDGE_TEMPLATE.format_messages(
            user_guess=text, core_desc=core_desc, ability=ability_txt,
        ),
        operation="guess_core_judge",
        trace_context={"kind": "background", "trace_id": str(ability_id)},
    )
"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from app.services.llm import build_chat_model

GUESS_CORE_JUDGE_PROMPT = """你是猜词检定员。用户正在根据一段叙述文本猜测人物拥有的能力。现在给出一条奇术的**核心一句话描述**（对该能力本质特征的抽象概括，猜词成功标准就是命中它），以及用户的一次猜测。

你的任务：把用户猜测与核心一句话描述做比对，判定：
1. 用户说对了哪些部分（与核心描述/能力实际机制一致或同义、命中的特征，用能力侧措辞转述）；
2. 用户说错了哪些部分（用户明确说出、但与能力实际设定矛盾或不符合的内容，用用户原话概括）；
3. 核心描述中有、但用户没提到的关键特征（遗漏）。

判定规则：
- 说对：用户表述与核心描述或能力实际机制一致，涵盖同一特征。
- 说错：用户明确说出的内容与能力实际设定不符（机制/限制/效果冲突）。用户没提到的内容不算说错，只归入遗漏。
- **命中核心** = 说对的部分已覆盖核心一句话描述的本质特征（关键机制/限制/效果）——命中即算猜词成功。

用户猜测：
{user_guess}

核心一句话描述：
{core_desc}

完整奇术设定（供准确判定对错的参考）：
{ability}"""

GUESS_CORE_JUDGE_TEMPLATE = ChatPromptTemplate.from_messages([("user", GUESS_CORE_JUDGE_PROMPT)])


class CoreGuessVerdict(BaseModel):
    """用户猜测与核心一句话描述的比对结果。"""

    hit_core: bool = Field(description="是否命中核心一句话描述的本质特征（命中即猜词成功）")
    correct: list[str] = Field(description="用户说对了的部分（能力侧措辞转述）")
    wrong: list[str] = Field(description="用户说错了的部分（用户原话概括）")
    missing: list[str] = Field(description="核心描述中用户未提到的关键特征")
    verdict: str = Field(description="简短的判定理由")


def build_core_judge_llm() -> Runnable:
    """核心命中检定 LLM：结构化输出 CoreGuessVerdict（method="function_calling"——DeepSeek 唯一可用方式）。

    不把 GUESS_CORE_JUDGE_TEMPLATE 用 `|` 拼进链：调用方用 GUESS_CORE_JUDGE_TEMPLATE.format_messages(...) 生成消息后
    ainvoke，保留对 build_chat_model 的桩兼容。
    """
    return build_chat_model(thinking=False).with_structured_output(CoreGuessVerdict, method="function_calling")
