"""AI 异能理解：保存异能后异步生成 LLM 对异能的理解，结果保存可复用。

推演 LLM 每次推演都重新理解异能太浪费；这里把「对异能的理解」提前生成并缓存到
`Ability.understanding`，推演时直接喂给推演 LLM。保存异能后由路由后台触发，
已有理解则跳过（复用）；失败静默（不阻塞异能保存，推演时退回原始字段）。
"""

from contextlib import suppress

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from app.db.base import async_session_factory
from app.models.ability import Ability
from app.services.llm import build_chat_model
from app.services.reliability import ainvoke_with_reliability

UNDERSTANDING_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "你是异能设定分析助手。根据异能的名称、效果、补充说明与战术用法，生成一段对该异能的**客观理解**："
                "说清它的核心机制、触发条件、限制、弱点与典型用法，供战斗推演使用。"
                "不要评价强弱，不要替持有者说话，用第三人称客观描述。150-250 字。"
            ),
        ),
        ("user", "名称：{name}\n效果：{effect}\n补充说明：{detail}\n战术用法：{tactic}"),
    ]
)


def build_understanding_chain() -> Runnable:
    """构建异能理解生成链（独立构建函数，供测试打桩）。"""
    return UNDERSTANDING_PROMPT | build_chat_model(thinking=False) | StrOutputParser()


async def ensure_ability_understanding(ability_id: str) -> None:
    """生成并保存异能理解；已有理解则跳过；失败静默（不阻塞异能保存）。"""
    async with async_session_factory() as db:
        ability = await db.get(Ability, ability_id)
        if ability is None or ability.understanding:
            return
        with suppress(Exception):  # 后台生成失败静默（可靠性层已记日志），下次推演走原始字段
            text = await ainvoke_with_reliability(
                build_understanding_chain(),
                {
                    "name": ability.name,
                    "effect": ability.effect,
                    "detail": ability.detail,
                    "tactic": ability.tactic,
                },
                operation="understanding",
            )
            ability.understanding = (text or "").strip()
            await db.commit()
