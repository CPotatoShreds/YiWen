"""奇人路由：每位异闻师初始 3 位奇人，解封开关、装入奇术，按见闻解锁更多槽位。

- enabled（解封）：解封 = 可主动启程，且进入台下听客。
- 槽位上限：见闻未达标不能新增奇人（见 models.user.loadout_capacity），后端 400。
- 解封强校验：至少装入一个奇术，否则后端 400（前端同样拦截）。
- 风格/战术/装配变更后后台重算「解读」（剔除装配清单外奇术的注入，见 loadout_interpretation）。
"""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.base import get_db
from app.models.ability import Ability
from app.models.battle import Battle
from app.models.loadout import Loadout, LoadoutAbility
from app.models.user import User, loadout_capacity
from app.models.user_ability import UserAbility
from app.schemas.ability import AbilityOut
from app.schemas.loadout import LoadoutOut, LoadoutSetIn
from app.services.loadout_interpretation import ensure_loadout_interpretation

router = APIRouter(prefix="/loadouts", tags=["loadouts"])

# 持有后台任务引用，防止 asyncio 在任务完成前 GC 取消它
_background_tasks: set[asyncio.Task] = set()


def _schedule_interpretation(loadout_id: int) -> None:
    """后台异步重算奇人风格/战术解读（失败静默，不阻塞用户操作）。"""
    task = asyncio.create_task(ensure_loadout_interpretation(loadout_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _get_owned_loadout(db: AsyncSession, loadout_id: int, user: User) -> Loadout:
    loadout = await db.get(Loadout, loadout_id)
    if loadout is None or loadout.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="奇人不存在")
    return loadout


async def _loadout_out(db: AsyncSession, loadout: Loadout) -> LoadoutOut:
    result = await db.execute(
        select(Ability)
        .join(LoadoutAbility, LoadoutAbility.ability_id == Ability.id)
        .where(LoadoutAbility.loadout_id == loadout.id)
        .order_by(LoadoutAbility.added_at)
    )
    abilities = [AbilityOut.model_validate(a) for a in result.scalars().all()]
    return LoadoutOut(
        id=loadout.id,
        name=loadout.name,
        style=loadout.style,
        enabled=loadout.enabled,
        tactic=loadout.tactic,
        abilities=abilities,
    )


@router.get("", response_model=list[LoadoutOut])
async def my_loadouts(
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[LoadoutOut]:
    """我的奇人（按 id 序）。"""
    result = await db.execute(select(Loadout).where(Loadout.user_id == current.id).order_by(Loadout.id))
    return [await _loadout_out(db, l) for l in result.scalars().all()]


@router.post("", response_model=LoadoutOut, status_code=status.HTTP_201_CREATED)
async def create_loadout(
    body: LoadoutSetIn,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoadoutOut:
    """新增一位奇人（见闻未达标不能超过槽位上限）。"""
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="奇人姓名不能为空")
    cap = loadout_capacity(current.exp)
    count = await db.execute(select(func.count()).select_from(Loadout).where(Loadout.user_id == current.id))
    if count.scalar_one() >= cap:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"见闻尚浅，未能解锁更多奇人槽位（{cap}/{cap}，见闻满档可解锁）",
        )
    loadout = Loadout(
        user_id=current.id,
        name=name,
        style=(body.style or "").strip(),
        tactic=(body.tactic or "").strip(),
    )
    db.add(loadout)
    await db.commit()
    await db.refresh(loadout)
    if loadout.style or loadout.tactic:
        _schedule_interpretation(loadout.id)
    return await _loadout_out(db, loadout)


@router.put("/{loadout_id}", response_model=LoadoutOut)
async def update_loadout(
    loadout_id: int,
    body: LoadoutSetIn,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoadoutOut:
    """更新奇人：解封开关、姓名、战斗风格、战术。"""
    loadout = await _get_owned_loadout(db, loadout_id, current)
    if body.name is not None:
        loadout.name = body.name.strip()
    if body.style is not None:
        loadout.style = body.style.strip()
    if body.tactic is not None:
        loadout.tactic = body.tactic.strip()
    if body.enabled is True:
        # 解封强校验：至少装入一个奇术，否则 400（后端守门，前端同样拦截）
        has_ability = await db.execute(
            select(LoadoutAbility).where(LoadoutAbility.loadout_id == loadout.id).limit(1)
        )
        if has_ability.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="奇人还没有奇术，至少装入一个才能解封",
            )
    if body.enabled is not None:
        loadout.enabled = body.enabled
    await db.commit()
    await db.refresh(loadout)
    if body.style is not None or body.tactic is not None:
        _schedule_interpretation(loadout.id)
    return await _loadout_out(db, loadout)


@router.delete("/{loadout_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_loadout(
    loadout_id: int,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """删除奇人：先摘除对决快照引用，清理奇术装配，再删本行。"""
    loadout = await _get_owned_loadout(db, loadout_id, current)
    # 历史/在途对决只存奇人 id 快照：逐侧摘除引用，避免悬挂外键
    await db.execute(update(Battle).where(Battle.loadout_a_id == loadout.id).values(loadout_a_id=None))
    await db.execute(update(Battle).where(Battle.loadout_b_id == loadout.id).values(loadout_b_id=None))
    # 清理奇术装配（loadout_abilities）
    await db.execute(delete(LoadoutAbility).where(LoadoutAbility.loadout_id == loadout.id))
    await db.delete(loadout)
    await db.commit()


@router.post("/{loadout_id}/abilities/{ability_id}", response_model=LoadoutOut)
async def add_ability_to_loadout(
    loadout_id: int,
    ability_id: str,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoadoutOut:
    """把奇术装入奇人（已装则幂等）。"""
    loadout = await _get_owned_loadout(db, loadout_id, current)
    owns = await db.get(UserAbility, (current.id, ability_id))
    if owns is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未拥有该奇术")
    existing = await db.get(LoadoutAbility, (loadout_id, ability_id))
    if existing is None:
        db.add(LoadoutAbility(loadout_id=loadout_id, ability_id=ability_id))
        await db.commit()
    if loadout.style or loadout.tactic:
        _schedule_interpretation(loadout.id)
    return await _loadout_out(db, loadout)


@router.delete("/{loadout_id}/abilities/{ability_id}", response_model=LoadoutOut)
async def remove_ability_from_loadout(
    loadout_id: int,
    ability_id: str,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoadoutOut:
    """把奇术移出奇人。"""
    loadout = await _get_owned_loadout(db, loadout_id, current)
    row = await db.get(LoadoutAbility, (loadout_id, ability_id))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="奇人中没有该奇术")
    await db.delete(row)
    await db.commit()
    if loadout.style or loadout.tactic:
        _schedule_interpretation(loadout.id)
    return await _loadout_out(db, loadout)
