"""管理员 API：用户、奇术、流量与 LLM 追踪（写操作全部审计留痕）。"""
import asyncio
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import audit
from app.core.security import get_current_admin, hash_password
from app.db.base import get_db
from app.models.ability import Ability
from app.models.admin_audit import AdminAuditLog
from app.models.character import CharacterAbility
from app.models.llm_trace import LlmTrace
from app.models.request_log import RequestLog
from app.models.user import ROLE_ADMIN, ROLE_USER, User
from app.schemas.admin import (
    AbilityAdminIn,
    AdminUserCreate,
    AdminUserOut,
    AdminUserUpdate,
    DailyPoint,
    EndpointStat,
    LlmTraceDetailOut,
    LlmTraceOpStat,
    LlmTraceOut,
    LlmTraceStatsOut,
    StatsOut,
    TrafficOut,
)
from app.schemas.creator import AbilityOut
from app.services.ability.understanding import ensure_ability_understanding

router = APIRouter(prefix="/admin", tags=["admin"])
_tasks: set[asyncio.Task] = set()


def _schedule(aid: str) -> None:
    task = asyncio.create_task(ensure_ability_understanding(aid))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


@router.get("/stats", response_model=StatsOut)
async def stats(admin: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)]):
    return StatsOut(total_users=await db.scalar(select(func.count()).select_from(User)), total_abilities=await db.scalar(select(func.count()).select_from(Ability)))


@router.get("/users", response_model=list[AdminUserOut])
async def users(
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    search: str | None = Query(default=None, max_length=50),
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    q = select(User).order_by(User.id)
    if search:
        q = q.where(User.username.contains(search))
    if offset:
        q = q.offset(offset)
    if limit:
        q = q.limit(limit)
    rows = (await db.scalars(q)).all()
    counts = dict((await db.execute(select(Ability.owner_id, func.count()).group_by(Ability.owner_id))).all())
    return [AdminUserOut(id=u.id, username=u.username, is_admin=u.is_admin, created_at=u.created_at, ability_count=counts.get(u.id, 0)) for u in rows]


@router.post("/users", response_model=AdminUserOut, status_code=201)
async def create_user(body: AdminUserCreate, admin: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)]):
    user = User(username=body.username, password_hash=await hash_password(body.password), role=ROLE_ADMIN if body.is_admin else ROLE_USER)
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(400, "用户名已被占用")
    await db.refresh(user)
    await audit(db, admin.id, "user.create", target_type="user", target_id=user.id, detail={"username": user.username, "role": user.role})
    await db.commit()
    return AdminUserOut(id=user.id, username=user.username, is_admin=user.is_admin, created_at=user.created_at)


@router.put("/users/{user_id}", response_model=AdminUserOut)
async def update_user(user_id: int, body: AdminUserUpdate, admin: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)]):
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "异闻师不存在")
    if body.is_admin is False and user_id == admin.id:
        raise HTTPException(400, "不能取消自己的管理员权限")
    changes: dict = {}
    if body.username is not None and body.username != user.username:
        user.username = body.username
        changes["username"] = True
    if body.password is not None:
        user.password_hash = await hash_password(body.password)
        changes["password_reset"] = True
    if body.is_admin is not None:
        user.role = ROLE_ADMIN if body.is_admin else ROLE_USER
        changes["role"] = user.role
    await audit(db, admin.id, "user.update", target_type="user", target_id=user_id, detail=changes)
    await db.commit()
    await db.refresh(user)
    return AdminUserOut(id=user.id, username=user.username, is_admin=user.is_admin, created_at=user.created_at)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: int, admin: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)]):
    if user_id == admin.id:
        raise HTTPException(400, "不能删除自己的账号")
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "异闻师不存在")
    await db.execute(update(RequestLog).where(RequestLog.user_id == user_id).values(user_id=None))
    await db.delete(user)
    await audit(db, admin.id, "user.delete", target_type="user", target_id=user_id, detail={"username": user.username})
    await db.commit()


@router.get("/abilities", response_model=list[AbilityOut])
async def abilities(
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    q = select(Ability).order_by(Ability.created_at.desc())
    if offset:
        q = q.offset(offset)
    if limit:
        q = q.limit(limit)
    return list((await db.scalars(q)).all())


@router.post("/abilities", response_model=AbilityOut, status_code=201)
async def create_ability(body: AbilityAdminIn, admin: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)]):
    owner_id = body.owner_id if body.owner_id is not None else admin.id
    if await db.get(User, owner_id) is None:
        raise HTTPException(400, "必须指定存在的奇术主人")
    ability = Ability(owner_id=owner_id, name=body.name.strip(), effect=body.effect.strip(), detail=(body.detail or "").strip())
    db.add(ability)
    await db.commit()
    await db.refresh(ability)
    await audit(db, admin.id, "ability.create", target_type="ability", target_id=ability.id, detail={"name": ability.name, "owner_id": owner_id})
    await db.commit()
    _schedule(ability.id)
    return ability


