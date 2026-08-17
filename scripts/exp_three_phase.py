"""三相槽位实验副本：收紧【槽位输出指令】判定规则，与线上原提示词输出对比。

理论部分（三相共鸣理论）从冻结的 UNDERSTANDING_SYSTEM_PROMPT 逐字复用，只替换槽位输出指令。
结构化输出模型 AbilitySlot 与字段描述完全不变（同 build_understanding_chain）。

用法：uv run python scripts/exp_three_phase.py [奇术名...]
不传参则跑内置标志性奇术集。
"""

import asyncio
import sys

from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy import select

from app.db.base import async_session_factory
from app.models.ability import Ability
from app.services.ability_understanding import (
    UNDERSTANDING_SYSTEM_PROMPT,
    AbilitySlot,
)
from app.services.llm import build_chat_model

_NEW_OUTPUT_INSTRUCTIONS = """【槽位输出指令】
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

# 理论部分逐字复用冻结提示词，仅替换输出指令
UNDERSTANDING_SYSTEM_PROMPT_EXP = (
    UNDERSTANDING_SYSTEM_PROMPT.split("【槽位输出指令】")[0] + _NEW_OUTPUT_INSTRUCTIONS
)

UNDERSTANDING_TEMPLATE_EXP = ChatPromptTemplate.from_messages(
    [
        ("system", UNDERSTANDING_SYSTEM_PROMPT_EXP),
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


def build_understanding_chain_exp():
    return build_chat_model(thinking=False, temperature=0.0).with_structured_output(
        AbilitySlot, method="function_calling"
    )


ICONIC = [
    # 愿望式 → 期望 mid=false
    "王选先手",  # 全知+先手（理论明确列为无效示范）
    "超强感知",  # 复述式
    "胜负公理",  # 元叙事编造机制
    "坐忘",  # 元叙事编造
    "天堂制造",  # 愿望式 + 编造隐含代价
    "不灭之握",  # 接触=契相，死亡=愿望式 → 期望 pre=true mid=false
    "全知",  # 看到敌人时=契相，知悉=愿望式 → 期望 pre=true mid=false
    "封绝",  # 意念锁定=契相，封禁=愿望式 → 期望 pre=true mid=false
    # 果相真实代价 → 期望 post=true 保留
    "免疫伤害",  # 24h后死亡
    "复活",  # 生命上限减半
    "九歌",  # 九瞬不分胜负双方死亡
    "瞬时之枪",  # 长枪销毁
    "现实锚定器",  # 怀表失效
    # 果相误判 → 期望 post=false
    "欺骗",  # 敌人死亡≠施术者代价
    "十二荣光",  # 收益≠果相
    "万象归墟",  # 机制真，但 post 是编造 → 期望 mid=true post=false
]


def _f(slot: AbilitySlot | None, part: str) -> str:
    if slot is None:
        return "<无>"
    p = getattr(slot, part)
    return (p.text or "")[:64] if p else ""


async def main() -> None:
    names = sys.argv[1:] or ICONIC
    async with async_session_factory() as db:
        rows = (
            await db.execute(
                select(Ability.name, Ability.effect, Ability.detail, Ability.understanding).where(
                    Ability.name.in_(names)
                )
            )
        ).all()
    chain = build_understanding_chain_exp()
    for name, effect, detail, orig in rows:
        try:
            orig_slot = AbilitySlot.model_validate_json(orig)
        except Exception:  # noqa: BLE001 - 实验脚本，存量解析失败按空槽位处理
            orig_slot = None
        msgs = UNDERSTANDING_TEMPLATE_EXP.format_messages(name=name, effect=effect, detail=detail)
        try:
            out = await asyncio.wait_for(chain.ainvoke(msgs), timeout=90)
        except Exception as e:  # noqa: BLE001 - 实验脚本，单条失败不中断
            print(f"=== {name} === 调用失败: {type(e).__name__}: {str(e)[:80]}")
            continue
        print(f"=== {name} ===")
        print(f"  effect: {effect[:64]}")
        if orig_slot:
            print(
                f"  原: pre={orig_slot.pre.present} mid={orig_slot.mid.present} "
                f"post={orig_slot.post.present} src={orig_slot.verdict.source_phases}"
            )
            print(f"      原mid  : {_f(orig_slot, 'mid')}")
            print(f"      原post : {_f(orig_slot, 'post')}")
        print(
            f"  exp: pre={out.pre.present} mid={out.mid.present} post={out.post.present} "
            f"src={out.verdict.source_phases}"
        )
        print(f"      expmid : {_f(out, 'mid')}")
        print(f"      exppost: {_f(out, 'post')}")


if __name__ == "__main__":
    asyncio.run(main())
