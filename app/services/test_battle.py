"""后台对战试验场服务层：纯测试对战与猜词，对玩家数据零持久性影响。

复刻 battle.py 的推演/猜词编排，但落库到 test_* 表、结算只作用于 TestUser——
绝不写入 battles / battle_guesses / users，不触发玩家 Elo/见闻，不落行迹 md。

- run_test_deduction：真实一次性推演（复用 run_deduction），SSE 事件进本地收集器，不发布到全局总线。
- resolve_test_battle：结算一场测试对战（写 TestBattle + TestBattleGuess + TestUser 名望）。
- submit_test_guess：复用 guess.py 共享猜词管道（点评），只更新 TestBattle/TestBattleGuess。
- verify_test_guess：复用 guess.py 检定管道（独立检定），只更新 TestBattle/TestBattleGuess。

指定胜负（skip）无战斗叙述时，猜词判定默认赢家全部奇术都被使用（不走 usage 节点）。
"""

from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.db.base import async_session_factory
from app.models.ability import Ability
from app.models.test_battle import TestBattle, TestBattleGuess, TestUser
from app.services import economy
from app.services.deduction import run_deduction
from app.services.guess import GUESS_ATTEMPTS_MAX, run_guess_commentary, run_guess_verification
from app.services.nodes.discusser import build_discuss_llm
from app.services.nodes.guess_matcher import build_guess_commentary_llm, build_guess_verify_llm
from app.services.nodes.usage_judge import USAGE_TEMPLATE, build_usage_llm
from app.services.reliability import ainvoke_with_reliability

logger = get_logger("test_battle")

# 猜词规则（GUESS_ATTEMPTS_MAX / VERIFY_FAIL_MISSING）在 app.services.guess 统一维护

class _EventCollector:
    """本地 SSE 事件收集器：run_deduction 只 publish 到这里，不触碰全局事件总线。"""

    def __init__(self) -> None:
        self.events: list[dict] = []

    async def publish(self, event: dict) -> None:
        self.events.append(event)

    async def close(self) -> None:
        pass


def _ability_dict(a: Ability) -> dict:
    return {"name": a.name, "effect": a.effect}


async def run_test_deduction(
    *,
    user_a: TestUser,
    user_b: TestUser,
    fighter_a: str,
    fighter_b: str,
    abilities_a: list[Ability],
    abilities_b: list[Ability],
    style_a: str = "",
    style_b: str = "",
    trace_context: dict | None = None,
) -> tuple[str, str, str, str, int | None, str]:
    """真实一次性推演一场测试对战，返回 (god, narration_a, narration_b, winner_side, winner_id, discuss_report)。"""
    collector = _EventCollector()
    r = await run_deduction(
        stream=collector,
        user_a=user_a,
        user_b=user_b,
        fighter_a=fighter_a,
        fighter_b=fighter_b,
        abilities_a=abilities_a,
        abilities_b=abilities_b,
        tactic_a="",
        tactic_b="",
        style_a=style_a,
        style_b=style_b,
        build_discuss=build_discuss_llm,
        trace_context=trace_context,
    )
    return r.god, r.narration_a, r.narration_b, r.winner_side, r.winner_id, r.discuss_report


async def generate_test_discuss_report(
    *,
    fighter_a: str,
    fighter_b: str,
    abilities_a: list[Ability],
    abilities_b: list[Ability],
    style_a: str = "",
    style_b: str = "",
) -> str:
    """仅生成战前讨论报告（不推演、不落库）：复用讨论节点与推演同一套 info 组装。

    讨论失败抛异常，由路由转成可读错误（报告是主动操作，失败要显式告知，不做静默降级）。
    """
    from app.services.deduction import _combat_info

    info = _combat_info(
        fighter_a, fighter_b, abilities_a, abilities_b,
        tactic_a="", tactic_b="", style_a=style_a, style_b=style_b,
    )
    return str(
        await ainvoke_with_reliability(
            build_discuss_llm(),
            {"info": info},
            operation="discuss",
            trace_context={"kind": "test_report"},
        )
    )


