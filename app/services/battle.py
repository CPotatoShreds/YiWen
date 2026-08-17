"""对决服务（生命周期编排层）：异步对决 + 猜奇术（非和局败方单侧 / 和局双方并行）。

流程：POST 启程 → 立即创建 pending 记录 → 后台任务把推演委托给推演链路模块
（app.services.deduction，各 LLM 节点位于 app.services.nodes/*）→ 结算（经济 + Elo）→
落库 done。

职责边界：battle.py 只管对决记录的生命周期（创建、加载、结算、猜奇术）；"把一场仗打
出来"（随机场景 + 一次性上帝推演 + 双视角并发转写）在 deduction.py；猜词三环节
（拆分→配对→检定）编排在 guess.py；各 LLM 角色（推演者/转写者/猜词判定者）的提示词与
链构造在 nodes/ 下各自成文件。节点构造器在 battle.py 以别名 _build_* 暴露，注入给推演
链路与猜词管道（测试同样打桩于此）。

推演链路：推演 LLM 以开场白 + 三选一固定结尾句一次性推演完整对战（不再分轮、无独立
判定节点），胜负从结尾句解析；随后对完整上帝叙述做一次并发转写，转写 LLM 扮演各侧
奇人、以第一人称向自己的异闻师讲述战斗经历（无系统固定首尾），经校验节点逐侧定稿
（校验 → 修复一次 → 再校验 → 上帝正文兜底），流式外发到 SSE 事件总线（先推 stage
进度：dueling 对决中 → recounting 奇人回归 → segment 转写正文）；上帝视角叙述只存档
（story["narration"]），API 恒过滤不展示；行迹各看各的。推演中一律使用奇人名字
（结尾模板 / 胜负解析 / 视角身份 / 校验视角），异闻师名字不进 LLM 上下文。

对局与活奇人解耦：新对局在创建时把双方奇人冻结为快照（snapshot_a/b，含名字/风格/战术/
奇术表），结算推演优先读快照（历史局无快照回退活奇人）。奇人榜点将局对阵榜上冻结刻印
（board_entry_id 标记，不回并入活奇人现状）；行迹「再战」以原局快照复刻（一律切磋不计
名望，猜词状态一并带入）。

奇术保密规则：对决结束前，任何一方都看不到对家的奇术表；行迹 API 与落盘
md 在看破前均不含对家奇术。结算时按「使用子集」节点判定对方**实际使用过**的奇术
（装配的子集），猜词者在有限次数内逐次道出猜测：匹配片段落到对应空白卡片、
解锁猜测条，某卡进度到门槛即看破（揭示该门真实奇术）。非和局败方全破 → 胜负逆转并
重算名望（分段结算：对决结束先记录一次名望变更，全破后回滚重算）；次数耗尽或主动
收手未全破时是否看破由被猜方 reveal_on_miss 设置决定。和局双方并行独立猜：恰一方全破
→ 其胜并重算名望，都破/都未破 → 保持和局。
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
from app.models.board import BoardEntry, BoardGuessProgress
from app.models.llm_profile import LlmProfile
from app.models.loadout import Loadout
from app.models.user import User
from app.services import economy
from app.services.battle_stream import _get_stream
from app.services.deduction import run_deduction
from app.services.guess import (
    GUESS_ATTEMPTS_MAX,
    VERIFY_FAIL_MISSING,
    render_commentary_text,
    run_guess_commentary,
    run_guess_verification,
)
from app.services.llm import profile_to_llm_config
from app.services.loadout_interpretation import ensure_loadout_interpretation
from app.services.loadouts import (
    abilities_from_snapshot,
    loadout_abilities,
    loadout_snapshot,
    pick_battle_loadout,
)
from app.services.matchmaking import pick_opponent, pick_opponent_no_repeat
from app.services.nodes.deducer import build_deduce_chain as _build_deduce_llm
from app.services.nodes.discusser import build_discuss_llm as _build_discuss_llm
from app.services.nodes.guess_matcher import build_guess_commentary_llm as _build_commentary_llm
from app.services.nodes.guess_matcher import build_guess_verify_llm as _build_verify_llm
from app.services.nodes.transcribe_validator import build_repair_chain as _build_repair_chain
from app.services.nodes.transcribe_validator import build_validate_chain as _build_validate_chain
from app.services.nodes.transcriber import build_transcribe_chain as _build_transcribe_chain
from app.services.nodes.usage_judge import USAGE_TEMPLATE
from app.services.nodes.usage_judge import build_usage_llm as _build_usage_llm
from app.services.notifications import create_notification
from app.services.reliability import ainvoke_with_reliability

logger = get_logger("battle")

# 持有后台任务引用，防止 asyncio 在任务完成前 GC 取消它
_background_tasks: set[asyncio.Task] = set()

# 在途猜词防重：同一（战场, 猜测者）后台判定期间再提交 → 409（防快速连点/网络重试双耗次数；
# 和局双方并行，各自独立防重，互不阻塞）
_guess_inflight: set[tuple[int, int]] = set()

# 全链路自动重试耗尽后的面向用户解释文本（说书语系）
FAIL_BATTLE_TEXT = "铺陈中途失联，行迹未能成卷，请稍后再启程。"
# 猜奇术规则（GUESS_ATTEMPTS_MAX / VERIFY_FAIL_MISSING）在 app.services.guess 统一维护


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
    """行迹落盘为 md 文档。看破前不含对家奇术表（保密）。"""
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
    ]
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


# ---------------------------------------------------------------------------
# 猜词行辅助（BattleGuess 复合主键 (battle_id, guesser_id)：一场多行，一行一猜测者）
# ---------------------------------------------------------------------------


async def _guess_rows(db: AsyncSession, battle_id: int) -> list[BattleGuess]:
    """某场全部猜词行（按猜测者排序，稳定）。"""
    result = await db.execute(
        select(BattleGuess)
        .where(BattleGuess.battle_id == battle_id)
        .order_by(BattleGuess.guesser_id)
    )
    return list(result.scalars().all())


def _row_for(rows: list[BattleGuess], guesser_id: int) -> BattleGuess | None:
    """某猜测者的行。"""
    return next((r for r in rows if r.guesser_id == guesser_id), None)


def _agg_guess_state(rows: list[BattleGuess]) -> str:
    """聚合猜词状态：无行 none / 有行未全 done guessing / 全 done done。"""
    if not rows:
        return "none"
    return "done" if all(r.done for r in rows) else "guessing"


async def _recalc_reveal(db: AsyncSession, battle: Battle, rows: list[BattleGuess]) -> None:
    """按逐行状态重算两侧揭示：某侧被猜破（对应行 flipped），或该侧开启 reveal_on_miss
    且对方行收手未破（done 且未 flipped）。"""
    user_a = await db.get(User, battle.user_a_id)
    user_b = await db.get(User, battle.user_b_id)
    a_row = _row_for(rows, battle.user_a_id)
    b_row = _row_for(rows, battle.user_b_id)

    def _revealed(row: BattleGuess | None, target: User | None) -> bool:
        if row is None:
            return False
        if row.flipped:
            return True
        return bool(row.done and target and target.reveal_on_miss)

    battle.revealed_a = _revealed(b_row, user_a)  # A 侧：被 B 猜破，或 A 开揭示且 B 收手未破
    battle.revealed_b = _revealed(a_row, user_b)
    battle.revealed = battle.revealed_a or battle.revealed_b


async def _resolve_loadout_inputs(
    db: AsyncSession, battle: Battle, user_a: User, user_b: User
) -> tuple[list[Ability], list[Ability], str, str, str, str, str, str] | None:
    """解析本场双方奇人输入（奇术/名字/战术/风格）：优先快照，历史局回退活奇人。奇术缺失返回 None。

    快照来自活奇人（启程/切磋/再战）且解读缺失时补生成并合并；奇人榜为冻结刻印（board_entry_id
    标记），不并入活奇人现状——榜上刻印就是参战姿态。
    """
    snap_a, snap_b = battle.snapshot_a, battle.snapshot_b
    if snap_a and snap_b:
        abilities_a = abilities_from_snapshot(snap_a.get("abilities") or [])
        abilities_b = abilities_from_snapshot(snap_b.get("abilities") or [])
        if not abilities_a or not abilities_b:
            return None
        loadout_a = await db.get(Loadout, battle.loadout_a_id) if battle.loadout_a_id else None
        loadout_b = await db.get(Loadout, battle.loadout_b_id) if battle.loadout_b_id else None
        # 解读缺失时同步补生成（关闭「改了风格/战术立刻开战」的注入窗口）；失败静默回退快照原文。
        # 快照字段已有值即直接用，不覆盖。
        if battle.board_entry_id is None:
            for lid in (battle.loadout_a_id, battle.loadout_b_id):
                if lid is not None:
                    with suppress(Exception):
                        await ensure_loadout_interpretation(lid)
            for ld, snap in ((loadout_a, snap_a), (loadout_b, snap_b)):
                if ld is not None:
                    await db.refresh(ld)
                    if not snap.get("style_interpretation"):
                        snap["style_interpretation"] = ld.style_interpretation or ""
                    if not snap.get("tactic_interpretation"):
                        snap["tactic_interpretation"] = ld.tactic_interpretation or ""
        fighter_a = (snap_a.get("name") or "").strip() or user_a.username
        fighter_b = (snap_b.get("name") or "").strip() or user_b.username
        tactic_a = snap_a.get("tactic_interpretation") or snap_a.get("tactic") or ""
        tactic_b = snap_b.get("tactic_interpretation") or snap_b.get("tactic") or ""
        style_a = snap_a.get("style_interpretation") or snap_a.get("style") or ""
        style_b = snap_b.get("style_interpretation") or snap_b.get("style") or ""
    else:
        # 历史局（无快照）：按 loadout_id 活读（奇人被删除时快照 id 已摘除，回退异闻师名）
        if battle.loadout_a_id is None or battle.loadout_b_id is None:
            return None
        abilities_a = await loadout_abilities(db, battle.loadout_a_id)
        abilities_b = await loadout_abilities(db, battle.loadout_b_id)
        if not abilities_a or not abilities_b:
            return None
        loadout_a = await db.get(Loadout, battle.loadout_a_id)
        loadout_b = await db.get(Loadout, battle.loadout_b_id)
        for lid in (battle.loadout_a_id, battle.loadout_b_id):
            with suppress(Exception):
                await ensure_loadout_interpretation(lid)
        if loadout_a is not None:
            await db.refresh(loadout_a)
        if loadout_b is not None:
            await db.refresh(loadout_b)
        fighter_a = ((loadout_a.name if loadout_a else "") or "").strip() or user_a.username
        fighter_b = ((loadout_b.name if loadout_b else "") or "").strip() or user_b.username
        tactic_a = (loadout_a.tactic_interpretation or loadout_a.tactic) if loadout_a else ""
        tactic_b = (loadout_b.tactic_interpretation or loadout_b.tactic) if loadout_b else ""
        style_a = (loadout_a.style_interpretation or loadout_a.style) if loadout_a else ""
        style_b = (loadout_b.style_interpretation or loadout_b.style) if loadout_b else ""
    fighter_a, fighter_b = disambiguate_fighters(
        fighter_a, fighter_b, user_a.username, user_b.username
    )
    return abilities_a, abilities_b, fighter_a, fighter_b, tactic_a, tactic_b, style_a, style_b


async def start_battle(
    db: AsyncSession,
    user_a: User,
    *,
    opponent_id: int | None = None,
    friendly: bool = False,
    no_repeat: bool = False,
) -> Battle | None:
    """启程：创建 pending 记录并启动后台推演。

    - 自身无已解封奇人（含奇术）→ 返回 None（路由 400）。
    - 已有 pending 对决 → 直接返回该记录（防重复启程）。
    - opponent_id 为 None 时自动摇签；指定则切磋。
    - no_repeat：摇签时避免与「我方奇人 × 对家奇人」同场过的具体配对；无可用配对兜底随机。
    - 摇不到对家 / 对家无已解封奇人 → 返回 None。
    """
    loadout_a = await pick_battle_loadout(db, user_a.id)
    if loadout_a is None:
        return None

    existing = await db.execute(
        select(Battle).where(Battle.user_a_id == user_a.id, Battle.status == "pending")
    )
    existing_battle = existing.scalar_one_or_none()
    if existing_battle:
        return existing_battle

    loadout_b: Loadout | None = None
    if opponent_id is not None:
        loadout_b = await pick_battle_loadout(db, opponent_id)
    elif no_repeat:
        pair = await pick_opponent_no_repeat(db, user_a.id, loadout_a.id)
        if pair is not None:
            opponent_id, loadout_b = pair
    if loadout_b is None and opponent_id is None:
        opponent_id = await pick_opponent(db, user_a.id)
        if opponent_id is not None:
            loadout_b = await pick_battle_loadout(db, opponent_id)
    if opponent_id is None or loadout_b is None:
        return None

    # 冻结快照：新对局与活奇人解耦（对家编辑/删除奇人不影响本场）
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
        snapshot_a=await loadout_snapshot(db, loadout_a),
        snapshot_b=await loadout_snapshot(db, loadout_b),
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


async def start_board_challenge(
    db: AsyncSession,
    challenger: User,
    entry: BoardEntry,
    chosen_loadout: Loadout,
) -> Battle | None:
    """奇人榜点将挑战：挑战者自选奇人 vs 榜上冻结刻印，建切磋局（不计名望）并启动后台推演。

    校验（chosen_loadout 归属/解封/装奇术、不能挑战自己）由路由完成；此处只组装与落库。
    榜上刻印作 snapshot_b（board_entry_id 标记，推演不回并入活奇人现状）；榜主无需在线或有活奇人。
    """
    existing = await db.execute(
        select(Battle).where(Battle.user_a_id == challenger.id, Battle.status == "pending")
    )
    existing_battle = existing.scalar_one_or_none()
    if existing_battle:
        return existing_battle

    snapshot_b = {
        "name": entry.name,
        "style": entry.style,
        "tactic": entry.tactic,
        "style_interpretation": "",
        "tactic_interpretation": "",
        "abilities": [dict(a) for a in (entry.abilities or [])],
    }
    battle = Battle(
        user_a_id=challenger.id,
        user_b_id=entry.user_id,
        status="pending",
        story="",
        friendly=True,
        share_token=secrets.token_hex(16),
        share_token_b=secrets.token_hex(16),
        loadout_a_id=chosen_loadout.id,
        loadout_b_id=entry.loadout_id,
        snapshot_a=await loadout_snapshot(db, chosen_loadout),
        snapshot_b=snapshot_b,
        board_entry_id=entry.id,
    )
    db.add(battle)
    try:
        await db.commit()
    except IntegrityError:
        # 并发双启程：唯一索引挡下重复 pending，回滚后返回已存在的那场
        await db.rollback()
        existing = await db.execute(
            select(Battle).where(Battle.user_a_id == challenger.id, Battle.status == "pending")
        )
        battle = existing.scalar_one_or_none()
        if battle is None:
            return None
        return battle
    await db.refresh(battle)

    # 通知榜主：有人点将挑战其刻印（榜主不可查看点将单场，跳奇人榜）
    await create_notification(
        db,
        user_id=entry.user_id,
        actor_id=challenger.id,
        type="board_challenge",
        title="你的奇人被点将挑战",
        body=f"「{challenger.username}」递帖点将，挑战你刻印在奇人榜上的「{entry.name}」。",
        ref_type="board",
        ref_id=entry.id,
    )

    task = asyncio.create_task(_resolve_battle(battle.id, True))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return battle


async def _fighter_name(db: AsyncSession, user_id: int, loadout_id: int | None) -> str:
    """历史局从行迹重建快照时用的名字：优先奇人名，未取名兜底异闻师名。"""
    loadout = await db.get(Loadout, loadout_id) if loadout_id else None
    if loadout and (loadout.name or "").strip():
        return (loadout.name or "").strip()
    user = await db.get(User, user_id)
    return (user.username if user else "") or ""


async def _snapshot_from_story(db: AsyncSession, battle: Battle, side: str) -> dict:
    """从行迹 story 重建快照（历史局无快照时兜底）：奇术表来自 abilities_a/b，名字回退异闻师名。"""
    story = json.loads(battle.story) if battle.story else {}
    abilities = story.get("abilities_a" if side == "a" else "abilities_b", [])
    uid = battle.user_a_id if side == "a" else battle.user_b_id
    lid = battle.loadout_a_id if side == "a" else battle.loadout_b_id
    return {
        "name": await _fighter_name(db, uid, lid),
        "style": "",
        "tactic": "",
        "style_interpretation": "",
        "tactic_interpretation": "",
        "abilities": [dict(a) for a in abilities],
    }


async def rematch_battle(db: AsyncSession, original: Battle) -> Battle:
    """行迹再战：以原局快照 + 猜词状态复刻一场新对决（一律切磋不计名望），后台重推演。

    原局有快照则原样复制（历史局无快照从 story 重建）；每个 BattleGuess 行按 guesser_id
    原样带入新局（used_abilities/cards/进度/flipped），猜词可续。新局换新 share_token。
    """
    snap_a = dict(original.snapshot_a) if original.snapshot_a else None
    snap_b = dict(original.snapshot_b) if original.snapshot_b else None
    if snap_a is None or snap_b is None:
        snap_a = snap_a or await _snapshot_from_story(db, original, "a")
        snap_b = snap_b or await _snapshot_from_story(db, original, "b")
    rows = await _guess_rows(db, original.id)
    new = Battle(
        user_a_id=original.user_a_id,
        user_b_id=original.user_b_id,
        status="pending",
        story="",
        friendly=True,  # 再战一律切磋，防互刷名望
        share_token=secrets.token_hex(16),
        share_token_b=secrets.token_hex(16),
        loadout_a_id=original.loadout_a_id,
        loadout_b_id=original.loadout_b_id,
        snapshot_a=snap_a,
        snapshot_b=snap_b,
        guess_by=original.guess_by,
        guess_text=original.guess_text,
        guess_state=original.guess_state,
        guess_hit=original.guess_hit,
        guess_score=original.guess_score,
        revealed=original.revealed,
        revealed_a=original.revealed_a,
        revealed_b=original.revealed_b,
    )
    db.add(new)
    await db.flush()
    for r in rows:
        db.add(
            BattleGuess(
                battle_id=new.id,
                guesser_id=r.guesser_id,
                used_abilities=[dict(a) for a in r.used_abilities],
                cards=[dict(c) for c in r.cards],
                guess_history=list(r.guess_history or []),
                comments=list(r.comments or []),
                attempts_used=r.attempts_used,
                attempts_max=r.attempts_max,
                verified_round=r.verified_round,
                flipped=r.flipped,
                done=r.done,
            )
        )
    await db.commit()
    await db.refresh(new)

    task = asyncio.create_task(_resolve_battle(new.id, True))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return new


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


def _plan_guess_rows(
    *,
    existing_rows: bool,
    board_entry_id: int | None,
    winner_side: str,
    user_a_id: int,
    user_b_id: int,
    fighter_a: str,
    fighter_b: str,
    abilities_a: list[Ability],
    abilities_b: list[Ability],
    progress_flipped: bool,
    progress_prefill: dict | None,
) -> list[dict]:
    """计划本次结算要建的猜词行（纯函数，不碰 db）。每项含 guesser_id/target_name/abilities/prefill。

    再战局已带入猜词行 → 空计划；点将局已全破 → 空计划；非和局败方猜胜者一行；
    和局双方各自一行（A 行猜 B、B 行猜 A）。
    """
    if existing_rows:
        return []
    if board_entry_id is not None:
        if progress_flipped:
            return []
        return [
            {"guesser_id": user_a_id, "target_name": fighter_b, "abilities": abilities_b, "prefill": progress_prefill}
        ]
    if winner_side == "A":
        return [{"guesser_id": user_b_id, "target_name": fighter_a, "abilities": abilities_a, "prefill": None}]
    if winner_side == "B":
        return [{"guesser_id": user_a_id, "target_name": fighter_b, "abilities": abilities_b, "prefill": None}]
    return [
        {"guesser_id": user_a_id, "target_name": fighter_b, "abilities": abilities_b, "prefill": None},
        {"guesser_id": user_b_id, "target_name": fighter_a, "abilities": abilities_a, "prefill": None},
    ]


async def _resolve_battle(battle_id: int, friendly: bool) -> None:
    """后台推演：分段连接——读输入（短连接）→ 推演/usage 判定（无连接）→ 结算（短连接）。

    推演产出单条 SSE segment（round 0）后由 run_deduction 发布；落定后此处发布 done。
    失败（重试耗尽）标记 failed 并输出解释文本，而非静默丢场。
    节点构造器以 battle 层别名注入推演链路（测试打桩同一位置）。
    推演期间不持连接（几十秒 LLM 等待时连接已还回池）：阶段1 只读不 commit，阶段2
    纯 LLM，阶段3 重开会话重新 get Battle/User 写回。
    """
    stream = _get_stream(battle_id)
    try:
        # ── 阶段1：读输入（短连接，只读不 commit）。会话关闭后 battle/user/ability 变
        # detached，但 expire_on_commit=False 且此处无 commit，已加载属性仍可读。──
        async with async_session_factory() as db:
            battle = await db.get(Battle, battle_id)
            if battle is None:
                return  # finally 关闭总线
            user_a = await db.get(User, battle.user_a_id)
            user_b = await db.get(User, battle.user_b_id)
            if user_a is None or user_b is None:
                battle.status = "failed"
                await db.commit()
                await stream.publish({"type": "error", "message": "对决信息缺失，推演失败"})
                return
            inputs = await _resolve_loadout_inputs(db, battle, user_a, user_b)
            if inputs is None:
                battle.status = "failed"
                battle.story = json.dumps({"error_message": "对决奇人缺失，推演失败"}, ensure_ascii=False)
                await db.commit()
                await stream.publish({"type": "error", "message": "对决奇人缺失，推演失败"})
                return
            abilities_a, abilities_b, fighter_a, fighter_b, tactic_a, tactic_b, style_a, style_b = inputs
            # 推演 LLM 配置：发起方（user_a）的激活方案，未配回退服务器默认
            profile = await db.get(LlmProfile, user_a.active_profile_id) if user_a.active_profile_id else None
            llm_config = profile_to_llm_config(profile)
            existing_rows = bool(await _guess_rows(db, battle.id))
            # 点将局跨场进度（cards/history/attempts）在此读入纯数据，供无连接阶段使用
            progress_flipped = False
            progress_prefill: dict | None = None
            if battle.board_entry_id is not None and not existing_rows:
                progress = await _board_progress(db, user_a.id, battle.board_entry_id)
                progress_flipped = bool(progress.flipped)
                progress_prefill = {
                    "cards": [dict(c) for c in (progress.cards or [])],
                    "history": list(progress.guess_history or []),
                    "comments": list(progress.comments or []),
                    "attempts": progress.attempts_used,
                    "verified_round": progress.verified_round,
                }
            user_a_id, user_b_id = user_a.id, user_b.id
            board_entry_id = battle.board_entry_id

        # ── 阶段2：推演 + 猜词行 usage 判定（无 db 连接，连接已还回池）──
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
            build_discuss=_build_discuss_llm,
            build_deduce=_build_deduce_llm,
            build_transcribe=_build_transcribe_chain,
            build_validate=_build_validate_chain,
            build_repair=_build_repair_chain,
            llm_config=llm_config,
            trace_context={"kind": "battle", "trace_id": str(battle_id)},
        )
        guess_plan = _plan_guess_rows(
            existing_rows=existing_rows,
            board_entry_id=board_entry_id,
            winner_side=r.winner_side,
            user_a_id=user_a_id,
            user_b_id=user_b_id,
            fighter_a=fighter_a,
            fighter_b=fighter_b,
            abilities_a=abilities_a,
            abilities_b=abilities_b,
            progress_flipped=progress_flipped,
            progress_prefill=progress_prefill,
        )
        for p in guess_plan:
            p["data"] = await _build_guess_row_data(
                battle_id=battle_id,
                target_name=p["target_name"],
                target_abilities=p["abilities"],
                god_narration=r.god,
                prefill=p["prefill"],
                llm_config=llm_config,
            )

        # ── 阶段3：结算落库（短连接，重新 get 写回；不 merge/add detached）──
        async with async_session_factory() as db:
            battle = await db.get(Battle, battle_id)
            if battle is None:
                await stream.publish({"type": "error", "message": "对决信息缺失，推演失败"})
                return
            user_a = await db.get(User, battle.user_a_id)
            user_b = await db.get(User, battle.user_b_id)
            if user_a is None or user_b is None:
                await stream.publish({"type": "error", "message": "对决信息缺失，推演失败"})
                return

            a_score = 1.0 if r.winner_side == "A" else (0.0 if r.winner_side == "B" else 0.5)
            abs_a = [_ability_dict(a) for a in abilities_a]
            abs_b = [_ability_dict(a) for a in abilities_b]
            battle.story = json.dumps(
                {
                    "narration": r.god,  # 上帝视角：存储但不展示（API 恒过滤）
                    "narration_a": r.narration_a,
                    "narration_b": r.narration_b,
                    "result": r.result,
                    "abilities_a": abs_a,
                    "abilities_b": abs_b,
                },
                ensure_ascii=False,
            )
            battle.winner_id = r.winner_id

            # 猜词行：结算时预生成（非和局败方猜胜者；和局双方并行猜对方）。
            # 再战局已带入猜词行（existing_rows 非空）→ 不再重建，guess_by/guess_state 沿用带入值。
            existing_rows = await _guess_rows(db, battle.id)
            if not existing_rows and battle.board_entry_id is not None:
                # 点将局：挑战者恒猜刻印侧（无论本场胜负），进度跨场累积；
                # 已全部看破 → 不再启动猜词，刻印全揭示（完整三视角由序列化按进度解锁）。
                await _board_progress(db, user_a.id, battle.board_entry_id)
                battle.guess_by = user_a.id
                if progress_flipped:
                    battle.guess_state = "none"
                    battle.revealed_b = True
                    battle.revealed = True
                else:
                    for p in guess_plan:
                        with suppress(Exception):  # 建猜词行失败只记日志，不打断 done 落定
                            db.add(BattleGuess(battle_id=battle.id, guesser_id=p["guesser_id"], **p["data"]))
                    battle.guess_state = _agg_guess_state(await _guess_rows(db, battle.id))
            elif not existing_rows:
                if r.winner_side == "A":
                    battle.guess_by = user_b.id
                elif r.winner_side == "B":
                    battle.guess_by = user_a.id
                else:
                    battle.guess_by = None  # 和局：双方皆可猜，各自一行
                for p in guess_plan:
                    with suppress(Exception):
                        db.add(BattleGuess(battle_id=battle.id, guesser_id=p["guesser_id"], **p["data"]))
                battle.guess_state = _agg_guess_state(await _guess_rows(db, battle.id))

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
            await db.commit()

            # 行迹落盘为 md 文档（看破前隐藏对家奇术；点将局已全看破则含刻印表）
            _write_md(battle, user_a, user_b, json.loads(battle.story), revealed=battle.revealed)
            # 通知参战双方战报落定；点将局榜主不可查看单场，仅通知挑战者
            recipients = [(battle.user_a_id, user_b), (battle.user_b_id, user_a)]
            if battle.board_entry_id is not None:
                recipients = [(battle.user_a_id, user_b)]
            for recipient_id, opponent in recipients:
                with suppress(Exception):  # 通知失败只跳过，不打断 done 落定
                    await create_notification(
                        db,
                        user_id=recipient_id,
                        actor_id=opponent.id,
                        type="battle_report",
                        title="新的战报已送达",
                        body=f"你与「{opponent.username}」的对决已落定，新的行迹战报待你检阅。",
                        ref_type="battle",
                        ref_id=battle.id,
                    )
            await stream.publish({"type": "done", "status": "done", "battle_id": battle_id})
    except Exception as e:  # noqa: BLE001 - 推演 LLM 重试耗尽/其他异常：中断并降级为解释文本
        logger.error("battle_failed id=%d err=%r", battle_id, e)
        # 落库兜底仅作用于仍 pending 的战场（重开短连接）：推演中途失败置 failed；
        # 已在阶段3落定 done 的不再覆盖（修复旧代码「done 后异常把状态改回 failed」的隐患）。
        async with async_session_factory() as db:
            with suppress(Exception):  # 落库兜底失败直接忽略，避免后台任务崩溃
                b = await db.get(Battle, battle_id)
                if b is not None and b.status == "pending":
                    b.status = "failed"
                    b.story = json.dumps({"error_message": FAIL_BATTLE_TEXT}, ensure_ascii=False)
                    await db.commit()
        await stream.publish({"type": "error", "message": FAIL_BATTLE_TEXT})
    finally:
        await stream.close()


def _can_verify(guess: BattleGuess) -> bool:
    """检定是否可发起：行未结束、未耗尽，且自上次检定后又有新的点评（can_verify 判据）。

    verified_round 存「最近一次检定时的点评数」，检定后再次发起须先有新点评（点评数增大）。
    """
    if guess.done or guess.flipped:
        return False
    if guess.attempts_used >= guess.attempts_max:
        return False
    return len(guess.comments or []) > (guess.verified_round or 0)


async def _guess_load(
    db: AsyncSession, battle: Battle, guesser: User, text: str
) -> dict:
    """点评读+校验（只读，不落库）：返回 run_guess_commentary 的入参 kwargs。

    与路由的同步校验镜像（校验失败 400）；校验规则与写回阶段 _guess_settle 顶部保持一致。
    """
    if battle.status != "done":
        raise ValueError("对决尚未完成")
    rows = await _guess_rows(db, battle.id)
    guess = _row_for(rows, guesser.id)
    if guess is None or not guess.used_abilities:
        raise ValueError("本场无奇术可猜")
    if guess.done or guess.flipped:
        raise ValueError("猜测已结束")
    if guess.attempts_used >= guess.attempts_max:
        raise ValueError("猜测次数已用完")
    text = text.strip()
    if not text:
        raise ValueError("猜测不能为空")

    abilities = guess.used_abilities  # 参考基准 = 对家实际使用的奇术（真名只在服务端作判定依据，绝不进入前端）
    profile = await db.get(LlmProfile, guesser.active_profile_id) if guesser.active_profile_id else None
    llm_config = profile_to_llm_config(profile)
    return {
        "text": text,
        "abilities": abilities,
        "cards": [dict(c) for c in guess.cards],  # 重建全新 dict 触发 JSON 变更检测（沿用既有套路）
        "trace_context": {"kind": "guess", "trace_id": str(battle.id)},
        "build_commentary": _build_commentary_llm,
        "llm_config": llm_config,
    }


async def _verify_load(
    db: AsyncSession, battle: Battle, guesser: User
) -> dict:
    """检定读+校验（只读，不落库）：返回 run_guess_verification 的入参 kwargs。

    与路由的同步校验镜像；校验规则与写回阶段 _verify_settle 顶部保持一致。
    """
    if battle.status != "done":
        raise ValueError("对决尚未完成")
    rows = await _guess_rows(db, battle.id)
    guess = _row_for(rows, guesser.id)
    if guess is None or not guess.used_abilities:
        raise ValueError("本场无奇术可猜")
    if not _can_verify(guess):
        raise ValueError("尚无新的猜测进展，暂不可检定")

    abilities = guess.used_abilities
    profile = await db.get(LlmProfile, guesser.active_profile_id) if guesser.active_profile_id else None
    llm_config = profile_to_llm_config(profile)
    return {
        "history": list(guess.guess_history or []),
        "comments": list(guess.comments or []),
        "abilities": abilities,
        "cards": [dict(c) for c in guess.cards],  # 重建全新 dict 触发 JSON 变更检测（沿用既有套路）
        "round_no": len(guess.comments or []),
        "trace_context": {"kind": "guess_verify", "trace_id": str(battle.id)},
        "build_verify": _build_verify_llm,
        "llm_config": llm_config,
    }


async def _guess_settle(
    db: AsyncSession, battle: Battle, guesser: User, text: str, commentary: list[dict]
) -> None:
    """点评写回+结算：重取 rows/guess/story（与读阶段读取一致，因读阶段不落库），应用本轮点评并落库。

    自包含，不依赖调用方预读的 ORM 状态；顶部复检防止竞态（如用户在本轮 LLM 期间收手）。
    点评只追加猜测原文与逐门原子判定、消耗一次机会；不改变看破状态、不重算 score。
    """
    rows = await _guess_rows(db, battle.id)
    guess = _row_for(rows, guesser.id)
    if guess is None or not guess.used_abilities:
        raise ValueError("本场无奇术可猜")
    if guess.done or guess.flipped:
        raise ValueError("猜测已结束")
    if guess.attempts_used >= guess.attempts_max:
        raise ValueError("猜测次数已用完")
    story = json.loads(battle.story)

    battle.guess_text = text
    # 猜测原文与逐门点评按提交顺序落历史（新建 list 对象触发 JSON 变更检测，与 guess.cards 同套路）；
    # 对家据此实时看到猜词者每次道出的猜测与点评
    guess.guess_history = list(guess.guess_history or []) + [text]
    guess.comments = list(guess.comments or []) + [commentary]
    guess.attempts_used += 1
    cracked = sum(1 for c in guess.cards if c.get("cracked"))

    if guess.attempts_used >= guess.attempts_max:
        # 次数耗尽未全破：是否揭示由被猜方（当前胜者）的设置决定
        guess.done = True
        if battle.guess_by is not None and battle.board_entry_id is None:
            battle.guess_hit = False
    elif battle.guess_by is not None:
        battle.guess_hit = None  # 仍在猜词中

    rows = await _guess_rows(db, battle.id)
    battle.guess_state = _agg_guess_state(rows)
    if battle.board_entry_id is not None:
        # 点将局：本轮点评即「本猜词爆出的线索」（点评文本全量入榜，供榜主追踪猜词路径）
        log_entry = {
            "battle_id": battle.id,
            "round": len(guess.guess_history),
            "text": text,
            "commentary": render_commentary_text(commentary),
            "cracked_after": cracked,
            "at": battle.created_at.isoformat(),
        }
        await _sync_board_progress(db, battle, guess, log_entry=log_entry)  # 点将局：回写跨场进度，揭示以进度全破为准
    else:
        await _recalc_reveal(db, battle, rows)
    if battle.guess_by is None and battle.guess_state == "done":
        await _settle_draw_outcome(db, battle, rows)

    battle.story = json.dumps(story, ensure_ascii=False)
    await db.commit()

    user_a = await db.get(User, battle.user_a_id)
    user_b = await db.get(User, battle.user_b_id)
    _write_md(battle, user_a, user_b, story, revealed=battle.revealed)

    # 通知被猜方有新的猜词进展：每次点评都通知（点评即新的窥探行为）；
    # 点将局榜主不可查看单场，猜词进展归并到榜单，不逐场通知。
    if battle.board_entry_id is None:
        opponent = user_b if guesser.id == battle.user_a_id else user_a
        with suppress(Exception):
            await create_notification(
                db,
                user_id=opponent.id,
                actor_id=guesser.id,
                type="guess_progress",
                title="你的奇术正被窥探",
                body=f"「{guesser.username}」正于行迹中道出猜测，窥探你的奇术（已看破 {cracked} 门）。",
                ref_type="battle",
                ref_id=battle.id,
            )


async def _verify_settle(
    db: AsyncSession, battle: Battle, guesser: User, cards: list[dict], round_no: int
) -> None:
    """检定写回+结算：应用本轮检定结果（看破/还缺什么），重算 score，触发全破逆转等结算。

    检定不追加 guess_history/comments（聊天记录只含点评轮）；verified_round 记为检定时点评数，
    can_verify = len(comments) > verified_round 由此保证「检定后须有新点评才能再检定」。
    """
    rows = await _guess_rows(db, battle.id)
    guess = _row_for(rows, guesser.id)
    if guess is None or not guess.used_abilities:
        raise ValueError("本场无奇术可猜")
    if not _can_verify(guess):
        raise ValueError("尚无新的猜测进展，暂不可检定")
    story = json.loads(battle.story)
    pre_cracked = sum(1 for c in guess.cards if c.get("cracked"))

    guess.cards = [
        {"cracked": c["cracked"], "missing": c.get("missing") or "", "cracked_round": c.get("cracked_round")}
        for c in cards
    ]
    guess.verified_round = round_no
    guess.attempts_used += 1

    cracked = sum(1 for c in cards if c["cracked"])
    battle.guess_score = cracked / len(cards) if cards else 0.0
    if cracked == len(cards):
        # 全破：本行结束。非和局立即逆转（回滚名望重算）；和局等双方都收手再结算；
        # 点将局全破不翻转胜负（猜词是研究刻印，非反杀），guess_hit 保持 None。
        guess.flipped = True
        guess.done = True
        battle.guess_score = 1.0
        if battle.guess_by is not None and battle.board_entry_id is None:
            battle.guess_hit = True
            await _apply_flip(db, battle, guesser, story)
    elif guess.attempts_used >= guess.attempts_max:
        # 次数耗尽未全破：是否揭示由被猜方（当前胜者）的设置决定
        guess.done = True
        if battle.guess_by is not None and battle.board_entry_id is None:
            battle.guess_hit = False
    else:
        if battle.guess_by is not None:
            battle.guess_hit = None  # 仍在猜词中

    rows = await _guess_rows(db, battle.id)
    battle.guess_state = _agg_guess_state(rows)
    if battle.board_entry_id is not None:
        await _sync_board_progress(db, battle, guess)  # 点将局：检定回写进度（新看破/还缺什么）
    else:
        await _recalc_reveal(db, battle, rows)
    if battle.guess_by is None and battle.guess_state == "done":
        await _settle_draw_outcome(db, battle, rows)

    battle.story = json.dumps(story, ensure_ascii=False)
    await db.commit()

    user_a = await db.get(User, battle.user_a_id)
    user_b = await db.get(User, battle.user_b_id)
    _write_md(battle, user_a, user_b, story, revealed=battle.revealed)

    # 通知被猜方有新的猜词进展：仅当本轮产生新看破（检定无新看破不刷屏）；
    # 点将局榜主不可查看单场，猜词进展归并到榜单，不逐场通知。
    if battle.board_entry_id is None and cracked > pre_cracked:
        opponent = user_b if guesser.id == battle.user_a_id else user_a
        with suppress(Exception):
            await create_notification(
                db,
                user_id=opponent.id,
                actor_id=guesser.id,
                type="guess_progress",
                title="你的奇术正被窥探",
                body=f"「{guesser.username}」正于行迹中道出猜测，窥探你的奇术（已看破 {cracked} 门）。",
                ref_type="battle",
                ref_id=battle.id,
            )


async def submit_guess(db: AsyncSession, battle: Battle, guesser: User, text: str) -> None:
    """猜对家奇术（迭代式）：读+校验 → LLM 点评 → 写回结算。

    保持单会话语义（同一传入会话完成三阶段），供直接调用方/测试使用；后台任务
    _run_guess_task 走分段连接版（读/LLM/写各一短连接）。
    """
    ctx = await _guess_load(db, battle, guesser, text)
    commentary = await run_guess_commentary(**ctx)
    await _guess_settle(db, battle, guesser, ctx["text"], commentary)


async def verify_guess(db: AsyncSession, battle: Battle, guesser: User) -> None:
    """主动检定对家奇术（迭代式）：读+校验 → LLM 逐卡检定 → 写回结算。同 submit_guess 会话语义。"""
    ctx = await _verify_load(db, battle, guesser)
    cards = await run_guess_verification(**ctx)
    await _verify_settle(db, battle, guesser, cards, ctx["round_no"])


async def give_up_guess(db: AsyncSession, battle: Battle, guesser: User) -> None:
    """收手：猜词者未全破即结束本轮猜词。未看破时是否揭示由被猜方 reveal_on_miss 决定
    （与次数耗尽分支同语义）。和局双方都收手后触发 _settle_draw_outcome 结算。
    """
    if battle.status != "done":
        raise ValueError("对决尚未完成")
    rows = await _guess_rows(db, battle.id)
    guess = _row_for(rows, guesser.id)
    if guess is None or not guess.used_abilities:
        raise ValueError("本场无奇术可猜")
    if guess.done or guess.flipped:
        raise ValueError("猜测已结束")
    guess.done = True
    if battle.guess_by is not None and battle.board_entry_id is None:
        battle.guess_hit = False
    rows = await _guess_rows(db, battle.id)
    battle.guess_state = _agg_guess_state(rows)
    if battle.board_entry_id is not None:
        await _sync_board_progress(db, battle, guess)  # 点将局：收手回写进度但不动揭示、不置 done
    else:
        await _recalc_reveal(db, battle, rows)
    if battle.guess_by is None and battle.guess_state == "done":
        await _settle_draw_outcome(db, battle, rows)
    story = json.loads(battle.story) if battle.story else {}
    await db.commit()

    user_a = await db.get(User, battle.user_a_id)
    user_b = await db.get(User, battle.user_b_id)
    _write_md(battle, user_a, user_b, story, revealed=battle.revealed)

    # 收手同步完成：经总线推 guess_done，对方打开的 SSE 流据此刷新；全部结束则关闭总线
    stream = _get_stream(battle.id)
    await stream.publish({"type": "guess_done", "battle_id": battle.id})
    if battle.guess_state == "done":
        await stream.close()


async def _run_guess_task(battle_id: int, guesser_id: int, text: str) -> None:
    """后台猜词（点评）：分段连接——读+校验（短连接）→ LLM 点评（无连接）→ 写回落库（短连接）。

    完成后经总线推 guess_done；猜词彻底结束（guess_state == "done"）时关闭总线，
    SSE 订阅端回落到立即 done。
    """
    stream = _get_stream(battle_id)
    try:
        async with async_session_factory() as db:
            battle = await db.get(Battle, battle_id)
            if battle is None:
                return
            guesser = await db.get(User, guesser_id)
            if guesser is None:
                return
            ctx = await _guess_load(db, battle, guesser, text)
        commentary = await run_guess_commentary(**ctx)  # 无 db 连接
        async with async_session_factory() as db:
            battle = await db.get(Battle, battle_id)
            guesser = await db.get(User, guesser_id)
            if battle is None or guesser is None:
                return
            await _guess_settle(db, battle, guesser, ctx["text"], commentary)
            finished = battle.guess_state == "done"
        await stream.publish({"type": "guess_done", "battle_id": battle_id})
        if finished:
            await stream.close()
    except ValueError as e:
        await stream.publish({"type": "guess_error", "message": str(e)})
    except Exception as e:  # noqa: BLE001 - 后台猜词任何异常都落到事件，不让任务静默死亡
        logger.error("guess_failed id=%d err=%r", battle_id, e)
        await stream.publish({"type": "guess_error", "message": "猜测判定失败，请稍后重试"})
    finally:
        _guess_inflight.discard((battle_id, guesser_id))


async def _run_verify_task(battle_id: int, guesser_id: int) -> None:
    """后台检定：分段连接——读+校验（短连接）→ LLM 逐卡检定（无连接）→ 写回落库（短连接）。

    与 _run_guess_task 同构；检定不追加聊天记录，只更新逐卡看破/还缺什么并重算 score。
    """
    stream = _get_stream(battle_id)
    try:
        async with async_session_factory() as db:
            battle = await db.get(Battle, battle_id)
            if battle is None:
                return
            guesser = await db.get(User, guesser_id)
            if guesser is None:
                return
            ctx = await _verify_load(db, battle, guesser)
        cards = await run_guess_verification(**ctx)  # 无 db 连接
        async with async_session_factory() as db:
            battle = await db.get(Battle, battle_id)
            guesser = await db.get(User, guesser_id)
            if battle is None or guesser is None:
                return
            await _verify_settle(db, battle, guesser, cards, ctx["round_no"])
            finished = battle.guess_state == "done"
        await stream.publish({"type": "guess_done", "battle_id": battle_id})
        if finished:
            await stream.close()
    except ValueError as e:
        await stream.publish({"type": "guess_error", "message": str(e)})
    except Exception as e:  # noqa: BLE001 - 后台检定任何异常都落到事件，不让任务静默死亡
        logger.error("guess_verify_failed id=%d err=%r", battle_id, e)
        await stream.publish({"type": "guess_error", "message": "检定失败，请稍后重试"})
    finally:
        _guess_inflight.discard((battle_id, guesser_id))


def try_start_guess(battle_id: int, guesser_id: int, text: str) -> bool:
    """猜词后台任务入队（在途防重，按猜测者独立）。调用方已完成同步校验；返回 False 表示已有判定在途。"""
    key = (battle_id, guesser_id)
    if key in _guess_inflight:
        return False
    _guess_inflight.add(key)
    task = asyncio.create_task(_run_guess_task(battle_id, guesser_id, text))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return True


def try_start_verify(battle_id: int, guesser_id: int) -> bool:
    """检定后台任务入队（与点评共用在途防重：同（战场, 猜测者）点评/检定互斥）。"""
    key = (battle_id, guesser_id)
    if key in _guess_inflight:
        return False
    _guess_inflight.add(key)
    task = asyncio.create_task(_run_verify_task(battle_id, guesser_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return True


async def _build_guess_row_data(
    battle_id: int,
    target_name: str,
    target_abilities: list[Ability],
    god_narration: str,
    prefill: dict | None,
    llm_config: dict | None,
) -> dict:
    """纯函数（无 db）：判定被猜侧实际使用的奇术子集，返回 BattleGuess 构造参数。

    非和局：败方猜胜者；和局：A 行猜 B、B 行猜 A；点将局：挑战者恒猜刻印侧，prefill 传入
    跨场进度纯数据（cards 按快照下标预填、history/attempts 带入；本场用术子集全部已认识 → 行即结束）。
    节点失败/编号非法/空结果 → 降级为全部装配（可猜性不归零）。调用方负责在同一事务里
    db.add 落库（不单独 commit：与 battle.status="done" 同事务落库，避免「done 已可见但
    猜词行未建」的竞态）。
    """
    abilities_txt = "\n".join(f"{i + 1}. {a.name}：{a.effect}" for i, a in enumerate(target_abilities))
    try:
        out = await ainvoke_with_reliability(
            _build_usage_llm(llm_config=llm_config),
            USAGE_TEMPLATE.format_messages(
                winner_name=target_name,
                abilities=abilities_txt,
                narration=god_narration,
            ),
            operation="usage",
            trace_context={"kind": "guess", "trace_id": str(battle_id)},
        )
        indices = sorted({i for i in out.indices if 1 <= i <= len(target_abilities)})
    except Exception:  # noqa: BLE001 - 可靠性层已记异常日志；此处降级为全部装配
        logger.warning("usage_fallback battle_id=%d", battle_id)
        indices = []
    if not indices:  # 空结果同样按全部装配处理
        indices = list(range(1, len(target_abilities) + 1))
    used = [{"name": target_abilities[i - 1].name, "effect": target_abilities[i - 1].effect} for i in indices]
    if prefill is not None:
        # 点将局：usage 下标即刻印快照下标，跨场进度按位预填；子集全已认识 → 行即结束（不翻转）
        cards = [dict(prefill["cards"][i - 1]) for i in indices]
        history = list(prefill.get("history") or [])
        comments = list(prefill.get("comments") or [])
        attempts = prefill.get("attempts") or 0
        verified_round = prefill.get("verified_round")
        done = bool(cards) and all(c["cracked"] for c in cards)
    else:
        cards = [{"cracked": False, "missing": None} for _ in used]
        history = []
        comments = []
        attempts = 0
        verified_round = None
        done = False
    return {
        "used_abilities": used,
        "cards": cards,
        "guess_history": history,
        "comments": comments,
        "attempts_used": attempts,
        "attempts_max": GUESS_ATTEMPTS_MAX,
        "verified_round": verified_round,
        "flipped": done,  # 点将局 flipped 仅表示「本场用术子集已全认识」（不驱动翻转/揭示）
        "done": done,
    }


async def _board_progress(db: AsyncSession, challenger_id: int, entry_id: int) -> BoardGuessProgress:
    """加载（不存在则建）挑战者 × 刻印 的跨场看破进度行。cards 初始按刻印全量奇术对齐。"""
    row = await db.get(BoardGuessProgress, (challenger_id, entry_id))
    if row is None:
        entry = await db.get(BoardEntry, entry_id)
        row = BoardGuessProgress(
            challenger_id=challenger_id,
            board_entry_id=entry_id,
            cards=[{"cracked": False, "missing": ""} for _ in (entry.abilities if entry else [])],
        )
        db.add(row)
        await db.flush()
    return row


def _progress_index(abilities: list[dict], used: dict) -> int | None:
    """把猜词行 used（{name, effect}）映射回刻印快照下标（同刻印内 name+effect 唯一）。"""
    for i, a in enumerate(abilities):
        if a.get("name") == used.get("name") and a.get("effect") == used.get("effect"):
            return i
    return None


async def _sync_board_progress(
    db: AsyncSession, battle: Battle, guess: BattleGuess, log_entry: dict | None = None
) -> None:
    """点将局：把本场猜词行状态合并回跨场进度（并集语义：已看破的卡不回退）。

    跨场进度与本场猜词行可能基于不同快照预填（新场结算读到的进度可能先于上一场猜词
    提交），故只上卷不回卷。揭示以「刻印全量奇术全破」为准（不翻转胜负）；收手未全破
    只回写进度、不置 done：下一场仍可猜。重建 JSON 对象触发变更检测。log_entry 非空时
    追加一条逐条猜词记录（供榜主挑战者追踪）。
    """
    entry = await db.get(BoardEntry, battle.board_entry_id)
    if entry is None:
        return
    abilities = entry.abilities or []
    progress = await _board_progress(db, battle.user_a_id, battle.board_entry_id)
    new_cards = [dict(p) for p in progress.cards]  # 重建触发 JSON 变更检测
    for used, card in zip(guess.used_abilities, guess.cards):
        idx = _progress_index(abilities, used)
        if idx is None or idx >= len(new_cards):
            continue
        if card["cracked"]:
            new_cards[idx] = dict(card)
        else:
            # 未看破门：只上卷最近一次检定给出的「还缺什么」（跨场并集）；不回退。
            # 检定失联的临时文案不持久化。
            missing = (card.get("missing") or "").strip()
            if missing and missing != VERIFY_FAIL_MISSING:
                new_cards[idx]["missing"] = missing
    progress.cards = new_cards
    progress.guess_history = list(guess.guess_history or [])
    progress.comments = list(guess.comments or [])
    progress.attempts_used = max(progress.attempts_used or 0, guess.attempts_used or 0)
    progress.verified_round = max(progress.verified_round or 0, guess.verified_round or 0)
    if log_entry is not None:
        progress.guess_log = list(progress.guess_log or []) + [log_entry]
    if new_cards and all(c["cracked"] for c in new_cards):
        progress.flipped = True
        progress.done = True
        battle.revealed_b = True
        battle.revealed = True


async def _settle_draw_outcome(
    db: AsyncSession, battle: Battle, rows: list[BattleGuess]
) -> None:
    """和局双方都收手后结算：恰一侧全破 → 其胜并重算名望；都全破/都未破 → 保持和局。"""
    if battle.guess_state != "done" or battle.guess_by is not None:
        return
    flips = [r for r in rows if r.flipped]
    if len(flips) == 1:
        winner = flips[0]
        guesser = await db.get(User, winner.guesser_id)
        story = json.loads(battle.story) if battle.story else {}
        await _apply_flip(db, battle, guesser, story)
        battle.guess_hit = True
        battle.story = json.dumps(story, ensure_ascii=False)
    else:
        battle.guess_hit = False


async def _apply_flip(db: AsyncSession, battle: Battle, guesser: User, story: dict) -> None:
    """全破逆转：看破方翻为胜者 + 名望重算（分段结算：回滚对决结束时的名望，按逆转方向重算）。

    切磋局不重算榜分。逆转必揭示被猜侧（_recalc_reveal 依行 flipped 置位）。
    """
    battle.winner_id = guesser.id
    # 结果用逆转方本场奇人的名字（优先快照，未取名时兜底异闻师用户名），与推演口径一致
    side = "a" if guesser.id == battle.user_a_id else "b"
    snap = battle.snapshot_a if side == "a" else battle.snapshot_b
    loadout_id = battle.loadout_a_id if side == "a" else battle.loadout_b_id
    loadout = await db.get(Loadout, loadout_id) if loadout_id else None
    snap_name = (snap.get("name") or "").strip() if snap else ""
    story["result"] = snap_name or ((loadout.name or "").strip() if loadout else "") or guesser.username
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
