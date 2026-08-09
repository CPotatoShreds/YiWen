"""奇人战斗风格/战术的异步解读：解读并清洗自由文本，防止借字段注入装配清单外的奇术。

`Loadout.style` / `Loadout.tactic` 是用户自由填写的文本，会原样进入推演上下文——若在其中
写到装配清单外的能力（如战术写「火球消耗」而奇人根本没装火球类奇术），推演 LLM 会照单全收，
等于借这两个字段注入更多奇术。本模块异步生成「清洗后文本」（`style_interpretation` /
`tactic_interpretation` 缓存列）：解读 LLM 把风格/战术改写为清晰自洽的表述，同时比对已装配
奇术清单，剔除引用到清单外能力的内容；对已装配奇术的合法用法开发**不可随意修正**（倾向保留，
不误伤）。推演 `_combat_info` 喂 `interpretation or 原文`，解读缺失/失败时静默回退原文。

与 `ability_understanding` 同模式：保存后由路由后台触发，独立会话落库，失败静默（不阻塞
用户操作，推演时回退原始字段）。
"""

from contextlib import suppress

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from app.db.base import async_session_factory
from app.models.loadout import Loadout
from app.services.llm import build_chat_model
from app.services.loadouts import loadout_abilities
from app.services.reliability import ainvoke_with_reliability


class LoadoutInterpretation(BaseModel):
    """清洗后的战斗风格/战术（剔除装配清单外的能力引用，保留意图与已装配奇术的用法开发）。"""

    style: str = Field(description="清洗后的战斗风格；原为空则空字符串")
    tactic: str = Field(description="清洗后的战术；原为空则空字符串")


INTERPRETATION_SYSTEM_PROMPT = """你是奇人设定解读师。给定一位奇人的战斗风格、战术，以及这位奇人**已装配**的奇术清单，产出清洗后的版本：

1. 解读：把风格/战术改写为清晰、自洽、可直接指导对战的表述（保留原意，可理顺措辞）。
2. 清洗：逐字对照【已装配奇术清单】——凡风格/战术中出现**清单之外**的奇术名、能力名或效果（这位奇人并未装配的能力，如提到「火球」但清单里没有火球类奇术），一律剔除或改写为不含该能力的中性表述，保留原战术意图（如「用火球消耗」可改写为「远程消耗」）。绝不允许保留清单外能力，也绝不允许新增清单外能力。
3. 不可随意修正：对**已装配奇术**的用法开发（怎么用、何时用、组合连招、针对特定打法）必须原样保留，不得因措辞夸张而删改；无法确定是否属于清单外的表述，倾向保留，不误伤。
4. 原字段为空则输出空字符串。"""

INTERPRETATION_TEMPLATE = ChatPromptTemplate.from_messages(
    [
        ("system", INTERPRETATION_SYSTEM_PROMPT),
        (
            "user",
            (
                "【战斗风格】\n{style}\n\n"
                "【战术】\n{tactic}\n\n"
                "【已装配奇术清单】\n{abilities}"
            ),
        ),
    ]
)


def build_interpretation_chain() -> Runnable:
    """奇人风格/战术解读链：结构化输出 LoadoutInterpretation（method="function_calling"——DeepSeek 唯一可用方式）。

    不把 INTERPRETATION_TEMPLATE 用 `|` 拼进链：调用方用 INTERPRETATION_TEMPLATE.format_messages(...) 生成消息后
    ainvoke，保留对 build_chat_model 的桩兼容（`|` 组合会把 mock runnable 包成 RunnableLambda，破坏测试桩）。
    """
    return build_chat_model(thinking=False).with_structured_output(LoadoutInterpretation, method="function_calling")


async def ensure_loadout_interpretation(loadout_id: int) -> None:
    """生成并保存某奇人风格/战术的解读；风格战术皆空则清空缓存；失败静默（推演时回退原文）。"""
    async with async_session_factory() as db:
        loadout = await db.get(Loadout, loadout_id)
        if loadout is None:
            return
        if not (loadout.style.strip() or loadout.tactic.strip()):
            loadout.style_interpretation = ""
            loadout.tactic_interpretation = ""
            await db.commit()
            return
        abilities = await loadout_abilities(db, loadout_id)
        abilities_txt = "\n".join(f"{i + 1}. {a.name}：{a.effect}" for i, a in enumerate(abilities))
        with suppress(Exception):  # 解读失败静默（可靠性层已记日志），推演时回退原文
            out = await ainvoke_with_reliability(
                build_interpretation_chain(),
                INTERPRETATION_TEMPLATE.format_messages(
                    style=loadout.style,
                    tactic=loadout.tactic,
                    abilities=abilities_txt,
                ),
                operation="loadout_interpretation",
            )
            loadout.style_interpretation = (out.style or "").strip()
            loadout.tactic_interpretation = (out.tactic or "").strip()
            await db.commit()
