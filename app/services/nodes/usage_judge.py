"""奇术使用子集判定者节点：结算时判定赢家实际使用过的奇术编号子集。结构化输出 UsedAbilities。

提示词为用户可手调的草稿（玩法冻结后不可改）。输入：赢家角色名 + 装配奇术编号清单 + 上帝视角战斗叙述。
"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from app.services.llm import build_chat_model

USAGE_JUDGE_PROMPT = """你是异能对战的说书人裁断。摆场已落幕，你需要在上帝视角叙述中确认：赢家装配的奇术里，哪些**实际使用过**。

赢家角色：
{winner_name}

赢家装配奇术清单（按 1 起编号）：
{abilities}

上帝视角战斗叙述（双方奇术使用与胜负的权威记录）：
{narration}

请判定上方奇术清单中，哪些在这场摆场中**实际使用过**：使用过 = 叙述中明确施展了该奇术、或该奇术对战斗产生了实质影响；
只是装配但未施展、未产生影响的不要输出。通常至少一门，但确实一场未用任何奇术时可输出空列表。"""

# 使用子集判定模板：system（判定规则）+ user（占位符 {winner_name}/{abilities}/{narration}）
USAGE_TEMPLATE = ChatPromptTemplate.from_messages(
    [
        ("system", USAGE_JUDGE_PROMPT),
        ("user", "请输出实际使用过的奇术编号列表（装配清单中的编号，仅数字）。"),
    ]
)


class UsedAbilities(BaseModel):
    """本场实际使用过的奇术编号子集（1 起，对应装配清单编号）。"""

    indices: list[int] = Field(description="实际使用过的奇术编号（装配清单中的 1 起编号；未施展/未产生影响的不在列）")


def build_usage_llm() -> Runnable:
    """使用子集判定 LLM：结构化输出 UsedAbilities（method="function_calling"——DeepSeek 唯一可用方式）。

    不把 USAGE_TEMPLATE 用 `|` 拼进链：调用方用 USAGE_TEMPLATE.format_messages(...) 生成消息后 ainvoke，
    保留对 build_chat_model 的桩兼容。
    """
    return build_chat_model(thinking=False).with_structured_output(UsedAbilities, method="function_calling")
