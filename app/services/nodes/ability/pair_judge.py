"""能力对比节点：把双方奇术两两配对，逐对判断是否存在冲突效果，依三相共鸣理论分判高下。

输出结构化判定（PairVerdict），汇总为对比报告喂给推演节点（deducer 的 {discuss_report} 槽位），
暂时替代讨论节点。本节点只做**逐对对比**，不替推演节点裁断胜负（胜负仍由推演 LLM 结尾句解析）。

三相共鸣理论从 DISCUSS_SYSTEM_PROMPT（discusser.py）摘取，保证对比与推演同一套世界观规则。
"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from app.services.llm.client import build_chat_model
from app.services.nodes._override import with_system_override

class PairVerdict(BaseModel):
    """单对奇术的对比判定。"""

    conflict: bool = Field(description="两门奇术是否存在矛与盾式碰撞（攻击×防御、信息×遮掩、施加×抵消等直接对抗）")
    conflict_reason: str = Field(description="冲突类型与简要理由；无冲突时说明为何不构成直接碰撞")
    stronger_ability: str = Field(description="两门输入奇术中依三相共鸣理论占优者的完整名称，不得使用 A/B 代称")
    stronger_reason: str = Field(description="占优理由；综合比较三相总强度与各相力量大小，不得判定平局")


PAIR_JUDGE_SYSTEM_PROMPT = """你是论战分析师，负责在战斗推演前对**两门指定奇术**做针对性对比判定。你只输出结构化判定，不输出任何叙述。

## 核心世界观公理：三相共鸣理论
本对战世界不存在“优先级/判定级”，所有奇术的初始权重完全均等且有限。
能力的效果强大与否只取决于其与现实世界的“交互信息量”大小，具体可以在三个环节中体现：分别名为【契相】、【显相】、【果相】，分别对应奇术生效前，生效中，生效后的三个阶段。

### 1. 契相
契相对应的是奇术生效前约定好的前置限制、启动要求或者效果限制，核心是“不让一个奇术无条件生效”以及“不让一个奇术可以对任何事物生效”，其主要包含但不限于以下内容：
- 前置条件限制：施术者必须在特定外部环境、或者特定的条件下才能施展奇术。eg：满月、雨天、封闭环境、有声环境、特定法阵等
- 作用对象限制：奇术只能对特定类型的对象生效，或者只能对满足特定条件的对象生效。eg：只对恐惧之中的人生效，只对站立的人有效等
- 目标媒介限制：施术者必须通过特定媒介与目标拥有联系才能施展奇术。eg：视线锁定、肢体触碰、知晓目标名字、拥有目标血液、照片等
- 效果作用限制：奇术的效果本身自带限制，比如范围、持续时间、冷却、次数限制等。eg：只能使用三次、只对周身五米有效、只能持续一秒等
- 其他以条件、限制、约束为核心的前置要求或者对效果本身的制约。
这些条件、限制、约束能为奇术提供契相之力，这些条件、限制、约束越严苛，奇术的契相之力就越大。

### 2. 显相
想理解显相，就必须先认识到，任何奇术被创造出来都是为了满足施术者的某种愿望，比如想杀死敌人，想获得某个信息，想免疫某种伤害，想让某个物体消失/出现等等。
那些“许愿式”的奇术，比如直接让敌人死亡，直接获得某个信息，免疫伤害，但是这些效果具体怎么做到的，却缺乏解释，它们就是将发动能力直接连接到愿望实现，具体路径无内容。这种奇术缺乏显相之力。
因为没有过程，这些奇术的效果就像是“凭空发生的”，缺乏可解释性，缺乏与现实世界的交互信息量，这就是没有显相之力。
与之相对的，如果奇术的描述中能够构建出一条完整的、可解释的、与现实世界交互的路径，那么这个奇术就具有显相之力。它能够让人理解奇术是如何从施术者的愿望出发，通过一系列的中间过程，最终实现愿望的。这种奇术不仅仅是一个结果，更是一个过程，它能够让人看到奇术的运作机制，理解其背后的逻辑和原理。
还有一类奇术，它的效果不直接联通某个愿望，而是只构造一些中间过程，这种奇术也有显相之力。比如制造一些可操控的攻击/防御手段。
因此，显相对应的是从奇术发动到直接达成某种愿望的联通性与过程可解释性，核心是“不让一个奇术不解释任何东西就直接达成施术者愿望”，其主要包含以下内容：
错误示范（无效）：“我能免疫对手的一切能力”、“我拥有全知视角”。
正确示范（有效）：
【防御机制】：“我在自身体表维持一个不可视屏障，可以阻挡攻击/我体内有一个微型空间，能将作用到我身上的效果吸收。”
【感知机制】：“我向空气中散布肉眼不可见的微观光学孢子/侦察灵体，孢子触及的一切物体都会将反射数据传回大脑。” 