@router.put("/abilities/{ability_id}", response_model=AbilityOut)
async def update_ability(ability_id: str, body: AbilityAdminIn, admin: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)]):
    ability = await db.get(Ability, ability_id)
    if ability is None:
        raise HTTPException(404, "奇术不存在")
    ability.name, ability.effect = body.name.strip(), body.effect.strip()
    ability.detail = body.detail.strip() if body.detail is not None else ability.detail
    await audit(db, admin.id, "ability.update", target_type="ability", target_id=ability_id, detail={"name": ability.name})
    await db.commit()
    await db.refresh(ability)
    _schedule(ability.id)
    return ability


@router.delete("/abilities/{ability_id}", status_code=204)
async def delete_ability(ability_id: str, admin: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)]):
    ability = await db.get(Ability, ability_id)
    if ability:
        await db.execute(delete(CharacterAbility).where(CharacterAbility.ability_id == ability.id))
        await db.delete(ability)
        await audit(db, admin.id, "ability.delete", target_type="ability", target_id=ability_id, detail={"name": ability.name})
    await db.commit()


@router.post("/abilities/backfill")
async def backfill(admin: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)]):
    ids = list((await db.scalars(select(Ability.id).where(Ability.understanding == ""))).all())
    await audit(db, admin.id, "ability.backfill", target_type="ability", detail={"scheduled": len(ids)})
    await db.commit()
    for aid in ids:
        _schedule(aid)
    return {"scheduled": len(ids)}


@router.get("/audit-logs")
async def audit_logs(
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    rows = (await db.scalars(select(AdminAuditLog).order_by(AdminAuditLog.id.desc()).offset(offset).limit(limit))).all()
    return [
        {"id": r.id, "operator_id": r.operator_id, "action": r.action, "target_type": r.target_type,
         "target_id": r.target_id, "detail": r.detail, "created_at": r.created_at}
        for r in rows
    ]


def _norm(path: str) -> str:
    return re.sub(r"/\d+(?=/|$)", "/{id}", path)


@router.get("/traffic", response_model=TrafficOut)
async def traffic(admin: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)]):
    now = datetime.now(UTC).replace(tzinfo=None)
    rows = list((await db.scalars(select(RequestLog).order_by(RequestLog.created_at.desc()).limit(1000))).all())
    recent = rows[:50]
    daily = Counter(r.created_at.date().isoformat() for r in rows if r.created_at and r.created_at >= now - timedelta(days=7))
    groups = Counter(_norm(r.path) for r in rows)
    endpoints = [EndpointStat(path=p, count=c, avg_ms=sum(r.duration_ms for r in rows if _norm(r.path) == p) / c) for p, c in groups.most_common(12)]
    return TrafficOut(
        total_requests=len(rows),
        last_24h=sum(1 for r in rows if r.created_at and r.created_at >= now - timedelta(hours=24)),
        avg_ms=(sum(r.duration_ms for r in rows) / len(rows) if rows else 0),
        daily=[DailyPoint(date=(now - timedelta(days=i)).date().isoformat(), count=daily[(now - timedelta(days=i)).date().isoformat()]) for i in range(6, -1, -1)],
        endpoints=endpoints,
        recent=recent,
    )


@router.get("/llm-traces", response_model=list[LlmTraceOut])
async def llm_traces(
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    return list((await db.scalars(select(LlmTrace).order_by(LlmTrace.created_at.desc()).offset(offset).limit(limit))).all())


@router.get("/llm-traces/stats", response_model=LlmTraceStatsOut)
async def llm_trace_stats(admin: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)]):
    rows = list((await db.scalars(select(LlmTrace))).all())
    by: dict = {}
    for r in rows:
        by.setdefault(r.operation, []).append(r)
    return LlmTraceStatsOut(
        total=len(rows),
        fail_total=sum(r.status != "ok" for r in rows),
        by_operation=[LlmTraceOpStat(operation=k, count=len(v), fail_count=sum(x.status != "ok" for x in v), avg_ms=sum(x.latency_ms for x in v) / len(v)) for k, v in by.items()],
    )


@router.get("/llm-traces/{trace_id}", response_model=LlmTraceDetailOut)
async def llm_trace(trace_id: int, admin: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)]):
    item = await db.get(LlmTrace, trace_id)
    if item is None:
        raise HTTPException(404, "追踪记录不存在")
    return item
