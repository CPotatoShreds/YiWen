"""奇术路由：异闻师自定义奇术（多个，自由增删改）。

奇术由异闻师写下（名目 + 效果 + 详细解释），保存后后台异步生成「因果槽位」
（见 services/ability_understanding.py），作为推演对战的主要依据。
同名同效果在系统内共享一条记录（内容哈希去重）。
"""

import asyncio
from hashlib import sha256
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.base import get_db
from app.models.ability import Ability
from app.models.loadout import Loadout, LoadoutAbility
from app.models.user import User
from app.models.user_ability import UserAbility
from app.schemas.ability import AbilityOut, AbilitySetIn
from app.services.ability_understanding import ensure_ability_understanding

router = APIRouter(prefix="/abilities", tags=["abilities"])

# 持有后台任务引用，防止 asyncio 在任务完成前 GC 取消它
_background_tasks: set[asyncio.Task] = set()


def _schedule_understanding(ability_id: str) -> None:
    """后台异步重算奇术因果槽位（失败静默，不阻塞用户操作）。"""
    task = asyncio.create_task(ensure_ability_understanding(ability_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _ability_id(user_id: int, name: str, effect: str) -> str:
    """奇术 id：内容哈希（同异闻师同内容去重，共享一条记录）。"""
    return sha256(f"{user_id}:{name}:{effect}".encode()).hexdigest()[:16]


@router.post("", response_model=AbilityOut, status_code=status.HTTP_201_CREATED)
async def create_ability(
    body: AbilitySetIn,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Ability:
    """新增一个自定义奇术。"""
    name, effect = body.name.strip(), body.effect.strip()
    if not name or not effect:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="奇术名称与效果不能为空")
    aid = _ability_id(current.id, name, effect)
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
    else:
        ability.name, ability.effect = name, effect
        if body.detail is not None:
            ability.detail = body.detail.strip()
    owns = await db.get(UserAbility, (current.id, aid))
    if owns is None:
        db.add(UserAbility(user_id=current.id, ability_id=aid))
    await db.commit()
    await db.refresh(ability)
    _schedule_understanding(ability.id)
    return ability


@router.get("/mine", response_model=list[AbilityOut])
async def my_abilities(
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Ability]:
    """我的奇术库。"""
    result = await db.execute(
        select(Ability)
        .join(UserAbility, Ability.id == UserAbility.ability_id)
        .where(UserAbility.user_id == current.id)
        .order_by(UserAbility.obtained_at)
    )
    return list(result.scalars().all())


@router.put("/{ability_id}", response_model=AbilityOut)
async def update_ability(
    ability_id: str,
    body: AbilitySetIn,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Ability:
    """修改我的奇术（id 保持稳定，不影响历史行迹记录）。"""
    owns = await db.get(UserAbility, (current.id, ability_id))
    if owns is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未拥有该奇术")
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


@router.delete("/{ability_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ability(
    ability_id: str,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """删除我的奇术。若不再被任何异闻师/奇人持有，则一并清理奇术本体。"""
    owns = await db.get(UserAbility, (current.id, ability_id))
    if owns is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未拥有该奇术")
    await db.delete(owns)
    # 不再拥有 → 从自己的奇人一并移除，避免留下悬空引用
    await db.execute(
        delete(LoadoutAbility).where(
            LoadoutAbility.ability_id == ability_id,
            LoadoutAbility.loadout_id.in_(select(Loadout.id).where(Loadout.user_id == current.id)),
        )
    )
    remain = await db.execute(select(UserAbility.ability_id).where(UserAbility.ability_id == ability_id).limit(1))
    in_loadout = await db.execute(
        select(LoadoutAbility.loadout_id).where(LoadoutAbility.ability_id == ability_id).limit(1)
    )
    if remain.scalar_one_or_none() is None and in_loadout.scalar_one_or_none() is None:
        ability = await db.get(Ability, ability_id)
        if ability is not None:
            await db.delete(ability)
    await db.commit()
