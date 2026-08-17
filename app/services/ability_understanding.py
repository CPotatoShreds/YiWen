"""奇术因果槽位：保存奇术后后台异步按「时序三相因果守恒律」忠实解析为结构化 JSON 槽位。

复用 `Ability.understanding` 字段（曾弃用，现重新启用）。槽位完全忠实于异闻师写下的效果
与详细解释，把用户描述的启动前置 / 运作机制 / 代价反噬归位到契相 / 显相 / 果相，判定是否「零相
空想」，作为推演对战的主要依据。推演 `deduction._render_ability` 读取 understanding 喂给
讨论 / 推演节点。保存后由路由后台触发，失败静默（不阻塞奇术保存，推演时退回原始字段）。
"""

import json
from contextlib import suppress

from cryptography.fernet import InvalidToken
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db.base import async_session_factory
from app.models.ability import Ability
from app.models.llm_profile import LlmProfile
from app.models.user import User
from app.models.user_ability import UserAbility
from app.services.llm import build_chat_model, profile_to_llm_config
from app.services.reliability import ainvoke_with_reliability


class Phase(BaseModel):
    """某一因果相：该相对价内容（完全忠实引述用户文本）。"""

    present: bool = Field(description="该因果相是否存在（契相/显相/果相）")
    text: str = Field(
        default="",
        description="该相对价的具体内容：完全忠实于用户所写的内容中涉及的启动前置/运作机制/代价反噬，将与该相对应的内容表达出来；用户没写则为空字符串。",
    )


class SlotVerdict(BaseModel):
    """因果槽位判定：力量来源相、是否零相空想、一句话定位与推演执行要点。"""

    zero_phase: bool = Field(description="三相全无（无启动前置、无运作机制解释、无代价反噬）时为 true")
    source_phases: list[str] = Field(description="力量来源相，取值 pre / mid / post，可多个")
    summary: str = Field(
        description="一句话总结该奇术在时序三相律下的定位与推演执行要点"
        "（如：力量来自契相对价，推演须把启动难度作为核心冲突描写；零相空想则注明威力稀释为微效）忠实于用户原文，不引入原文没有的内容，不擅自对原文做进一步阐述。"
    )


class AbilitySlot(BaseModel):
    """奇术的时序三相因果槽位（结构化 JSON，作为后续推演对战的主要依据）。"""

    verdict: SlotVerdict
    pre: Phase  # 契相 · 启动前置（输入端对价）
    mid: Phase  # 显相 · 过程与机理解释（传输端对价）
    post: Phase  # 果相 · 代价反噬（结算端对价）


