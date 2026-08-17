"""后台管理路由：仪表盘 / 数据库 CRUD / 流量 / 对战试验场。全部要求管理员权限。

- 用户、异能：完整增删改查
- 对战、奇人、故人：查看 + 删除
- 对战试验场：纯测试对战与猜词（test_* 表），对玩家数据零持久性影响
- SQLite 未开 foreign_keys、FK 均无 ondelete → 删除一律手动清理依赖行（仿
  app/api/routes/loadouts.py 与 abilities.py 的既有模式）
"""

import asyncio
import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_admin, hash_password
from app.db.base import get_db
from app.models.ability import Ability
from app.models.battle import Battle, BattleGuess
from app.models.board import BoardGuessProgress
from app.models.friendship import Friendship
from app.models.llm_trace import LlmTrace
from app.models.loadout import Loadout, LoadoutAbility
from app.models.notification import Notification
from app.models.prompt_debug import PromptDebugRun, PromptScheme
from app.models.request_log import RequestLog
from app.models.test_battle import (
    TestBattle,
    TestBattleGuess,
    TestLoadout,
    TestLoadoutAbility,
    TestUser,
)
from app.models.user import User
from app.models.user_ability import UserAbility
from app.schemas.ability import AbilityOut
from app.schemas.admin import (
    AbilityAdminIn,
    AdminBattleOut,
    AdminLoadoutOut,
    AdminUserCreate,
    AdminUserOut,
    AdminUserUpdate,
    DailyPoint,
    EndpointStat,
    FriendshipRowOut,
    LlmTraceDetailOut,
    LlmTraceOpStat,
    LlmTraceOut,
    LlmTraceStatsOut,
    PromptDebugRunOut,
    PromptSchemeIn,
    PromptSchemeOut,
    PromptSchemeUpdate,
    RecentBattle,
    RequestLogOut,
    RerunIn,
    StatsOut,
    TestBattleOut,
    TestBattleStartIn,
    TestFighterIn,
    TestGuessIn,
    TestLoadoutCreateIn,
    TestLoadoutOut,
    TestReportOut,
    TestSkipIn,
    TestUserCreate,
    TestUserOut,
    TrafficOut,
)
from app.services.ability_understanding import ensure_ability_understanding
from app.services.battle import GUESS_ATTEMPTS_MAX
from app.services.prompt_debug import rerun_battle
from app.services.test_battle import (
    generate_test_discuss_report,
    resolve_test_battle,
    resolve_test_battle_from_deduction,
    submit_test_guess,
)

router = APIRouter(prefix="/admin", tags=["admin"])

RECENT_BATTLES = 10  # 仪表盘最近场数
BATTLE_LIST_LIMIT = 100  # 行迹列表上限
ENDPOINT_TOP = 12  # 接口流量 TOP 数量

# 持有后台任务引用，防止 asyncio 在任务完成前 GC 取消它
_background_tasks: set[asyncio.Task] = set()


def _ability_id(name: str, effect: str) -> str:
    """后台创建的奇术 id：内容哈希（管理员域内同内容去重）。"""
    return sha256(f"admin:{name}:{effect}".encode()).hexdigest()[:16]


