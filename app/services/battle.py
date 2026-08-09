"""对决服务（生命周期编排层）：异步对决 + 败方猜奇术。

流程：POST 启程 → 立即创建 pending 记录 → 后台任务把推演委托给推演链路模块
（app.services.deduction，各 LLM 节点位于 app.services.nodes/*）→ 结算（经济 + Elo）→
落库 done。

职责边界：battle.py 只管对决记录的生命周期（创建、加载、结算、猜奇术）；"把一场仗打
出来"（随机场景 + 一次性上帝推演 + 双视角并发转写）在 deduction.py；各 LLM 角色
（推演者/转写者/猜词判定者）的提示词与链构造在 nodes/ 下各自成文件。节点构造器在
battle.py 以别名 _build_* 暴露，注入给推演链路（测试同样打桩于此）。

推演链路：推演 LLM 以开场白 + 三选一固定结尾句一次性推演完整对战（不再分轮、无独立
判定节点），胜负从结尾句解析；随后对完整上帝叙述做一次并发转写，转写 LLM 扮演各侧
奇人、以第一人称向自己的异闻师讲述战斗经历（无系统固定首尾），经校验节点逐侧定稿
（校验 → 修复一次 → 再校验 → 上帝正文兜底），流式外发到 SSE 事件总线（先推 stage
进度：dueling 对决中 → recounting 奇人回归 → segment 转写正文）；上帝视角叙述只存档
（story["narration"]），API 恒过滤不展示；行迹各看各的。推演中一律使用奇人名字
（结尾模板 / 胜负解析 / 视角身份 / 校验视角），异闻师名字不进 LLM 上下文。

奇术保密规则：对决结束前，任何一方都看不到对家的奇术表；行迹 API 与落盘
md 在看破前均不含对家奇术。结算时按「使用子集」节点判定赢家**实际使用过**的
奇术（装配的子集），败方在有限次数内逐次道出猜测：匹配片段落到对应空白卡片、
解锁猜测条，某卡进度到门槛即看破（揭示该门真实奇术），**全部看破**胜负逆转并
重算名望（分段结算：对决结束先记录一次名望变更，全破后回滚重算）；次数
耗尽未全破时是否看破由被猜方 reveal_on_miss 设置决定。
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
from contextlib import suppress

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.db.base import async_session_factory
from app.models.ability import Ability
from app.models.battle import Battle, BattleGuess
from app.models.loadout import Loadout
from app.models.user import User
from app.services import economy
from app.services.battle_stream import _get_stream
from app.services.deduction import run_deduction
from app.services.loadout_interpretation import ensure_loadout_interpretation
from app.services.loadouts import loadout_abilities, pick_battle_loadout
from app.services.matchmaking import pick_opponent
from app.services.nodes.deducer import build_deduce_chain as _build_deduce_llm
from app.services.nodes.guess_matcher import GUESS_MATCHER_TEMPLATE
from app.services.nodes.guess_matcher import build_guess_matcher_llm as _build_matcher_llm
from app.services.nodes.transcribe_validator import build_repair_chain as _build_repair_chain
from app.services.nodes.transcribe_validator import build_validate_chain as _build_validate_chain
from app.services.nodes.transcriber import build_transcribe_chain as _build_transcribe_chain
from app.services.nodes.usage_judge import USAGE_TEMPLATE
from app.services.nodes.usage_judge import build_usage_llm as _build_usage_llm
from app.services.reliability import ainvoke_with_reliability

logger = get_logger("battle")

# 持有后台任务引用，防止 asyncio 在任务完成前 GC 取消它
_background_tasks: set[asyncio.Task] = set()

# 全链路自动重试耗尽后的面向用户解释文本（说书语系）
FAIL_BATTLE_TEXT = "铺陈中途失联，行迹未能成卷，请稍后再启程。"
FAIL_GUESS_TEXT = "奇术判定失联，请稍后重试猜奇术。"

# 猜奇术规则：有限次数内逐次道出猜测，逐卡解锁猜测条；进度 ≥CRACK_THRESHOLD 即看破该卡（揭示真实奇术），全破逆转
GUESS_ATTEMPTS_MAX = 5
CRACK_THRESHOLD = 80


def _ability_dict(a: Ability) -> dict:
    """奇术表条目（行迹记录用）。"""
    return {"name": a.name, "effect": a.effect}


def disambiguate_fighters(
    fighter_a: str, fighter_b: str, username_a: str, username_b: str
) -> tuple[str, str]:
    """双方奇人同名时，显示为「奇人名（异闻师名）」加以区分（推演上下文与结算展示共用）。

    同名的两人分属不同异闻师（匹配排除自己），用异闻师名作后缀即可唯一区分；不同名原样返回。
    """
    if fighter_a and fighter_a == fighter_b:
        return f"{fighter_a}（{username_a}）", f"{fighter_b}（{username_b}）"
    return fighter_a, fighter_b


def _write_md(battle: Battle, user_a: User, user_b: User, story: dict, revealed: bool) -> None:
    """行迹落盘为 md 文档。看破前不含对家奇术表与解读（保密）。"""
    os.makedirs("data/battles", exist_ok=True)
    winner_name = story.get("result", "和局")
    lines = [
        f"# 行迹 #{battle.id}",
        "",
        f"**对决**：{user_a.username} vs {user_b.username}",
        f"**胜者**：{winner_name}",
        f"**名望变化**：{user_a.username} {battle.rank_delta_a:+d} / {user_b.username} {battle.rank_delta_b:+d}",
        "",
        "## 战斗叙述（发起方视角）",
        "",
        story.get("narration_a", story.get("narration", "")),
        "",
        "## 奇术解读",
        "",
        f"**{user_a.username}**：{story.get('insight_a', '')}",
        "",
    ]
    if revealed:
        lines.append(f"**{user_b.username}**：{story.get('insight_b', '')}")
    else:
        lines.append(f"**{user_b.username}**：（未看破——等待败方猜奇术，猜中可逆转胜负）")
    lines += ["", "## 发起方奇术", ""]
    for ab in story.get("abilities_a", []):
        lines.append(f"- **{ab['name']}**：{ab['effect']}")
    lines += ["", "## 对家奇术", ""]
    if revealed:
        for ab in story.get("abilities_b", []):
            lines.append(f"- **{ab['name']}**：{ab['effect']}")
    else:
        lines.append("（未看破）")
    with open(f"data/battles/battle_{battle.id}.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


async def start_battle(
    db: AsyncSession,
    user_a: User,
    *,
    opponent_id: int | None = None,
    friendly: bool = False,
) -> Battle | None:
    """启程：创建 pending 记录并启动后台推演。

    - 自身无已解封奇人（含奇术）→ 返回 None（路由 400）。
    - 已有 pending 对决 → 直接返回该记录（防重复启程）。
    - opponent_id 为 None 时自动摇签；指定则切磋。
    - 摇不到对家 / 对家无已解封奇人 → 返回 None。
    """
    loadout_a = await pick_battle_loadout(db, user_a.id)
    if loadout_a is None:
        return None

    existing = await db.execute(
        select(Battle).where(Battle.user_a_id == user_a.id, Battle.status == "pending")
    )
    if existing.scalar_one_or_none():
        return existing.scalar_one_or_none()

    if opponent_id is None:
        opponent_id = await pick_opponent(db, user_a.id)
        if opponent_id is None:
            return None
    loadout_b = await pick_battle_loadout(db, opponent_id)
    if loadout_b is None:
        return None

    battle = Battle(
        user_a_id=user_a.id,
        user_b_id=opponent_id,
        status="pending",
        story="",
        friendly=friendly,
        share_token=secrets.token_hex(16),
        share_token_b=secrets.token_hex(16),
        loadout_a_id=loadout_a.id,
        loadout_b_id=loadout_b.id,
    )
    db.add(battle)
    try:
        await db.commit()
    except IntegrityError:
        # 并发双启程：部分唯一索引挡下重复 pending，回滚后返回已存在的那场
        await db.rollback()
        existing = await db.execute(
            select(Battle).where(Battle.user_a_id == user_a.id, Battle.status == "pending")
        )
        battle = existing.scalar_one_or_none()
        if battle is None:
            return None
        return battle
    await db.refresh(battle)

    task = asyncio.create_task(_resolve_battle(battle.id, friendly))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return battle


async def recover_pending_battles() -> None:
    """启动恢复：把遗留 pending 的对决重新拉入后台推演（整场重推）。

    后台任务随进程消亡——服务重启会让进行中的对决永远停在 pending（前端一直轮询 = 卡死）。
    一次性推演没有可断点续推的中间状态，重启后从开场重推整场。
    """
    async with async_session_factory() as db:
        result = await db.execute(select(Battle).where(Battle.status == "pending"))
        for b in result.scalars().all():
            task = asyncio.create_task(_resolve_battle(b.id, b.friendly))
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)


async def _resolve_battle(battle_id: int, friendly: bool) -> None:
    """后台推演：独立会话，加载双方 → 调用推演链路模块（一次性推演 + 并发转写）→ 结算 → 落库。

    推演产出单条 SSE segment（round 0）后由 run_deduction 发布；落定后此处发布 done。
    失败（重试耗尽）标记 failed 并输出解释文本，而非静默丢场。
    节点构造器以 battle 层别名注入推演链路（测试打桩同一位置）。
    """
    stream = _get_stream(battle_id)
    async with async_session_factory() as db:
        battle = await db.get(Battle, battle_id)
        if battle is None:
            await stream.close()
            return
        try:
            user_a = await db.get(User, battle.user_a_id)
            user_b = await db.get(User, battle.user_b_id)
            if user_a is None or user_b is None:
                battle.status = "failed"
                await db.commit()
                await stream.publish({"type": "error", "message": "对决信息缺失，推演失败"})
                return
            if battle.loadout_a_id is None or battle.loadout_b_id is None:
                battle.status = "failed"
                await db.commit()
                await stream.publish({"type": "error", "message": "对决奇人缺失，推演失败"})
                return
            abilities_a = await loadout_abilities(db, battle.loadout_a_id)
            abilities_b = await loadout_abilities(db, battle.loadout_b_id)
            if not abilities_a or not abilities_b:
                battle.status = "failed"
                await db.commit()
                await stream.publish({"type": "error", "message": "双方奇术缺失，推演失败"})
                return
            loadout_a = await db.get(Loadout, battle.loadout_a_id)
            loadout_b = await db.get(Loadout, battle.loadout_b_id)
            # 奇人名字为主字（推演一律用它）；未取名时兜底异闻师用户名，保证推演输入不空
            # 奇人被删除时快照 id 已摘除（routes/loadouts.delete_loadout），回退异闻师名
            fighter_a = ((loadout_a.name if loadout_a else "") or "").strip() or user_a.username
            fighter_b = ((loadout_b.name if loadout_b else "") or "").strip() or user_b.username
            # 双方同名时以「奇人名（异闻师名）」区分（进推演上下文与结算；与 routes/battles._to_out 同规则）
            fighter_a, fighter_b = disambiguate_fighters(
                fighter_a, fighter_b, user_a.username, user_b.username
            )

            # 解读缺失时同步补生成（关闭「改了风格/战术立刻开战」的注入窗口）；失败静默回退原文。
            # ensure 在独立会话落库，需 refresh 当前会话对象以读到新值。
            for lid in (battle.loadout_a_id, battle.loadout_b_id):
                with suppress(Exception):
                    await ensure_loadout_interpretation(lid)
            if loadout_a is not None:
                await db.refresh(loadout_a)
            if loadout_b is not None:
                await db.refresh(loadout_b)
            tactic_a = (loadout_a.tactic_interpretation or loadout_a.tactic) if loadout_a else ""
            tactic_b = (loadout_b.tactic_interpretation or loadout_b.tactic) if loadout_b else ""
            style_a = (loadout_a.style_interpretation or loadout_a.style) if loadout_a else ""
            style_b = (loadout_b.style_interpretation or loadout_b.style) if loadout_b else ""

            # 推演链路模块：随机场景 + 信息组装 + 一次性推演 + 并发转写，产出全文与胜负
            r = await run_deduction(
                stream=stream,
                user_a=user_a,
                user_b=user_b,
                fighter_a=fighter_a,
                fighter_b=fighter_b,
                abilities_a=abilities_a,
                abilities_b=abilities_b,
                tactic_a=tactic_a,
                tactic_b=tactic_b,
                style_a=style_a,
                style_b=style_b,
                build_deduce=_build_deduce_llm,
                build_transcribe=_build_transcribe_chain,
                build_validate=_build_validate_chain,
                build_repair=_build_repair_chain,
            )

            a_score = 1.0 if r.winner_side == "A" else (0.0 if r.winner_side == "B" else 0.5)
            abs_a = [_ability_dict(a) for a in abilities_a]
            abs_b = [_ability_dict(a) for a in abilities_b]
            insight_a = "\n\n".join(a.understanding for a in abilities_a if a.understanding)
            insight_b = "\n\n".join(a.understanding for a in abilities_b if a.understanding)
            battle.story = json.dumps(
                {
                    "narration": r.god,  # 上帝视角：存储但不展示（API 恒过滤）
                    "narration_a": r.narration_a,
                    "narration_b": r.narration_b,
                    "insight_a": insight_a,
                    "insight_b": insight_b,
                    "result": r.result,
                    "abilities_a": abs_a,
                    "abilities_b": abs_b,
                },
                ensure_ascii=False,
            )
            battle.winner_id = r.winner_id
            # 败方 = 未获胜一方（和局无败方，不可猜奇术）
            battle.guess_by = user_b.id if r.winner_side == "A" else (user_a.id if r.winner_side == "B" else None)

            # 经济结算：双方 +5 见闻；当日首次对决额外 +5 见闻
            economy.apply_battle_rewards(user_a)
            economy.apply_battle_rewards(user_b)
            # 名望：摇签战按 Elo 更新（和局 a_score=0.5），切磋局不更新
            rank_da = rank_db = 0
            if not friendly:
                rank_da, rank_db = economy.elo_update(user_a.rank_points, user_b.rank_points, a_score)
                user_a.rank_points += rank_da
                user_b.rank_points += rank_db
                battle.rank_delta_a, battle.rank_delta_b = rank_da, rank_db
            battle.status = "done"
            # 结算时预生成猜词：判定赢家实际使用的奇术子集，与 done 同事务建 BattleGuess 行
            # （避免「done 已可见但猜词行未落库」的竞态——_prepare_guess 不单独 commit）
            if battle.guess_by is not None:
                winner_name = fighter_a if r.winner_side == "A" else fighter_b
                winner_abilities = abilities_a if r.winner_side == "A" else abilities_b
                with suppress(Exception):  # 建猜词行失败只记日志，不打断 done 落定
                    await _prepare_guess(db, battle, winner_name, winner_abilities, r.god)
            await db.commit()

            # 行迹落盘为 md 文档（看破前隐藏对家奇术）
            _write_md(battle, user_a, user_b, json.loads(battle.story), revealed=False)
            await stream.publish({"type": "done", "status": "done", "battle_id": battle_id})
        except Exception as e:  # noqa: BLE001 - 推演 LLM 重试耗尽/其他异常：中断并降级为解释文本
            logger.error("battle_failed id=%d err=%r", battle_id, e)
            with suppress(Exception):  # 落库兜底失败直接忽略，避免后台任务崩溃
                battle.status = "failed"
                battle.story = json.dumps({"error_message": FAIL_BATTLE_TEXT}, ensure_ascii=False)
                await db.commit()
            await stream.publish({"type": "error", "message": FAIL_BATTLE_TEXT})
        finally:
            await stream.close()


async def submit_guess(db: AsyncSession, battle: Battle, guesser: User, text: str) -> None:
    """败方猜对家奇术（迭代式）：每次道出一段猜测，匹配内容落到对应空白卡片并解锁猜测条；
    某卡进度到门槛即看破（揭示真实奇术）；全部看破 → 胜负逆转 + 重算名望；次数耗尽未全破 → 按设置揭示。
    """
    if battle.status != "done":
        raise ValueError("对决尚未完成")
    if battle.guess_by != guesser.id:
        raise ValueError("只有战败方可以猜奇术")
    guess = await db.get(BattleGuess, battle.id)
    if guess is None or not guess.used_abilities:
        raise ValueError("本场无奇术可猜")
    if battle.guess_state == "done":
        raise ValueError("猜测已结束")
    if guess.attempts_used >= guess.attempts_max:
        raise ValueError("猜测次数已用完")
    text = text.strip()
    if not text:
        raise ValueError("猜测不能为空")

    story = json.loads(battle.story)
    # 传给匹配 LLM 的线索 = 败方自己的视角叙述（行迹各看各的，猜奇术也只凭自己视角的线索）
    loser_narration = story.get("narration_a") if guesser.id == battle.user_a_id else story.get("narration_b", "")
    # 参考基准 = 对家实际使用的奇术（真名只在服务端作判定依据，绝不进入前端）
    abilities_txt = "\n".join(f"- {ab['name']}：{ab['effect']}" for ab in guess.used_abilities)
    cards_txt = json.dumps(
        [{"index": i + 1, "matched": c["matched"]} for i, c in enumerate(guess.cards)],
        ensure_ascii=False,
    )
    try:
        # 可靠性层：超时 + 指数退避重试（1s、2s），重试耗尽抛 ChainFailure → 降级为可重试文案
        out = await ainvoke_with_reliability(
            _build_matcher_llm(),
            GUESS_MATCHER_TEMPLATE.format_messages(
                narration=loser_narration,
                abilities=abilities_txt,
                cards=cards_txt,
                text=text,
            ),
            operation="guess",
        )
    except Exception:  # noqa: BLE001 - 可靠性层已记异常日志；此处降级为可重试文案（路由 400），不消耗次数
        raise ValueError(FAIL_GUESS_TEXT) from None

    # 应用匹配：片段上卡 + 进度累计到门槛 → 看破该卡。
    # 注意：必须重建全新字典对象再赋值——若沿用浅拷贝共享的 dict，原地改动后
    # guess.cards 当前值已被同步改动，赋回去的新值与之 == 相等，SQLAlchemy 判定
    # JSON 列"无变更"不落库（attempts_used 等标量列不受影响）。
    cards = [dict(c) for c in guess.cards]
    for m in out.matches:
        idx = m.index - 1  # LLM 输出 1 起编号，内部按 0 起
        if not (0 <= idx < len(cards)):
            continue
        card = cards[idx]
        if card["cracked"]:
            continue
        if m.snippet:
            card["matched"] = list(card["matched"]) + [m.snippet]
        card["progress"] = min(100, card["progress"] + max(0, m.progress_delta))
        if card["progress"] >= CRACK_THRESHOLD:
            card["cracked"] = True  # 看破：揭示真实奇术

    guess.cards = cards
    guess.attempts_used += 1
    battle.guess_text = text
    # 猜测原文按提交顺序落历史（新建 list 对象触发 JSON 变更检测，与 guess.cards 同套路）；
    # 赢家据此实时看到败方每次道出的猜测
    guess.guess_history = list(guess.guess_history or []) + [text]
    battle.guess_state = "guessing"

    cracked = sum(1 for c in cards if c["cracked"])
    battle.guess_score = cracked / len(cards) if cards else 0.0
    if cracked == len(cards):
        # 全破逆转：分段结算——回滚对决结束记录的名望，按逆转方向重算
        battle.guess_state = "done"
        guess.flipped = True
        battle.guess_hit = True
        battle.guess_score = 1.0
        await _apply_flip(db, battle, guesser, story)
    elif guess.attempts_used >= guess.attempts_max:
        # 次数耗尽未全破：是否揭示由被猜方（当前胜者）的设置决定
        battle.guess_state = "done"
        battle.guess_hit = False
        opponent = await db.get(User, battle.user_a_id if guesser.id == battle.user_b_id else battle.user_b_id)
        battle.revealed = opponent.reveal_on_miss if opponent else False
    else:
        battle.guess_hit = None  # 仍在猜词中

    battle.story = json.dumps(story, ensure_ascii=False)
    await db.commit()

    user_a = await db.get(User, battle.user_a_id)
    user_b = await db.get(User, battle.user_b_id)
    _write_md(battle, user_a, user_b, story, revealed=battle.revealed)


async def _prepare_guess(
    db: AsyncSession,
    battle: Battle,
    winner_name: str,
    winner_abilities: list[Ability],
    god_narration: str,
) -> None:
    """结算时预生成猜词：判定赢家实际使用的奇术子集（装配的子集），建 BattleGuess 行。

    节点失败/编号非法/空结果 → 降级为全部装配（可猜性不归零）。仅和局无败方时调用方不调用。
    不单独 commit：与 battle.status="done" 同事务落库，避免「done 已可见但猜词行未建」的竞态。
    """
    abilities_txt = "\n".join(f"{i + 1}. {a.name}：{a.effect}" for i, a in enumerate(winner_abilities))
    try:
        out = await ainvoke_with_reliability(
            _build_usage_llm(),
            USAGE_TEMPLATE.format_messages(
                winner_name=winner_name,
                abilities=abilities_txt,
                narration=god_narration,
            ),
            operation="usage",
        )
        indices = sorted({i for i in out.indices if 1 <= i <= len(winner_abilities)})
    except Exception:  # noqa: BLE001 - 可靠性层已记异常日志；此处降级为全部装配
        logger.warning("usage_fallback battle_id=%d", battle.id)
        indices = []
    if not indices:  # 空结果同样按全部装配处理
        indices = list(range(1, len(winner_abilities) + 1))
    used = [{"name": winner_abilities[i - 1].name, "effect": winner_abilities[i - 1].effect} for i in indices]
    db.add(
        BattleGuess(
            battle_id=battle.id,
            used_abilities=used,
            cards=[{"matched": [], "progress": 0, "cracked": False} for _ in used],
            attempts_max=GUESS_ATTEMPTS_MAX,
        )
    )


async def _apply_flip(db: AsyncSession, battle: Battle, guesser: User, story: dict) -> None:
    """全破逆转：败方看破全部奇术 → 胜负逆转 + 名望重算（分段结算：回滚对决结束时的名望，按逆转方向重算）。

    切磋局不重算榜分。逆转必揭示（作为确认）。
    """
    battle.winner_id = guesser.id
    # 结果用逆转方本场奇人的名字（未取名时兜底异闻师用户名），与推演口径一致
    loadout_id = battle.loadout_a_id if guesser.id == battle.user_a_id else battle.loadout_b_id
    loadout = await db.get(Loadout, loadout_id) if loadout_id else None
    story["result"] = (loadout.name or "").strip() if loadout else guesser.username
    if not battle.friendly:
        user_a = await db.get(User, battle.user_a_id)
        user_b = await db.get(User, battle.user_b_id)
        user_a.rank_points -= battle.rank_delta_a
        user_b.rank_points -= battle.rank_delta_b
        a_score = 1.0 if guesser.id == battle.user_a_id else 0.0
        delta_a, delta_b = economy.elo_update(user_a.rank_points, user_b.rank_points, a_score)
        user_a.rank_points += delta_a
        user_b.rank_points += delta_b
        battle.rank_delta_a, battle.rank_delta_b = delta_a, delta_b
    battle.revealed = True  # 全破必揭示（作为确认）