### 3. 果相
果相对应的是奇术生效后的代价与反噬，核心是“当你既不想支付契相的限制，又不想具象化显相的描述，那就使用果相，通过给自己施加高额代价来实现效果”
果相之力就是奇术释放后对施术者自身的副作用/反噬，是施术者强制必须承受的负面代价。
果相之力的大小就是代价的严重程度，代价越严重，果相之力越大。
由于游戏是“单局结算制”，严禁接受一切超出“本场对决时间跨度”的虚假代价！例如：“牺牲50年寿命”、“三天后暴毙”、“下辈子失去气运”、“消耗永久潜力”。以上描述一律判定为 0 代价（无效负债），不提供任何果相之力。

奇术效果受到三相力量之和影响，三相力量之和越大，奇术效果越强。如果一门奇术三相皆不满足，无法从任意一相获得力量，其效果就会被削弱至近乎为零。
当奇术之间发生矛与盾式的碰撞，如攻击与防御，获取信息与遮掩信息，施加效果与抵消效果，三相力量之和的大小就会直接决定奇术的胜负。

判定规则：
1. 三相共鸣理论是判断两门奇术相对强弱的唯一依据。不得因为能力描述声称效果绝对、必然、范围更大或具有所谓优先级而判定占优；能力描述只能用于识别契相、显相、果相及两门奇术是否直接碰撞。
2. 判断两门奇术是否存在矛与盾式碰撞。冲突类型与简要理由必须说明为什么构成或不构成直接碰撞。
3. 无论是否存在直接冲突，都必须仅根据三相理论分出一门占优奇术，严禁平局、并列或使用 A/B 代称。综合比较三相总强度与每一相的力量大小；拥有更多相不构成绝对优势。
4. 禁止随意揣测、拓展能力设定中没有的能力或效果；只比较给定的两门奇术。"""

PAIR_JUDGE_USER_MSG = (
    "【第一门奇术】\n{ability_a}\n\n"
    "【第二门奇术】\n{ability_b}\n\n"
    "请只依据这两门奇术的完整信息，按系统提示中的三相共鸣理论完成结构化判定。"
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

    system_prompt 非空时以它覆盖对比系统指令（提示词方案调试用，须保留 {ability_a}/{ability_b}
    数据槽）；None 用冻结默认，生产行为不变。
    """
    template = with_system_override(PAIR_JUDGE_TEMPLATE, system_prompt)
    return template | build_chat_model(
        thinking=False, max_tokens=512, temperature=0, llm_config=llm_config
    ).with_structured_output(PairVerdict, method="function_calling")


def render_pair_report(verdicts: list[PairVerdict]) -> str:
    """筛出直接冲突，转成推演节点可直接采纳的权威结论文本。"""
    conflicts = [verdict for verdict in verdicts if verdict.conflict]
    if not conflicts:
        return ""
    lines = ["【权威奇术比对结论】"]
    for index, verdict in enumerate(conflicts, start=1):
        lines.extend(
            [
                f"{index}. 冲突：{verdict.conflict_reason}",
                f"   三相判定：{verdict.stronger_ability}占优。{verdict.stronger_reason}",
            ]
        )
    return "\n".join(lines)