def _schedule_understanding(ability_id: str) -> None:
    """后台异步重算奇术因果槽位（失败静默，不阻塞管理员操作）。"""
    task = asyncio.create_task(ensure_ability_understanding(ability_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _names(db: AsyncSession, ids: set[int]) -> dict[int, str]:
    """批量解析用户 id → 用户名（删过的用户兜底跳过）。"""
    if not ids:
        return {}
    rows = await db.execute(select(User).where(User.id.in_(ids)))
    return {u.id: u.username for u in rows.scalars().all()}


async def _test_names(db: AsyncSession, ids: set[int]) -> dict[int, str]:
    """批量解析测试账号 id → 用户名（测试账号独立于玩家表，须查 test_users）。"""
    if not ids:
        return {}
    rows = await db.execute(select(TestUser).where(TestUser.id.in_(ids)))
    return {u.id: u.username for u in rows.scalars().all()}


def _load_story(raw: str) -> dict | None:
    """解析 story JSON；空串 / 坏 JSON 兜底 None。"""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


def _admin_battle_out(
    b: Battle,
    name_map: dict[int, str],
    guess_history: list[str] | None = None,
    guess_total: int = 0,
    guess_cards: list[dict] | None = None,
    guess_attempts_used: int = 0,
    guess_attempts_max: int = GUESS_ATTEMPTS_MAX,
) -> AdminBattleOut:
    """行迹的管理员视角序列化（story 完整上帝视角，含双方奇术表）。"""
    return AdminBattleOut(
        id=b.id,
        user_a=name_map.get(b.user_a_id),
        user_b=name_map.get(b.user_b_id),
        winner=name_map.get(b.winner_id) if b.winner_id else None,
        status=b.status,
        friendly=b.friendly,
        story=_load_story(b.story),
        rank_delta_a=b.rank_delta_a,
        rank_delta_b=b.rank_delta_b,
        loadout_a_id=b.loadout_a_id,
        loadout_b_id=b.loadout_b_id,
        guess_by=name_map.get(b.guess_by) if b.guess_by else None,
        guess_state=b.guess_state,
        guess_hit=b.guess_hit,
        guess_score=b.guess_score,
        guess_history=guess_history or [],
        guess_total=guess_total,
        guess_cards=guess_cards,
        guess_attempts_used=guess_attempts_used,
        guess_attempts_max=guess_attempts_max,
        revealed=b.revealed,
        share_token=b.share_token,
        share_token_b=b.share_token_b,
        created_at=b.created_at,
    )


# ---------- 仪表盘 ----------


@router.get("/stats", response_model=StatsOut)
async def admin_stats(
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StatsOut:
    """仪表盘统计：各表总数 + 对战状态分布 + 最近对战。"""
    total_users = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    total_abilities = (await db.execute(select(func.count()).select_from(Ability))).scalar_one()
    total_loadouts = (await db.execute(select(func.count()).select_from(Loadout))).scalar_one()
    total_battles = (await db.execute(select(func.count()).select_from(Battle))).scalar_one()

    status_counts = {s: 0 for s in ("pending", "done", "failed")}
    for s, c in (await db.execute(select(Battle.status, func.count()).group_by(Battle.status))).all():
        status_counts[s] = c

    recent = (
        (await db.execute(select(Battle).order_by(Battle.created_at.desc()).limit(RECENT_BATTLES)))
        .scalars()
        .all()
    )
    name_map = await _names(db, {b.user_a_id for b in recent} | {b.user_b_id for b in recent})
    recent_battles = [
        RecentBattle(
            id=b.id,
            user_a=name_map.get(b.user_a_id),
            user_b=name_map.get(b.user_b_id),
            winner=name_map.get(b.winner_id) if b.winner_id else None,
            status=b.status,
            friendly=b.friendly,
            created_at=b.created_at,
        )
        for b in recent
    ]

    return StatsOut(
        total_users=total_users,
        total_abilities=total_abilities,
        total_loadouts=total_loadouts,
        total_battles=total_battles,
        battles_pending=status_counts["pending"],
        battles_done=status_counts["done"],
        battles_failed=status_counts["failed"],
        recent_battles=recent_battles,
    )


# ---------- 用户 CRUD ----------


@router.get("/users", response_model=list[AdminUserOut])
async def admin_users(
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    search: str | None = Query(default=None, max_length=50, description="按用户名模糊搜索"),
) -> list[AdminUserOut]:
    """异闻师列表（附奇人/奇术/行迹计数），按 id 升序。"""
    loadout_cnt = select(func.count()).where(Loadout.user_id == User.id).scalar_subquery()
    ability_cnt = select(func.count()).where(UserAbility.user_id == User.id).scalar_subquery()
    battle_cnt = (
        select(func.count())
        .where(or_(Battle.user_a_id == User.id, Battle.user_b_id == User.id))
        .scalar_subquery()
    )
    q = select(User, loadout_cnt.label("lc"), ability_cnt.label("ac"), battle_cnt.label("bc"))
    if search:
        q = q.where(User.username.contains(search))
    q = q.order_by(User.id)
    rows = (await db.execute(q)).all()
    return [
        AdminUserOut(
            id=u.id,
            username=u.username,
            exp=u.exp,
            rank_points=u.rank_points,
            reveal_on_miss=u.reveal_on_miss,
            is_admin=u.is_admin,
            last_login_date=u.last_login_date,
            last_battle_date=u.last_battle_date,
            created_at=u.created_at,
            loadout_count=lc,
            ability_count=ac,
            battle_count=bc,
        )
        for u, lc, ac, bc in rows
    ]


@router.post("/users", response_model=AdminUserOut, status_code=status.HTTP_201_CREATED)
async def admin_create_user(
    body: AdminUserCreate,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminUserOut:
    """后台新建异闻师（可指定管理员权限与初始数值）。"""
    exists = await db.execute(select(User).where(User.username == body.username))
    if exists.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已被占用")
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        exp=body.exp,
        rank_points=body.rank_points,
        reveal_on_miss=body.reveal_on_miss,
        is_admin=body.is_admin,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已被占用")
    await db.refresh(user)
    return AdminUserOut(
        id=user.id,
        username=user.username,
        exp=user.exp,
        rank_points=user.rank_points,
        reveal_on_miss=user.reveal_on_miss,
        is_admin=user.is_admin,
        last_login_date=user.last_login_date,
        last_battle_date=user.last_battle_date,
        created_at=user.created_at,
    )


@router.put("/users/{user_id}", response_model=AdminUserOut)
async def admin_update_user(
    user_id: int,
    body: AdminUserUpdate,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminUserOut:
    """编辑异闻师：逐个应用非空字段；改密码则重哈希。守卫：不能取消自己的管理员权限。"""
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="异闻师不存在")
    if body.is_admin is False and user_id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能取消自己的管理员权限")
    if body.username is not None and body.username != user.username:
        clash = await db.execute(select(User).where(User.username == body.username, User.id != user_id))
        if clash.scalar_one_or_none() is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已被占用")
        user.username = body.username
    if body.password is not None:
        user.password_hash = hash_password(body.password)
    if body.exp is not None:
        user.exp = body.exp
    if body.rank_points is not None:
        user.rank_points = body.rank_points
    if body.reveal_on_miss is not None:
        user.reveal_on_miss = body.reveal_on_miss
    if body.is_admin is not None:
        user.is_admin = body.is_admin
    await db.commit()
    await db.refresh(user)
    return AdminUserOut(
        id=user.id,
        username=user.username,
        exp=user.exp,
        rank_points=user.rank_points,
        reveal_on_miss=user.reveal_on_miss,
        is_admin=user.is_admin,
        last_login_date=user.last_login_date,
        last_battle_date=user.last_battle_date,
        created_at=user.created_at,
    )


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_user(
    user_id: int,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """删除异闻师：级联清理其奇术关联、奇人、参与的对战与故人关系。守卫：不能删自己。"""
    if user_id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能删除自己的账号")
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="异闻师不存在")

    # 1. 参与的对战：先删对应的猜词状态，再删对战本身
    battle_ids = (
        await db.execute(
            select(Battle.id).where(or_(Battle.user_a_id == user_id, Battle.user_b_id == user_id))
        )
    ).scalars().all()
    if battle_ids:
        await db.execute(delete(BattleGuess).where(BattleGuess.battle_id.in_(battle_ids)))
        await db.execute(delete(Battle).where(Battle.id.in_(battle_ids)))

    # 2. 其奇人：置空其余战场的快照引用，删装配关系，删奇人
    loadout_ids = (await db.execute(select(Loadout.id).where(Loadout.user_id == user_id))).scalars().all()
    if loadout_ids:
        await db.execute(
            update(Battle).where(Battle.loadout_a_id.in_(loadout_ids)).values(loadout_a_id=None)
        )
        await db.execute(
            update(Battle).where(Battle.loadout_b_id.in_(loadout_ids)).values(loadout_b_id=None)
        )
        await db.execute(delete(LoadoutAbility).where(LoadoutAbility.loadout_id.in_(loadout_ids)))
        await db.execute(delete(Loadout).where(Loadout.id.in_(loadout_ids)))

    # 3. 奇术归属
    await db.execute(delete(UserAbility).where(UserAbility.user_id == user_id))

    # 4. 故人关系（双向）
    await db.execute(
        delete(Friendship).where(or_(Friendship.user_id == user_id, Friendship.friend_id == user_id))
    )

    # 4b. 其作为挑战者的点将看破进度（榜主侧进度随其榜单条目级联）
    await db.execute(delete(BoardGuessProgress).where(BoardGuessProgress.challenger_id == user_id))

    # 4c. 通知：删其收件箱；其作为触发者的通知置空 actor（保留接收方通知）
    await db.execute(delete(Notification).where(Notification.user_id == user_id))
    await db.execute(update(Notification).where(Notification.actor_id == user_id).values(actor_id=None))

    # 5. 请求日志软引用置空（保留审计历史）
    await db.execute(update(RequestLog).where(RequestLog.user_id == user_id).values(user_id=None))

    await db.delete(target)
    await db.commit()


# ---------- 异能 CRUD ----------


@router.get("/abilities", response_model=list[AbilityOut])
async def admin_abilities(
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Ability]:
    """奇术列表，按创建时间倒序。"""
    result = await db.execute(select(Ability).order_by(Ability.created_at.desc()))
    return list(result.scalars().all())


@router.post("/abilities", response_model=AbilityOut, status_code=status.HTTP_201_CREATED)
async def admin_create_ability(
    body: AbilityAdminIn,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Ability:
    """后台新建奇术（内容哈希去重，可挂到指定异闻师名下；调度因果槽位生成）。"""
    name, effect = body.name.strip(), body.effect.strip()
    if not name or not effect:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="奇术名称与效果不能为空")
    aid = _ability_id(name, effect)
    ability = await db.get(Ability, aid)
    if ability is None:
        ability = Ability(
            id=aid,
            name=name,
            effect=effect,
            detail=(body.detail or "").strip(),
        )
        db.add(ability)
        await db.flush()
    if body.owner_id is not None:
        owner = await db.get(User, body.owner_id)
        if owner is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="归属异闻师不存在")
        owns = await db.get(UserAbility, (body.owner_id, aid))
        if owns is None:
            db.add(UserAbility(user_id=body.owner_id, ability_id=aid))
    await db.commit()
    await db.refresh(ability)
    _schedule_understanding(ability.id)
    return ability


@router.put("/abilities/{ability_id}", response_model=AbilityOut)
async def admin_update_ability(
    ability_id: str,
    body: AbilityAdminIn,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Ability:
    """编辑奇术。"""
    ability = await db.get(Ability, ability_id)
    if ability is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="奇术不存在")
    name, effect = body.name.strip(), body.effect.strip()
    if not name or not effect:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="奇术名称与效果不能为空")
    detail = body.detail.strip() if body.detail is not None else ability.detail
    changed = (name, effect, detail) != (ability.name, ability.effect, ability.detail)
    ability.name, ability.effect = name, effect
    if body.detail is not None:
        ability.detail = detail
    await db.commit()
    await db.refresh(ability)
    if changed:  # 全字段无变化不触发因果推演
        _schedule_understanding(ability.id)
    return ability


@router.delete("/abilities/{ability_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_ability(
    ability_id: str,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """强制删除奇术：从所有异闻师与奇人中移除（管理员权限，与用户侧引用计数删除不同）。"""
    await db.execute(delete(UserAbility).where(UserAbility.ability_id == ability_id))
    await db.execute(delete(LoadoutAbility).where(LoadoutAbility.ability_id == ability_id))
    await db.execute(delete(TestLoadoutAbility).where(TestLoadoutAbility.ability_id == ability_id))
    ability = await db.get(Ability, ability_id)
    if ability is not None:
        await db.delete(ability)
    await db.commit()


@router.post("/abilities/backfill", status_code=status.HTTP_200_OK)
async def admin_backfill_understanding(
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, int]:
    """为所有尚无因果槽位的奇术调度后台生成（一次性补全旧数据）。"""
    rows = (await db.execute(select(Ability.id).where(Ability.understanding == ""))).scalars().all()
    for aid in rows:
        _schedule_understanding(aid)
    return {"scheduled": len(rows)}


# ---------- 对战：查看 + 删除 ----------


@router.get("/battles", response_model=list[AdminBattleOut])
async def admin_battles(
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AdminBattleOut]:
    """行迹列表（最近 100 场），story 为完整上帝视角。"""
    battles = (
        (await db.execute(select(Battle).order_by(Battle.created_at.desc()).limit(BATTLE_LIST_LIMIT)))
        .scalars()
        .all()
    )
    ids = set()
    for b in battles:
        ids.update((b.user_a_id, b.user_b_id))
        if b.winner_id:
            ids.add(b.winner_id)
        if b.guess_by:
            ids.add(b.guess_by)
    name_map = await _names(db, ids)
    return [_admin_battle_out(b, name_map) for b in battles]


@router.get("/battles/{battle_id}", response_model=AdminBattleOut)
async def admin_battle_detail(
    battle_id: int,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminBattleOut:
    """单场行迹详情（管理员上帝视角：完整 story 含双方奇术表与叙述）。"""
    battle = await db.get(Battle, battle_id)
    if battle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="行迹不存在")
    ids = {battle.user_a_id, battle.user_b_id}
    if battle.winner_id:
        ids.add(battle.winner_id)
    if battle.guess_by:
        ids.add(battle.guess_by)
    name_map = await _names(db, ids)
    # 猜词行一行一猜测者（和局两行）；优先取 battle.guess_by 指向的那行，兜底第一行
    rows = (
        (await db.execute(select(BattleGuess).where(BattleGuess.battle_id == battle_id)))
        .scalars()
        .all()
    )
    guess = next((r for r in rows if r.guesser_id == battle.guess_by), None) if battle.guess_by else None
    if guess is None and rows:
        guess = rows[0]
    guess_total = len(guess.used_abilities) if guess and guess.used_abilities else 0
    guess_cards = None
    if guess is not None and guess.used_abilities:
        guess_cards = [
            {
                "index": i + 1,
                "matched": c["matched"],
                "cracked": c["cracked"],
                "cracked_round": c.get("cracked_round"),
                "rounds": c.get("rounds") or [],
                "verifies": c.get("verifies") or [],
                **({"name": used["name"], "effect": used["effect"]} if c["cracked"] else {}),
            }
            for i, (c, used) in enumerate(zip(guess.cards, guess.used_abilities))
        ]
    return _admin_battle_out(
        battle,
        name_map,
        guess_history=list(guess.guess_history) if guess else [],
        guess_total=guess_total,
        guess_cards=guess_cards,
        guess_attempts_used=guess.attempts_used if guess else 0,
        guess_attempts_max=guess.attempts_max if guess else GUESS_ATTEMPTS_MAX,
    )


@router.delete("/battles/{battle_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_battle(
    battle_id: int,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """删除行迹（含对应猜词状态）。在途推演不可删（防破坏后台任务）。"""
    battle = await db.get(Battle, battle_id)
    if battle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="行迹不存在")
    if battle.status == "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="在途推演不可删除")
    # 复合主键 (battle_id, guesser_id)：删该场全部猜词行
    guesses = await db.execute(select(BattleGuess).where(BattleGuess.battle_id == battle_id))
    for guess in guesses.scalars().all():
        await db.delete(guess)
    await db.delete(battle)
    await db.commit()


# ---------- 奇人：查看 + 删除 ----------


@router.get("/loadouts", response_model=list[AdminLoadoutOut])
async def admin_loadouts(
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AdminLoadoutOut]:
    """奇人列表（含所装奇术、参战数），按创建时间倒序。"""
    ability_cnt = select(func.count()).where(LoadoutAbility.loadout_id == Loadout.id).scalar_subquery()
    battle_cnt = (
        select(func.count())
        .where(or_(Battle.loadout_a_id == Loadout.id, Battle.loadout_b_id == Loadout.id))
        .scalar_subquery()
    )
    rows = (
        await db.execute(
            select(Loadout, ability_cnt.label("ac"), battle_cnt.label("bc")).order_by(Loadout.created_at.desc())
        )
    ).all()
    name_map = await _names(db, {l.user_id for l, _, _ in rows})
    return [await _loadout_out(db, l, name_map.get(l.user_id), ac, bc) for l, ac, bc in rows]


async def _loadout_out(
    db: AsyncSession, l: Loadout, username: str | None, ability_count: int, battle_count: int
) -> AdminLoadoutOut:
    """序列化一个奇人（含按装配顺序的奇术）。"""
    ab_rows = await db.execute(
        select(Ability)
        .join(LoadoutAbility, LoadoutAbility.ability_id == Ability.id)
        .where(LoadoutAbility.loadout_id == l.id)
        .order_by(LoadoutAbility.added_at)
    )
    return AdminLoadoutOut(
        id=l.id,
        user_id=l.user_id,
        username=username,
        name=(l.name or "").strip() or "奇人",
        style=l.style,
        enabled=l.enabled,
        tactic=l.tactic,
        ability_count=ability_count,
        battle_count=battle_count,
        abilities=[AbilityOut.model_validate(a) for a in ab_rows.scalars().all()],
        created_at=l.created_at,
    )


@router.get("/loadouts/{loadout_id}", response_model=AdminLoadoutOut)
async def admin_loadout_detail(
    loadout_id: int,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminLoadoutOut:
    """单个奇人详情（含所装奇术、参战数）。"""
    loadout = await db.get(Loadout, loadout_id)
    if loadout is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="奇人不存在")
    ability_count = (
        await db.execute(select(func.count()).where(LoadoutAbility.loadout_id == loadout.id))
    ).scalar_one()
    battle_count = (
        await db.execute(
            select(func.count()).where(or_(Battle.loadout_a_id == loadout.id, Battle.loadout_b_id == loadout.id))
        )
    ).scalar_one()
    username = (await _names(db, {loadout.user_id})).get(loadout.user_id)
    return await _loadout_out(db, loadout, username, ability_count, battle_count)


@router.get("/loadouts/{loadout_id}/battles", response_model=list[AdminBattleOut])
async def admin_loadout_battles(
    loadout_id: int,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AdminBattleOut]:
    """某奇人参与过的全部行迹（甲乙任一侧），按创建时间倒序。"""
    loadout = await db.get(Loadout, loadout_id)
    if loadout is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="奇人不存在")
    battles = (
        (
            await db.execute(
                select(Battle)
                .where(or_(Battle.loadout_a_id == loadout_id, Battle.loadout_b_id == loadout_id))
                .order_by(Battle.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    ids = set()
    for b in battles:
        ids.update((b.user_a_id, b.user_b_id))
        if b.winner_id:
            ids.add(b.winner_id)
        if b.guess_by:
            ids.add(b.guess_by)
    name_map = await _names(db, ids)
    return [_admin_battle_out(b, name_map) for b in battles]


@router.delete("/loadouts/{loadout_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_loadout(
    loadout_id: int,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """删除奇人：置空行迹快照引用、清装配关系，再删本体（与用户侧同套级联）。"""
    loadout = await db.get(Loadout, loadout_id)
    if loadout is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="奇人不存在")
    await db.execute(update(Battle).where(Battle.loadout_a_id == loadout.id).values(loadout_a_id=None))
    await db.execute(update(Battle).where(Battle.loadout_b_id == loadout.id).values(loadout_b_id=None))
    await db.execute(delete(LoadoutAbility).where(LoadoutAbility.loadout_id == loadout.id))
    await db.delete(loadout)
    await db.commit()


# ---------- 故人：查看 + 删除 ----------


@router.get("/friendships", response_model=list[FriendshipRowOut])
async def admin_friendships(
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[FriendshipRowOut]:
    """故人关系列表。"""
    rows = (await db.execute(select(Friendship).order_by(Friendship.created_at.desc()))).scalars().all()
    ids = set()
    for f in rows:
        ids.update((f.user_id, f.friend_id))
    name_map = await _names(db, ids)
    return [
        FriendshipRowOut(
            user_id=f.user_id,
            friend_id=f.friend_id,
            user=name_map.get(f.user_id),
            friend=name_map.get(f.friend_id),
            status=f.status,
            created_at=f.created_at,
        )
        for f in rows
    ]


@router.delete("/friendships/{user_id}/{friend_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_friendship(
    user_id: int,
    friend_id: int,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """删除一条故人关系。"""
    friendship = await db.get(Friendship, (user_id, friend_id))
    if friendship is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="故人关系不存在")
    await db.delete(friendship)
    await db.commit()


# ---------- 流量 ----------


def _norm_path(path: str) -> str:
    """把路径里的数字段归一化为 {id}，让 /users/5 与 /users/9 归并统计。"""
    return "/".join("{id}" if seg.isdigit() else seg for seg in path.split("/"))


@router.get("/traffic", response_model=TrafficOut)
async def admin_traffic(
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TrafficOut:
    """流量总览：总量/近 24h/平均耗时 + 近 7 日序列 + 接口 TOP + 最近日志。"""
    total, avg = (
        await db.execute(select(func.count(), func.avg(RequestLog.duration_ms)).select_from(RequestLog))
    ).one()
    # 近 24h 与近 7 日：截止时间在 Python 侧计算（func.datetime("now", …) 是 SQLite 方言），
    # 按日聚合也在 Python 侧做（func.date 在 PG 下编译为 date()，不存在）。
    # created_at 列是无时区的 TIMESTAMP（func.now() 落 naive UTC），比较参数须同样 naive，否则
    # asyncpg 报 offset-naive/aware 不可相减。
    _now = datetime.now(UTC).replace(tzinfo=None)
    last_24h = (
        await db.execute(
            select(func.count())
            .select_from(RequestLog)
            .where(RequestLog.created_at >= _now - timedelta(days=1))
        )
    ).scalar_one()

    # 近 7 日序列（Python 侧按 UTC 零填充缺日）
    seven_days_cutoff = _now - timedelta(days=6)
    recent_ts = (
        (await db.execute(select(RequestLog.created_at).where(RequestLog.created_at >= seven_days_cutoff)))
        .scalars()
        .all()
    )
    daily_map = Counter(ts.replace(tzinfo=UTC).date().isoformat() for ts in recent_ts)
    today = datetime.now(UTC).date()
    daily = [
        DailyPoint(date=(today - timedelta(days=i)).isoformat(), count=daily_map.get((today - timedelta(days=i)).isoformat(), 0))
        for i in range(6, -1, -1)
    ]

    # 接口 TOP：先按原始 path 聚合，再归一化数字段合并
    ep_rows = (
        await db.execute(
            select(RequestLog.path, func.count().label("n"), func.avg(RequestLog.duration_ms).label("avg"))
            .group_by(RequestLog.path)
            .order_by(func.count().desc())
            .limit(50)
        )
    ).all()
    merged: dict[str, list[int | float]] = {}
    for path, n, ep_avg in ep_rows:
        key = _norm_path(path)
        acc = merged.setdefault(key, [0, 0.0])
        acc[0] += n
        acc[1] += float(ep_avg or 0) * n  # 加权平均（PG 下 func.avg 返回 Decimal，须转 float）
    endpoints = [
        EndpointStat(path=k, count=acc[0], avg_ms=acc[1] / acc[0])
        for k, acc in merged.items()
    ]
    endpoints.sort(key=lambda e: e.count, reverse=True)
    endpoints = endpoints[:ENDPOINT_TOP]

    recent = (
        (await db.execute(select(RequestLog).order_by(RequestLog.id.desc()).limit(50))).scalars().all()
    )

    return TrafficOut(
        total_requests=total,
        last_24h=last_24h,
        avg_ms=float(avg or 0.0),
        daily=daily,
        endpoints=endpoints,
        recent=[RequestLogOut.model_validate(r) for r in recent],
    )


# ---------- 对战试验场：纯测试，对玩家数据零持久性影响 ----------


def _test_user_out(u: TestUser) -> TestUserOut:
    return TestUserOut(
        id=u.id,
        username=u.username,
        exp=u.exp,
        rank_points=u.rank_points,
        created_at=u.created_at,
    )


@router.get("/test/users", response_model=list[TestUserOut])
async def admin_test_users(
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[TestUserOut]:
    """测试账号列表（按 id 序）。"""
    rows = (await db.execute(select(TestUser).order_by(TestUser.id))).scalars().all()
    return [_test_user_out(u) for u in rows]


@router.post("/test/users", response_model=TestUserOut, status_code=status.HTTP_201_CREATED)
async def admin_test_create_user(
    body: TestUserCreate,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TestUserOut:
    """新建测试账号；用户名缺省用词库自动起名。"""
    username = (body.username or "").strip()
    if not username:
        import random

        from scripts.namegen import gen_username

        username = gen_username(random.Random())
    exists = await db.execute(select(TestUser).where(TestUser.username == username))
    if exists.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="测试账号名已被占用")
    user = TestUser(username=username, exp=body.exp, rank_points=body.rank_points)
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="测试账号名已被占用")
    await db.refresh(user)
    return _test_user_out(user)


@router.delete("/test/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_test_delete_user(
    user_id: int,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """删除测试账号（级联删其参与的测试行迹、持久测试奇人与装配）。"""
    target = await db.get(TestUser, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="测试账号不存在")
    battle_ids = (
        await db.execute(
            select(TestBattle.id).where(or_(TestBattle.user_a_id == user_id, TestBattle.user_b_id == user_id))
        )
    ).scalars().all()
    if battle_ids:
        await db.execute(delete(TestBattleGuess).where(TestBattleGuess.battle_id.in_(battle_ids)))
        await db.execute(delete(TestBattle).where(TestBattle.id.in_(battle_ids)))
    loadout_ids = (
        await db.execute(select(TestLoadout.id).where(TestLoadout.user_id == user_id))
    ).scalars().all()
    if loadout_ids:
        await db.execute(delete(TestLoadoutAbility).where(TestLoadoutAbility.loadout_id.in_(loadout_ids)))
        await db.execute(delete(TestLoadout).where(TestLoadout.id.in_(loadout_ids)))
    await db.delete(target)
    await db.commit()


@router.get("/test/loadouts", response_model=list[TestLoadoutOut])
async def admin_test_loadouts(
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[TestLoadoutOut]:
    """持久测试奇人列表（含绑定账号名与装配奇术，倒序）。"""
    loadouts = (await db.execute(select(TestLoadout).order_by(TestLoadout.id.desc()))).scalars().all()
    if not loadouts:
        return []
    name_map = await _test_names(db, {l.user_id for l in loadouts})
    return [await _test_loadout_out(db, l, name_map.get(l.user_id)) for l in loadouts]


async def _test_loadout_out(db: AsyncSession, l: TestLoadout, username: str | None) -> TestLoadoutOut:
    """序列化一个持久测试奇人（含按装配顺序的奇术）。"""
    ab_rows = await db.execute(
        select(Ability)
        .join(TestLoadoutAbility, TestLoadoutAbility.ability_id == Ability.id)
        .where(TestLoadoutAbility.loadout_id == l.id)
        .order_by(TestLoadoutAbility.added_at)
    )
    return TestLoadoutOut(
        id=l.id,
        user_id=l.user_id,
        username=username,
        name=(l.name or "").strip() or "奇人",
        style=l.style,
        abilities=[AbilityOut.model_validate(a) for a in ab_rows.scalars().all()],
    )


@router.post("/test/loadouts", response_model=TestLoadoutOut, status_code=status.HTTP_201_CREATED)
async def admin_test_generate_loadout(
    body: TestLoadoutCreateIn,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TestLoadoutOut:
    """生成持久测试奇人：校验奇术 → 自动绑定新测试账号 → 词库随机起名（风格空）→ 落库。"""
    import random

    from scripts.namegen import gen_loadout_name, gen_username

    abilities: list[Ability] = []
    for aid in body.abilities:
        ability = await db.get(Ability, aid)
        if ability is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"奇术不存在: {aid}")
        abilities.append(ability)

    rng = random.Random()
    # 自动绑定账号：词库起名，撞车重抽
    while True:
        username = gen_username(rng)
        exists = await db.execute(select(TestUser).where(TestUser.username == username))
        if exists.scalar_one_or_none() is None:
            break
    user = TestUser(username=username)
    db.add(user)
    await db.flush()

    # 奇人名随机，唯一索引撞车重抽
    while True:
        name = gen_loadout_name(rng)
        exists = await db.execute(select(TestLoadout).where(TestLoadout.name == name))
        if exists.scalar_one_or_none() is None:
            break
    loadout = TestLoadout(user_id=user.id, name=name, style="")
    db.add(loadout)
    await db.flush()
    for ability in abilities:
        db.add(TestLoadoutAbility(loadout_id=loadout.id, ability_id=ability.id))
    await db.commit()
    await db.refresh(loadout)
    return await _test_loadout_out(db, loadout, user.username)


@router.delete("/test/loadouts/{loadout_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_test_delete_loadout(
    loadout_id: int,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """删除持久测试奇人：若绑定账号无其他奇人且无对局引用，一并删除（避免残留空号）。"""
    loadout = await db.get(TestLoadout, loadout_id)
    if loadout is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="测试奇人不存在")
    owner_id = loadout.user_id
    await db.execute(delete(TestLoadoutAbility).where(TestLoadoutAbility.loadout_id == loadout.id))
    await db.delete(loadout)
    # 绑定账号无其他奇人且未参与任何对局 → 一并清理
    has_other = (
        await db.execute(
            select(TestLoadout.id).where(TestLoadout.user_id == owner_id).limit(1)
        )
    ).scalar_one_or_none()
    has_battle = (
        await db.execute(
            select(TestBattle.id).where(or_(TestBattle.user_a_id == owner_id, TestBattle.user_b_id == owner_id)).limit(1)
        )
    ).scalar_one_or_none()
    if has_other is None and has_battle is None:
        owner = await db.get(TestUser, owner_id)
        if owner is not None:
            await db.delete(owner)
    await db.commit()


async def _resolve_fighter(
    db: AsyncSession,
    fighter: TestFighterIn,
    default_owner: TestUser,
) -> tuple[TestUser, str, list[Ability]]:
    """把一侧的奇人解析为 (测试账号, 奇人名, 奇术列表)。

    优先持久测试奇人（test_loadout_id，绑定账号随奇人）；其次玩家奇人（loadout_id）；
    最后临时内联（name+abilities，兼容测试保留）。
    """
    owner = default_owner
    if fighter.test_loadout_id is not None:
        loadout = await db.get(TestLoadout, fighter.test_loadout_id)
        if loadout is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="测试奇人不存在")
        owner = await db.get(TestUser, loadout.user_id)
        if owner is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="测试奇人绑定账号不存在")
        ab_rows = await db.execute(
            select(Ability)
            .join(TestLoadoutAbility, TestLoadoutAbility.ability_id == Ability.id)
            .where(TestLoadoutAbility.loadout_id == loadout.id)
            .order_by(TestLoadoutAbility.added_at)
        )
        abilities = list(ab_rows.scalars().all())
        name = (loadout.name or "").strip() or "奇人"
    else:
        if fighter.owner:
            row = await db.execute(select(TestUser).where(TestUser.username == fighter.owner))
            owner = row.scalar_one_or_none()
            if owner is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"测试账号不存在: {fighter.owner}")
        if fighter.loadout_id is not None:
            loadout = await db.get(Loadout, fighter.loadout_id)
            if loadout is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="奇人不存在")
            ab_rows = await db.execute(
                select(Ability)
                .join(LoadoutAbility, LoadoutAbility.ability_id == Ability.id)
                .where(LoadoutAbility.loadout_id == loadout.id)
                .order_by(LoadoutAbility.added_at)
            )
            abilities = list(ab_rows.scalars().all())
            name = (loadout.name or "").strip() or "奇人"
        else:
            abilities = []
            for aid in fighter.abilities:
                ability = await db.get(Ability, aid)
                if ability is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"奇术不存在: {aid}")
                abilities.append(ability)
            name = (fighter.name or "").strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="奇人缺少名字")
    if not abilities:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="奇人缺少奇术（至少一门）")
    return owner, name, abilities


async def _test_battle_out_full(db: AsyncSession, battle: TestBattle) -> TestBattleOut:
    """测试行迹完整序列化（含双方测试账号名、奇人名、猜词状态）。"""
    ids = {battle.user_a_id, battle.user_b_id}
    if battle.winner_id:
        ids.add(battle.winner_id)
    if battle.guess_by:
        ids.add(battle.guess_by)
    name_map = await _test_names(db, ids)
    guess = await db.get(TestBattleGuess, battle.id)
    guess_total = len(guess.used_abilities) if guess and guess.used_abilities else 0
    guess_cards = None
    if guess is not None and guess.used_abilities:
        guess_cards = [
            {
                "index": i + 1,
                "matched": c["matched"],
                "cracked": c["cracked"],
                "cracked_round": c.get("cracked_round"),
                "rounds": c.get("rounds") or [],
                "verifies": c.get("verifies") or [],
                **({"name": used["name"], "effect": used["effect"]} if c["cracked"] else {}),
            }
            for i, (c, used) in enumerate(zip(guess.cards, guess.used_abilities))
        ]
    return TestBattleOut(
        id=battle.id,
        user_a=name_map.get(battle.user_a_id, "?"),
        user_b=name_map.get(battle.user_b_id, "?"),
        fighter_a=battle.loadout_a_name or "?",
        fighter_b=battle.loadout_b_name or "?",
        status=battle.status,
        winner=name_map.get(battle.winner_id) if battle.winner_id else None,
        winner_fighter=(
            (battle.loadout_a_name or None) if battle.winner_id == battle.user_a_id
            else ((battle.loadout_b_name or None) if battle.winner_id == battle.user_b_id else None)
        ),
        story=_load_story(battle.story),
        rank_delta_a=battle.rank_delta_a,
        rank_delta_b=battle.rank_delta_b,
        guess_by=name_map.get(battle.guess_by) if battle.guess_by else None,
        guess_state=battle.guess_state,
        guess_hit=battle.guess_hit,
        guess_score=battle.guess_score,
        revealed=battle.revealed,
        guess_history=list(guess.guess_history) if guess else [],
        guess_total=guess_total,
        guess_cards=guess_cards,
        guess_attempts_used=guess.attempts_used if guess else 0,
        guess_attempts_max=guess.attempts_max if guess else GUESS_ATTEMPTS_MAX,
        created_at=battle.created_at,
    )


@router.post("/test/battles", response_model=TestBattleOut, status_code=status.HTTP_201_CREATED)
async def admin_test_start_battle(
    body: TestBattleStartIn,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TestBattleOut:
    """真实推演一场测试对战：建 pending，后台跑推演 + 结算（只落 test_* 表）。"""
    user_a, name_a, abilities_a = await _resolve_fighter(db, body.fighter_a, await _default_test_user(db))
    user_b, name_b, abilities_b = await _resolve_fighter(db, body.fighter_b, user_a)
    if name_a == name_b:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="双方奇人同名，请改名后重试")
    battle = TestBattle(
        user_a_id=user_a.id,
        user_b_id=user_b.id,
        status="pending",
        story="",
        loadout_a_name=name_a,
        loadout_b_name=name_b,
    )
    db.add(battle)
    await db.commit()
    await db.refresh(battle)

    task = asyncio.create_task(
        resolve_test_battle_from_deduction(
            battle.id,
            ability_ids_a=[a.id for a in abilities_a],
            ability_ids_b=[a.id for a in abilities_b],
            style_a=body.fighter_a.style or "",
            style_b=body.fighter_b.style or "",
        )
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return await _test_battle_out_full(db, battle)


@router.post("/test/battles/report", response_model=TestReportOut)
async def admin_test_generate_report(
    body: TestBattleStartIn,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TestReportOut:
    """仅生成战前讨论报告（不推演、不落库）：复用讨论节点与推演同一套信息组装。"""
    user_a, name_a, abilities_a = await _resolve_fighter(db, body.fighter_a, await _default_test_user(db))
    _, name_b, abilities_b = await _resolve_fighter(db, body.fighter_b, user_a)
    if name_a == name_b:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="双方奇人同名，请改名后重试")
    report = await generate_test_discuss_report(
        fighter_a=name_a,
        fighter_b=name_b,
        abilities_a=abilities_a,
        abilities_b=abilities_b,
        style_a=body.fighter_a.style or "",
        style_b=body.fighter_b.style or "",
    )
    return TestReportOut(report=report)


@router.post("/test/battles/skip", response_model=TestBattleOut, status_code=status.HTTP_201_CREATED)
async def admin_test_skip_battle(
    body: TestSkipIn,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TestBattleOut:
    """跳过对战直接指定胜负：零 LLM，直接进猜词阶段（默认全部奇术被使用）。"""
    if body.winner not in ("A", "B", "draw"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="winner 须为 A / B / draw")
    user_a, name_a, abilities_a = await _resolve_fighter(db, body.fighter_a, await _default_test_user(db))
    user_b, name_b, abilities_b = await _resolve_fighter(db, body.fighter_b, user_a)
    if name_a == name_b:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="双方奇人同名，请改名后重试")
    battle = await resolve_test_battle(
        db,
        user_a=user_a,
        user_b=user_b,
        fighter_a=name_a,
        fighter_b=name_b,
        abilities_a=abilities_a,
        abilities_b=abilities_b,
        winner_side=body.winner,
    )
    return await _test_battle_out_full(db, battle)


@router.get("/test/battles", response_model=list[TestBattleOut])
async def admin_test_battles(
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[TestBattleOut]:
    """测试行迹列表（倒序）。"""
    rows = (await db.execute(select(TestBattle).order_by(TestBattle.id.desc()).limit(50))).scalars().all()
    return [await _test_battle_out_full(db, b) for b in rows]


@router.get("/test/battles/{battle_id}", response_model=TestBattleOut)
async def admin_test_battle_detail(
    battle_id: int,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TestBattleOut:
    """单场测试行迹详情。"""
    battle = await db.get(TestBattle, battle_id)
    if battle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="测试行迹不存在")
    return await _test_battle_out_full(db, battle)


@router.post("/test/battles/{battle_id}/guess", response_model=TestBattleOut)
async def admin_test_guess(
    battle_id: int,
    body: TestGuessIn,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TestBattleOut:
    """对测试行迹猜奇术（复用三环节，只更新 test_* 表）。"""
    battle = await db.get(TestBattle, battle_id)
    if battle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="测试行迹不存在")
    guesser = await db.get(TestUser, battle.guess_by or 0)
    if guesser is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="本场无败方可猜")
    try:
        await submit_test_guess(db, battle, guesser, body.text)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return await _test_battle_out_full(db, battle)


@router.delete("/test/battles/{battle_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_test_delete_battle(
    battle_id: int,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """删除测试行迹（含猜词状态）。"""
    battle = await db.get(TestBattle, battle_id)
    if battle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="测试行迹不存在")
    guess = await db.get(TestBattleGuess, battle_id)
    if guess is not None:
        await db.delete(guess)
    await db.delete(battle)
    await db.commit()


async def _default_test_user(db: AsyncSession) -> TestUser:
    """取第一个测试账号兜底；一个都没有时自动建一个（词库起名），保证试验场可即开即用。"""
    row = (await db.execute(select(TestUser).order_by(TestUser.id).limit(1))).scalar_one_or_none()
    if row is not None:
        return row
    import random

    from scripts.namegen import gen_username

    user = TestUser(username=gen_username(random.Random()))
    db.add(user)
    await db.flush()
    return user


# ---------- LLM 链路追踪 ----------


@router.get("/llm-traces", response_model=list[LlmTraceOut])
async def admin_llm_traces(
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    operation: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    trace_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[LlmTraceOut]:
    """LLM 调用追踪列表（按 id 倒序，支持按环节/场景/业务 id 过滤）。"""
    stmt = select(LlmTrace)
    if operation:
        stmt = stmt.where(LlmTrace.operation == operation)
    if kind:
        stmt = stmt.where(LlmTrace.kind == kind)
    if trace_id:
        stmt = stmt.where(LlmTrace.trace_id == trace_id)
    rows = (
        (await db.execute(stmt.order_by(LlmTrace.id.desc()).limit(limit).offset(offset)))
        .scalars()
        .all()
    )
    return [LlmTraceOut.model_validate(r) for r in rows]


@router.get("/llm-traces/stats", response_model=LlmTraceStatsOut)
async def admin_llm_trace_stats(
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LlmTraceStatsOut:
    """LLM 调用聚合：总量 / 失败量 + 按环节分组的调用数、失败数、平均耗时。

    注意：必须注册在 /llm-traces/{trace_id}（int 路径参数）之前，否则 "stats" 会被当作 trace_id 解析。
    """
    total, fail_total = (
        await db.execute(
            select(func.count(), func.sum(case((LlmTrace.status == "fail", 1), else_=0))).select_from(LlmTrace)
        )
    ).one()
    op_rows = (
        await db.execute(
            select(
                LlmTrace.operation,
                func.count().label("cnt"),
                func.sum(case((LlmTrace.status == "fail", 1), else_=0)).label("fails"),
                func.avg(LlmTrace.latency_ms).label("avg"),
            )
            .group_by(LlmTrace.operation)
            .order_by(func.count().desc())
        )
    ).all()
    return LlmTraceStatsOut(
        total=int(total or 0),
        fail_total=int(fail_total or 0),
        by_operation=[
            LlmTraceOpStat(
                operation=op,
                count=int(cnt or 0),
                fail_count=int(fails or 0),
                avg_ms=float(avg or 0.0),
            )
            for op, cnt, fails, avg in op_rows
        ],
    )


@router.get("/llm-traces/{trace_id}", response_model=LlmTraceDetailOut)
async def admin_llm_trace_detail(
    trace_id: int,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LlmTraceDetailOut:
    """单条 LLM 追踪详情（含完整请求输入与模型输出）。"""
    trace = await db.get(LlmTrace, trace_id)
    if trace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="追踪记录不存在")
    return LlmTraceDetailOut.model_validate(trace)


# ---------- 提示词方案调试 ----------


async def _debug_run_out(db: AsyncSession, run: PromptDebugRun) -> PromptDebugRunOut:
    """调试记录 → 输出 schema：解析 story JSON + 关联方案名。"""
    scheme = await db.get(PromptScheme, run.scheme_id)
    return PromptDebugRunOut(
        id=run.id,
        battle_id=run.battle_id,
        scheme_id=run.scheme_id,
        scheme_name=scheme.name if scheme else None,
        status=run.status,
        error=run.error,
        story=_load_story(run.story),
        discuss_report=run.discuss_report,
        winner_side=run.winner_side,
        created_at=run.created_at,
    )


@router.get("/prompt-schemes", response_model=list[PromptSchemeOut])
async def admin_prompt_schemes(
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[PromptSchemeOut]:
    """提示词方案列表（按创建顺序）。"""
    rows = (await db.execute(select(PromptScheme).order_by(PromptScheme.id))).scalars().all()
    return [PromptSchemeOut.model_validate(r) for r in rows]


@router.post("/prompt-schemes", response_model=PromptSchemeOut, status_code=status.HTTP_201_CREATED)
async def admin_create_prompt_scheme(
    data: PromptSchemeIn,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PromptSchemeOut:
    """新建方案：name 唯一，各环节提示词空/None = 冻结默认。"""
    try:
        scheme = PromptScheme(**data.model_dump())
        db.add(scheme)
        await db.commit()
        await db.refresh(scheme)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="方案名已存在") from None
    return PromptSchemeOut.model_validate(scheme)


@router.patch("/prompt-schemes/{scheme_id}", response_model=PromptSchemeOut)
async def admin_update_prompt_scheme(
    scheme_id: int,
    data: PromptSchemeUpdate,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PromptSchemeOut:
    """更新方案：只改传入字段（None 保持原值；空字符串 = 清空覆盖、回冻结默认）。"""
    scheme = await db.get(PromptScheme, scheme_id)
    if scheme is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="方案不存在")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(scheme, field, value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="方案名已存在") from None
    await db.refresh(scheme)
    return PromptSchemeOut.model_validate(scheme)


@router.delete("/prompt-schemes/{scheme_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_prompt_scheme(
    scheme_id: int,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """删除方案：一并清理其调试记录（对齐 SQLite 无级联的手动清理模式）。"""
    scheme = await db.get(PromptScheme, scheme_id)
    if scheme is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="方案不存在")
    await db.execute(delete(PromptDebugRun).where(PromptDebugRun.scheme_id == scheme_id))
    await db.delete(scheme)
    await db.commit()


@router.post("/battles/{battle_id}/rerun", response_model=PromptDebugRunOut, status_code=status.HTTP_201_CREATED)
async def admin_rerun_battle(
    battle_id: int,
    data: RerunIn,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PromptDebugRunOut:
    """用指定方案重跑一场行迹：建 pending 调试记录并后台推演，接口立即返回。"""
    battle = await db.get(Battle, battle_id)
    if battle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="行迹不存在")
    scheme = await db.get(PromptScheme, data.scheme_id)
    if scheme is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="方案不存在")
    run = await rerun_battle(db, battle_id, data.scheme_id)
    return await _debug_run_out(db, run)


@router.get("/prompt-debug-runs", response_model=list[PromptDebugRunOut])
async def admin_prompt_debug_runs(
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    battle_id: int | None = Query(default=None),
) -> list[PromptDebugRunOut]:
    """调试记录列表：按战场筛选（默认全部），新→旧。"""
    stmt = select(PromptDebugRun)
    if battle_id is not None:
        stmt = stmt.where(PromptDebugRun.battle_id == battle_id)
    rows = (await db.execute(stmt.order_by(PromptDebugRun.id.desc()))).scalars().all()
    return [await _debug_run_out(db, r) for r in rows]


@router.get("/prompt-debug-runs/{run_id}", response_model=PromptDebugRunOut)
async def admin_prompt_debug_run_detail(
    run_id: int,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PromptDebugRunOut:
    """单条调试记录详情（含重跑产物三视角全文）。"""
    run = await db.get(PromptDebugRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="调试记录不存在")
    return await _debug_run_out(db, run)


@router.delete("/prompt-debug-runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_prompt_debug_run(
    run_id: int,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """删除单条调试记录（重跑产物是独立调试数据，可随时清理）。"""
    run = await db.get(PromptDebugRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="调试记录不存在")
    await db.delete(run)
    await db.commit()
