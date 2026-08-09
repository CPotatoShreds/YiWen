"""后台管理路由：仪表盘 / 数据库 CRUD / 流量。全部要求管理员权限。

- 用户、异能：完整增删改查
- 对战、奇人、故人：查看 + 删除
- SQLite 未开 foreign_keys、FK 均无 ondelete → 删除一律手动清理依赖行（仿
  app/api/routes/loadouts.py 与 abilities.py 的既有模式）
"""

import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_admin, hash_password
from app.db.base import get_db
from app.models.ability import Ability
from app.models.battle import Battle, BattleGuess
from app.models.friendship import Friendship
from app.models.loadout import Loadout, LoadoutAbility
from app.models.request_log import RequestLog
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
    RecentBattle,
    RequestLogOut,
    StatsOut,
    TrafficOut,
)

router = APIRouter(prefix="/admin", tags=["admin"])

RECENT_BATTLES = 10  # 仪表盘最近场数
BATTLE_LIST_LIMIT = 100  # 行迹列表上限
ENDPOINT_TOP = 12  # 接口流量 TOP 数量


def _ability_id(name: str, effect: str) -> str:
    """后台创建的奇术 id：内容哈希（管理员域内同内容去重）。"""
    return sha256(f"admin:{name}:{effect}".encode()).hexdigest()[:16]


async def _names(db: AsyncSession, ids: set[int]) -> dict[int, str]:
    """批量解析用户 id → 用户名（删过的用户兜底跳过）。"""
    if not ids:
        return {}
    rows = await db.execute(select(User).where(User.id.in_(ids)))
    return {u.id: u.username for u in rows.scalars().all()}


def _load_story(raw: str) -> dict | None:
    """解析 story JSON；空串 / 坏 JSON 兜底 None。"""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


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
    """后台新建奇术（内容哈希去重，可挂到指定异闻师名下；不调度 LLM 理解）。"""
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
            tactic=(body.tactic or "").strip(),
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
    return ability


@router.put("/abilities/{ability_id}", response_model=AbilityOut)
async def admin_update_ability(
    ability_id: str,
    body: AbilityAdminIn,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Ability:
    """编辑奇术：内容变更后旧理解失效（清空，不调度 LLM 重新生成）。"""
    ability = await db.get(Ability, ability_id)
    if ability is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="奇术不存在")
    name, effect = body.name.strip(), body.effect.strip()
    if not name or not effect:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="奇术名称与效果不能为空")
    ability.name, ability.effect = name, effect
    if body.detail is not None:
        ability.detail = body.detail.strip()
    if body.tactic is not None:
        ability.tactic = body.tactic.strip()
    ability.understanding = ""
    await db.commit()
    await db.refresh(ability)
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
    ability = await db.get(Ability, ability_id)
    if ability is not None:
        await db.delete(ability)
    await db.commit()


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
    return [
        AdminBattleOut(
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
            revealed=b.revealed,
            share_token=b.share_token,
            share_token_b=b.share_token_b,
            created_at=b.created_at,
        )
        for b in battles
    ]


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
    return AdminBattleOut(
        id=battle.id,
        user_a=name_map.get(battle.user_a_id),
        user_b=name_map.get(battle.user_b_id),
        winner=name_map.get(battle.winner_id) if battle.winner_id else None,
        status=battle.status,
        friendly=battle.friendly,
        story=_load_story(battle.story),
        rank_delta_a=battle.rank_delta_a,
        rank_delta_b=battle.rank_delta_b,
        loadout_a_id=battle.loadout_a_id,
        loadout_b_id=battle.loadout_b_id,
        guess_by=name_map.get(battle.guess_by) if battle.guess_by else None,
        guess_state=battle.guess_state,
        guess_hit=battle.guess_hit,
        guess_score=battle.guess_score,
        revealed=battle.revealed,
        share_token=battle.share_token,
        share_token_b=battle.share_token_b,
        created_at=battle.created_at,
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
    guess = await db.get(BattleGuess, battle_id)
    if guess is not None:
        await db.delete(guess)
    await db.delete(battle)
    await db.commit()


# ---------- 奇人：查看 + 删除 ----------


@router.get("/loadouts", response_model=list[AdminLoadoutOut])
async def admin_loadouts(
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AdminLoadoutOut]:
    """奇人列表（含所装奇术数），按创建时间倒序。"""
    ability_cnt = select(func.count()).where(LoadoutAbility.loadout_id == Loadout.id).scalar_subquery()
    rows = (await db.execute(select(Loadout, ability_cnt.label("ac")).order_by(Loadout.created_at.desc()))).all()
    name_map = await _names(db, {l.user_id for l, _ in rows})
    return [
        AdminLoadoutOut(
            id=l.id,
            user_id=l.user_id,
            username=name_map.get(l.user_id),
            name=l.name,
            style=l.style,
            enabled=l.enabled,
            tactic=l.tactic,
            ability_count=ac,
            created_at=l.created_at,
        )
        for l, ac in rows
    ]


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
    last_24h = (
        await db.execute(
            select(func.count())
            .select_from(RequestLog)
            .where(RequestLog.created_at >= func.datetime("now", "-1 day"))
        )
    ).scalar_one()

    # 近 7 日序列（SQLite 侧按日聚合，Python 侧按 UTC 零填充缺日）
    daily_rows = (
        await db.execute(
            select(func.date(RequestLog.created_at).label("day"), func.count())
            .where(RequestLog.created_at >= func.datetime("now", "-6 days"))
            .group_by(func.date(RequestLog.created_at))
        )
    ).all()
    daily_map = {day: cnt for day, cnt in daily_rows}
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
        acc[1] += (ep_avg or 0) * n  # 加权平均
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