async def _build_test_guess(
    db: AsyncSession,
    battle: TestBattle,
    winner_name: str,
    winner_abilities: list[Ability],
    god_narration: str,
    *,
    all_used: bool,
) -> None:
    """生成测试猜词行：有叙述时用 usage 节点判定实际使用子集，无叙述（skip）默认全部奇术。

    不单独 commit：与 battle.status="done" 同事务落库。
    """
    if all_used or not god_narration:
        used = [_ability_dict(a) for a in winner_abilities]
    else:
        abilities_txt = "\n".join(f"{i + 1}. {a.name}：{a.effect}" for i, a in enumerate(winner_abilities))
        try:
            out = await ainvoke_with_reliability(
                build_usage_llm(),
                USAGE_TEMPLATE.format_messages(
                    winner_name=winner_name,
                    abilities=abilities_txt,
                    narration=god_narration,
                ),
                operation="usage",
                trace_context={"kind": "test_guess", "trace_id": str(battle.id)},
            )
            indices = sorted({i for i in out.indices if 1 <= i <= len(winner_abilities)})
        except Exception:  # noqa: BLE001 - 可靠性层已记异常日志；降级为全部装配
            logger.warning("test_usage_fallback battle_id=%d", battle.id)
            indices = []
        if not indices:
            indices = list(range(1, len(winner_abilities) + 1))
        used = [_ability_dict(winner_abilities[i - 1]) for i in indices]
    db.add(
        TestBattleGuess(
            battle_id=battle.id,
            used_abilities=used,
            cards=[
                {"cracked": False, "cracked_round": None, "missing": None, "verifies": []}
                for _ in used
            ],
            attempts_max=GUESS_ATTEMPTS_MAX,
        )
    )


async def _settle_test_battle(
    db: AsyncSession,
    battle: TestBattle,
    user_a: TestUser,
    user_b: TestUser,
    abilities_a: list[Ability],
    abilities_b: list[Ability],
    winner_side: str,
    narration_text: str,
    *,
    narration_a: str = "",
    narration_b: str = "",
    discuss_report: str = "",
) -> None:
    """结算核心：写 story、TestUser 名望 Elo、winner/guess_by、猜词行。

    narration_text 为上帝视角（推演产出，skip 时为空串）；narration_a/b 为双方视角，
    缺省回退上帝视角（skip 时双视角同为空）。discuss_report 为战前讨论报告（skip 时为空）。
    """
    a_score = 1.0 if winner_side == "A" else (0.0 if winner_side == "B" else 0.5)
    rank_da, rank_db = economy.elo_update(user_a.rank_points, user_b.rank_points, a_score)
    user_a.rank_points += rank_da
    user_b.rank_points += rank_db
    battle.rank_delta_a, battle.rank_delta_b = rank_da, rank_db

    if winner_side == "A":
        battle.winner_id, winner_name = user_a.id, battle.loadout_a_name
        winner_abilities, loser_id = abilities_a, user_b.id
    elif winner_side == "B":
        battle.winner_id, winner_name = user_b.id, battle.loadout_b_name
        winner_abilities, loser_id = abilities_b, user_a.id
    else:
        winner_name, winner_abilities, loser_id = "和局", [], None
    battle.guess_by = loser_id

    battle.story = json.dumps(
        {
            "narration": narration_text,  # 上帝视角（skip 时为空：测试工具仅需猜词结果，不展示叙述）
            "narration_a": narration_a or narration_text,  # 甲视角（回退上帝）
            "narration_b": narration_b or narration_text,  # 乙视角（回退上帝）
            "discuss_report": discuss_report,  # 战前讨论报告（skip 时为空）
            "result": winner_name,
            "abilities_a": [_ability_dict(a) for a in abilities_a],
            "abilities_b": [_ability_dict(a) for a in abilities_b],
        },
        ensure_ascii=False,
    )
    # 和局无败方，不建猜词行
    if loser_id is not None:
        await _build_test_guess(
            db, battle, winner_name, winner_abilities, narration_text, all_used=not narration_text
        )