UNDERSTANDING_SYSTEM_PROMPT = """

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


【槽位输出指令】
基于上述三相理论，把异闻师写下的奇术「效果」与「详细解释」（如有）忠实解析为一个 JSON 槽位。
判定时先分清三层：**效果是什么**（愿望/结果）≠ **怎么做到**（机制/How）≠ **施术者付什么**（代价）。
判定完成后**只输出 JSON 槽位本身，严禁输出任何判定过程、自检理由或文字说明**。

■ 逐相判定程序（仅在脑中自检，不写入输出）：
**契相（pre）**：原文是否写明「施术者必须满足某项条件/限制/约束才能发动或生效」？
　施术条件（满月/雨天/封闭环境/特定法阵/特定状态…）、作用对象限制（只对恐惧中的人/只对站立的人…）、
　目标媒介要求（视线锁定/肢体触碰/知晓名字/拥有血液照片/携带特定道具…）、效果自带限制（只能三次/只能持续一秒/有冷却…）。
　→ 有则 present=true，text 引用原文的限制表述；没有则 false。泛泛的「对敌人」「对目标」「战斗开始时」不是契相。

**显相（mid）**：原文是否写明「从发动到生效的具体过程/路径（How）——通过什么手段、怎么一步步干涉现实生效」？
　只写了结果/效果（敌人死亡、获得信息、免疫伤害、封禁对方奇术、无效化对方能力、必定命中、先手预知…）→ 愿望式，present=false。
　复述能力本身（感知力强、看破弱点、知悉情报、洞悉一切、全知视角、直觉感知、高速再生、时间停滞…）→ 不是 How，present=false。
　感知/知晓/洞悉/预知类措辞只描述了「能力让我知道/看到什么」，没有写「怎么实现」，一律 present=false；不得套用「感知机制」范例。
　解释里用「原理是…」「因果层面…」「机制上…」补出的套话，只要没有具体手段或路径，仍是伪机制 → present=false。
　原文写了真实过程/路径（维持屏障、散布光学孢子、释放干扰波、构造实体/力场、经媒介传导…）→ present=true。
　text 只写原文明确写出的过程；无过程则留空。

**果相（post）**：原文是否写明「施术者本人必须承受的负面代价/副作用/反噬/双刃剑」？
　敌人死亡/敌人被削弱/环境改变/地质剧变/对方遭殃 → 作用于对方或环境的后果，不是施术者代价，false。
　自身收益/属性（绝对免疫、不可被无效化、不可被复制观测、十二次复活机会…）→ 不是果相，false。
　「复活」本身不是果相；只有写明真实代价（每次复活生命上限减半、自毁、重伤、能力反噬）才是。
　一次性道具/媒介在发动后损毁或失效（长枪销毁、怀表失效、祭品消耗）→ 施术者的资源代价，present=true。
　原文没写代价 → false，禁止编造「隐含代价」。
　超出本场时间跨度的虚假代价（牺牲50年寿命/三天后暴毙/消耗永久潜力）→ 无效负债，false。

■ 判定范例（对齐判定口径；仅供口径参照，不照抄其措辞）：
例1「效果：我可以免疫一切伤害」→ pre=false mid=false post=false（zero_phase=true，纯许愿式）
例2「效果：接触的物体立刻死亡」→ pre=true（肢体触碰=目标媒介契相）mid=false（死亡是结果）post=false
例3「效果：我向空气中散布肉眼不可见的微观光学孢子，孢子触及的一切物体都会将反射数据传回大脑」→ pre=false mid=true（真实感知路径）post=false
例4「效果：持续24h免疫一切伤害，结束后立刻死亡」→ pre=false mid=false post=true（24h后的死亡是真实代价）
例5「效果：只能在满月之夜施展，对恐惧中的人生效，令其当场死亡」→ pre=true（满月+对象限制）mid=false（死亡是结果）post=false
例6「效果：我能看破对方的一切想法、计谋与弱点」→ pre=false mid=false post=false（知晓类，无路径无代价）
例7「效果：我对灵力的感知力远超常人，容易看破对方奇术的情报」→ pre=false mid=false post=false（复述感知力，感知能力本身≠显相机制）
例8「效果：被动获得十二次复活，复活后对上次死因绝对免疫，自身能力不可被无效化」→ pre=false mid=false post=false（纯收益属性，原文无代价；复活≠果相）
例9「效果：投掷一把附着一次性魔法的长枪，使用后长枪当场销毁」→ pre=true（以长枪为媒介）mid=false（无效化是结果）post=true（长枪销毁=施术者的道具代价）
例10「效果：我加速自己与周围非生物的时间，沧海桑田万物风化，连地质剧变都会杀死对方」→ pre=false mid=true（时间加速是运作方式）post=false（环境剧变是作用于对方/环境的后果，非施术者代价）
例11「效果：被我欺骗的人立刻死亡，此死亡效果无法被任何手段抵消」→ pre=false mid=false post=false（死亡是结果；「无法被抵消/无法被无效化」是效果的强度属性，不是施术者的代价）
例12「效果：战斗开始时我即洞悉对方全部手段与弱点并获得先手，先手权意味着因果层面我先行动；详细解释写着原理是全知视角」→ pre=false mid=false post=false（全知+先手是愿望与伪机制；即便解释用了「原理/因果层面」措辞，没有具体路径就仍非显相，泛泛的「战斗开始时」也不是契相）

1. **完全忠实于异闻师的意图**：只把异闻师明确写出的内容归位到对应相。绝不新增、推导或擅自补充效果、机制或代价；不得为了凑满某相而虚构原文没有的内容。
2. 所有 `text` 一律忠于异闻师原文表述，可理顺措辞但不得改变语义，绝不引入原文没有的内容。
3. **verdict**：`zero_phase` = 三相全无（无前置、无机制解释、无代价）时为 true；`source_phases` = 力量来源相（可多个，必须始终输出为数组）；`summary` = 一句话因果定位 + 推演执行要点（指出推演须重点描写哪个环节的限制/破绽/代价；零相空想则注明威力稀释为微效、绝不可判定致命或无敌）。"""

UNDERSTANDING_TEMPLATE = ChatPromptTemplate.from_messages(
    [
        ("system", UNDERSTANDING_SYSTEM_PROMPT),
        (
            "user",
            (
                "【奇术名目】\n{name}\n\n"
                "【奇术效果】\n{effect}\n\n"
                "【详细解释】\n{detail}"
            ),
        ),
    ]
)


def build_understanding_chain(llm_config: dict | None = None) -> Runnable:
    """奇术因果槽位生成链：结构化输出 AbilitySlot（method="function_calling"——DeepSeek 唯一可用方式）。

    temperature=0：槽位需完全忠实于异闻师原文，确定性解析，不做创意发挥。
    与 loadout_interpretation 相同：不把 UNDERSTANDING_TEMPLATE 用 `|` 拼进链，调用方用
    format_messages 生成消息后 ainvoke，保留对 build_chat_model 的桩兼容。
    """
    return build_chat_model(thinking=False, temperature=0.0, llm_config=llm_config).with_structured_output(
        AbilitySlot, method="function_calling"
    )


async def ensure_ability_understanding(ability_id: str) -> None:
    """生成并保存奇术因果槽位（紧凑 JSON 字符串）；失败静默（推演时退回原始字段）。"""
    async with async_session_factory() as db:
        ability = await db.get(Ability, ability_id)
        if ability is None or not (ability.name.strip() and ability.effect.strip()):
            return
        owner_id = (
            await db.execute(select(UserAbility.user_id).where(UserAbility.ability_id == ability_id).limit(1))
        ).scalar_one_or_none()
        owner = await db.get(User, owner_id) if owner_id is not None else None
        profile = await db.get(LlmProfile, owner.active_profile_id) if owner and owner.active_profile_id else None
        try:
            llm_config = profile_to_llm_config(profile)
        except InvalidToken:  # api_key 解密失败 → 回退默认模型（qwen）
            llm_config = None
        with suppress(Exception):  # 槽位生成失败静默（可靠性层已记日志），推演时回退原始字段
            out = await ainvoke_with_reliability(
                build_understanding_chain(llm_config=llm_config),
                UNDERSTANDING_TEMPLATE.format_messages(
                    name=ability.name,
                    effect=ability.effect,
                    detail=ability.detail,
                ),
                operation="understanding",
                trace_context={"kind": "background", "trace_id": str(ability_id)},
            )
            ability.understanding = json.dumps(out.model_dump(), ensure_ascii=False)
            await db.commit()
