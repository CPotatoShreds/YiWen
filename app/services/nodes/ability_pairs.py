"""能力对比节点：把双方奇术两两配对，逐对判断是否存在冲突效果，依三相共鸣理论分判高下。

输出结构化判定（PairVerdict），汇总为对比报告喂给推演节点（deducer 的 {discuss_report} 槽位），
暂时替代讨论节点。本节点只做**逐对对比**，不替推演节点裁断胜负（胜负仍由推演 LLM 结尾句解析）。

三相共鸣理论从 DISCUSS_SYSTEM_PROMPT（discusser.py）摘取，保证对比与推演同一套世界观规则。
"""

from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from app.services.llm import build_chat_model
from app.services.nodes._override import with_system_override

# 单场对比的配对上限：每侧至多 4 门奇术，两两配对最坏 16 对，按上限截断控制成本
MAX_ABILITY_PAIRS = 10


class PairVerdict(BaseModel):
    """单对奇术的对比判定。"""

    ability_a: str = Field(description="奇术 A 的名称")
    ability_b: str = Field(description="奇术 B 的名称")
    conflict: bool = Field(description="两门奇术是否存在矛与盾式碰撞（攻击×防御、信息×遮掩、施加×抵消等直接对抗）")
    interaction: str = Field(default="", description="碰撞类型一句话简述（如「攻击×防御」）；无冲突时为空字符串")
    winner: Literal["A", "B", "none"] = Field(
        default="none",
        description="冲突时依三相力量之和占上风的一侧（A/B 为对家一侧）；不相上下或无冲突为 none",
    )
    reasoning: str = Field(default="", description="依三相共鸣理论简要说明三相力量对比与结论")


PAIR_JUDGE_SYSTEM_PROMPT = """你是论战分析师，负责在战斗推演前对**两门指定奇术**做针对性对比判定。你只输出结构化判定，不输出任何叙述。

核心世界观公理（三相共鸣理论）：
本对战世界不存在「优先级/判定级」，所有奇术初始权重完全均等且有限。奇术效果强弱取决于它与现实世界的「交互信息量」大小，由三个环节体现：
- 【契相】奇术生效前的前置限制：前置条件、作用对象、目标媒介、效果自身限制等越严苛，契相之力越大；没有任何限制则无契相之力。
- 【显相】奇术生效中从发动到达成愿望的过程可解释性：效果「凭空发生」、缺乏路径则无显相之力；能构建完整、可解释、与现实世界交互的中间过程则显相之力大。
- 【果相】奇术生效后施术者强制承受的代价与反噬：代价越严重果相之力越大。严禁接受超出「本场对决时间跨度」的虚假代价（如「牺牲五十年寿命」「三天后暴毙」一律计 0 代价）。
三相力量之和越大，奇术效果越强；三相皆不满足则效果被削弱至近乎为零。

判定任务：
1. 判断两门奇术是否存在【矛与盾式碰撞】——攻击与防御、获取信息与遮掩信息、施加效果与抵消效果等直接相互对抗的关系。不存在直接对抗则 conflict=false。
2. 若存在碰撞，依三相共鸣理论分别评估两门奇术的三相力量之和，力量大者占上风；winner 填占上风的一侧（A 指第一门奇术所属方，B 指第二门奇术所属方）；不相上下填 none。
3. interaction 用一句话概括碰撞类型；无冲突时为空字符串。

规则：
- 禁止随意揣测、拓展能力设定中没有的能力或效果。
- 只比较给定的这两门奇术，忽略双方其他奇术与战术。"""

PAIR_JUDGE_USER_MSG = (
    "【双方信息（仅作背景，比较对象是下面这两门奇术）】\n{info}\n\n"
    "【奇术 A】\n{ability_a}\n\n"
    "【奇术 B】\n{ability_b}\n\n"
    "请按系统提示中的三相共鸣理论，判定这两门奇术是否存在冲突效果；若有，依三相力量之和分判高下。"
)

PAIR_JUDGE_TEMPLATE = ChatPromptTemplate.from_messages(
    [
        ("system", PAIR_JUDGE_SYSTEM_PROMPT),
        ("user", PAIR_JUDGE_USER_MSG),
    ]
)


def _render_pair_ability(a) -> str:
    """单门奇术渲染为对比输入文本（有值才附详细解释/因果槽位）。"""
    lines = [f"- {a.name}：{a.effect}"]
    if getattr(a, "detail", None):
        lines.append(f"  详细解释：{a.detail}")
    if getattr(a, "understanding", None):
        lines.append(f"  因果槽位：{a.understanding}")
    return "\n".join(lines)


def build_pair_judge_chain(llm_config: dict | None = None, system_prompt: str | None = None) -> Runnable:
    """单对奇术对比链：结构化输出 PairVerdict（method="function_calling"）。

    system_prompt 非空时以它覆盖对比系统指令（提示词方案调试用，须保留 {info}/{ability_a}
    /{ability_b} 数据槽）；None 用冻结默认，生产行为不变。
    """
    template = with_system_override(PAIR_JUDGE_TEMPLATE, system_prompt)
    return template | build_chat_model(
        thinking=False, max_tokens=512, temperature=0, llm_config=llm_config
    ).with_structured_output(PairVerdict, method="function_calling")


def render_pair_report(verdicts: list[PairVerdict]) -> str:
    """把逐对判定汇总为对比报告文本，供推演节点读取。"""
    if not verdicts:
        return ""
    lines = ["【奇术对比分析】"]
    winner_text = {"A": "A 侧占优", "B": "B 侧占优", "none": "不相上下"}
    for v in verdicts:
        if v.conflict:
            detail = f"依三相共鸣理论，{winner_text.get(v.winner, '不相上下')}。"
            if v.reasoning:
                detail += v.reasoning
            lines.append(f"- {v.ability_a} × {v.ability_b}：冲突（{v.interaction or '矛与盾式碰撞'}），{detail}")
        else:
            lines.append(f"- {v.ability_a} × {v.ability_b}：无直接冲突。")
    return "\n".join(lines)