async def resolve_test_battle(
    db: AsyncSession,
    *,
    user_a: TestUser,
    user_b: TestUser,
    fighter_a: str,
    fighter_b: str,
    abilities_a: list[Ability],
    abilities_b: list[Ability],
    winner_side: str,
    narration_text: str = "",
) -> TestBattle:
    """指定胜负直接落库（skip）：零 LLM，创建 TestBattle 并结算。"""
    battle = TestBattle(
        user_a_id=user_a.id,
        user_b_id=user_b.id,
        status="done",
        story="",
        loadout_a_name=fighter_a,
        loadout_b_name=fighter_b,
    )
    db.add(battle)
    await db.flush()
    await _settle_test_battle(db, battle, user_a, user_b, abilities_a, abilities_b, winner_side, narration_text)
    await db.commit()
    await db.refresh(battle)
    return battle


async def resolve_test_battle_from_deduction(
    battle_id: int,
    *,
    ability_ids_a: list[str],
    ability_ids_b: list[str],
    style_a: str,
    style_b: str,
) -> None:
    """后台真实推演结算：独立会话（随任务上下文关闭），加载 TestBattle → 读奇术 → 真实推演 → 结算落库。"""
    async with async_session_factory() as db:
        await _resolve_test_battle_from_deduction(
            db, battle_id,
            ability_ids_a=ability_ids_a,
            ability_ids_b=ability_ids_b,
            style_a=style_a,
            style_b=style_b,
        )


async def _resolve_test_battle_from_deduction(
    db: AsyncSession,
    battle_id: int,
    *,
    ability_ids_a: list[str],
    ability_ids_b: list[str],
    style_a: str,
    style_b: str,
) -> None:
    battle = await db.get(TestBattle, battle_id)
    if battle is None:
        return
    user_a = await db.get(TestUser, battle.user_a_id)
    user_b = await db.get(TestUser, battle.user_b_id)
    if user_a is None or user_b is None:
        battle.status = "failed"
        await db.commit()
        return
    abilities_a = [a for a in [await db.get(Ability, aid) for aid in ability_ids_a] if a is not None]
    abilities_b = [a for a in [await db.get(Ability, aid) for aid in ability_ids_b] if a is not None]
    if not abilities_a or not abilities_b:
        battle.status = "failed"
        battle.story = json.dumps({"error_message": "奇术缺失，测试推演失败"}, ensure_ascii=False)
        await db.commit()
        return
    try:
        god, nar_a, nar_b, winner_side, _, discuss_report = await run_test_deduction(
            user_a=user_a,
            user_b=user_b,
            fighter_a=battle.loadout_a_name,
            fighter_b=battle.loadout_b_name,
            abilities_a=abilities_a,
            abilities_b=abilities_b,
            style_a=style_a,
            style_b=style_b,
            trace_context={"kind": "test_battle", "trace_id": str(battle.id)},
        )
    except Exception:  # noqa: BLE001 - 推演重试耗尽/异常：标记 failed
        logger.error("test_battle_failed id=%d", battle_id)
        battle.status = "failed"
        battle.story = json.dumps({"error_message": "铺陈中途失联，测试推演失败。"}, ensure_ascii=False)
        await db.commit()
        return
    await _settle_test_battle(
        db, battle, user_a, user_b, abilities_a, abilities_b, winner_side, god,
        narration_a=nar_a, narration_b=nar_b, discuss_report=discuss_report,
    )
    battle.status = "done"
    await db.commit()


async def submit_test_guess(db: AsyncSession, battle: TestBattle, guesser: TestUser, text: str) -> None:
    """败方猜对家奇术（测试域）：点评一次（只追加猜测/点评、消耗机会，不改看破状态）。

    全破 / 次数耗尽在检定中处理；本函数只负责点评。失败时异常上抛由路由转成可读错误。
    """
    if battle.status != "done":
        raise ValueError("对决尚未完成")
    if battle.guess_by != guesser.id:
        raise ValueError("只有战败方可以猜奇术")
    guess = await db.get(TestBattleGuess, battle.id)
    if guess is None or not guess.used_abilities:
        raise ValueError("本场无奇术可猜")
    if battle.guess_state == "done":
        raise ValueError("猜测已结束")
    if guess.attempts_used >= guess.attempts_max:
        raise ValueError("猜测次数已用完")
    text = text.strip()
    if not text:
        raise ValueError("猜测不能为空")

    commentary = await run_guess_commentary(
        text=text,
        abilities=guess.used_abilities,  # 参考基准 = 对家实际使用的奇术（真名只在服务端作判定依据）
        cards=[dict(c) for c in guess.cards],
        trace_context={"kind": "test_guess", "trace_id": str(battle.id)},
        build_commentary=build_guess_commentary_llm,
    )
    guess.guess_history = list(guess.guess_history or []) + [text]
    guess.comments = list(guess.comments or []) + [commentary]
    guess.attempts_used += 1
    battle.guess_state = "guessing"

    if guess.attempts_used >= guess.attempts_max:
        # 次数耗尽未全破：测试工具直接揭示（便于检验全流程）
        battle.guess_state = "done"
        battle.guess_hit = False
        battle.revealed = True
    else:
        battle.guess_hit = None

    await db.commit()


async def verify_test_guess(db: AsyncSession, battle: TestBattle, guesser: TestUser) -> None:
    """主动检定对家奇术（测试域）：对未看破卡并发检定，更新逐卡看破/还缺什么并重算 score。

    检定不追加聊天记录；可反复发起，但须自上次检定后又有新点评（can_verify 判据）。
    全破 → 测试域内胜负逆转 + 名望重算；次数耗尽 → 直接揭示（测试工具便于检验全流程）。
    """
    if battle.status != "done":
        raise ValueError("对决尚未完成")
    if battle.guess_by != guesser.id:
        raise ValueError("只有战败方可以猜奇术")
    guess = await db.get(TestBattleGuess, battle.id)
    if guess is None or not guess.used_abilities:
        raise ValueError("本场无奇术可猜")
    if battle.guess_state == "done":
        raise ValueError("猜测已结束")
    if guess.attempts_used >= guess.attempts_max:
        raise ValueError("猜测次数已用完")
    if len(guess.comments or []) <= (guess.verified_round or 0):
        raise ValueError("尚无新的猜测进展，暂不可检定")

    round_no = len(guess.comments or [])
    cards = await run_guess_verification(
        history=list(guess.guess_history or []),
        comments=list(guess.comments or []),
        abilities=guess.used_abilities,
        cards=[dict(c) for c in guess.cards],
        round_no=round_no,
        trace_context={"kind": "test_guess", "trace_id": str(battle.id)},
        build_verify=build_guess_verify_llm,
    )
    guess.cards = cards
    guess.verified_round = round_no
    guess.attempts_used += 1

    cracked = sum(1 for c in cards if c["cracked"])
    battle.guess_score = cracked / len(cards) if cards else 0.0
    if cracked == len(cards):
        # 全破逆转：测试域内重算名望（回滚原结算，按逆转方向重算）
        battle.guess_state = "done"
        guess.flipped = True
        battle.guess_hit = True
        battle.guess_score = 1.0
        battle.winner_id = guesser.id
        user_a = await db.get(TestUser, battle.user_a_id)
        user_b = await db.get(TestUser, battle.user_b_id)
        if user_a is not None and user_b is not None:
            user_a.rank_points -= battle.rank_delta_a
            user_b.rank_points -= battle.rank_delta_b
            a_score = 1.0 if guesser.id == battle.user_a_id else 0.0
            delta_a, delta_b = economy.elo_update(user_a.rank_points, user_b.rank_points, a_score)
            user_a.rank_points += delta_a
            user_b.rank_points += delta_b
            battle.rank_delta_a, battle.rank_delta_b = delta_a, delta_b
        battle.revealed = True
    elif guess.attempts_used >= guess.attempts_max:
        # 次数耗尽未全破：测试工具直接揭示（便于检验全流程）
        battle.guess_state = "done"
        battle.guess_hit = False
        battle.revealed = True
    else:
        battle.guess_hit = None

    await db.commit()
