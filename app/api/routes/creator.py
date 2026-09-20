"""用户奇人、奇术 CRUD。"""
import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.base import get_db
from app.models.ability import Ability
from app.models.character import Character, CharacterAbility
from app.models.user import User
from app.schemas.creator import (
    AbilityCreate,
    AbilityOut,
    CharacterCreate,
    CharacterDetailOut,
    CharacterOut,
)
from app.services.ability.understanding import ensure_ability_understanding

router = APIRouter(prefix="/creator", tags=["creator"])
_tasks: set[asyncio.Task] = set()


def _schedule(aid: str) -> None:
    task = asyncio.create_task(ensure_ability_understanding(aid))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _ability_list(db: AsyncSession, ids: list[str], owner_id: int) -> list[Ability]:
    if not ids:
        return []
    rows = list((await db.scalars(select(Ability).where(Ability.id.in_(ids), Ability.owner_id == owner_id))).all())
    by_id = {a.id: a for a in rows}
    return [by_id[i] for i in ids if i in by_id]


async def _character_out(db: AsyncSession, character: Character, detail: bool = False):
    links = list((await db.scalars(select(CharacterAbility).where(CharacterAbility.character_id == character.id).order_by(CharacterAbility.position))).all())
    ids = [x.ability_id for x in links]
    abilities = await _ability_list(db, ids, character.owner_id)
    if detail:
        return CharacterDetailOut.model_validate({**character.__dict__, "ability_ids": ids, "abilities": abilities})
    return CharacterOut.model_validate({**character.__dict__, "ability_ids": ids})


async def _get_owned_ability(ability_id: str, current: User, db: AsyncSession) -> Ability:
    ability = await db.get(Ability, ability_id)
    if ability is None or ability.owner_id != current.id:
        raise HTTPException(404, "奇术不存在")
    return ability


@router.get("/abilities", response_model=list[AbilityOut])
async def list_abilities(current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    return list((await db.scalars(select(Ability).where(Ability.owner_id == current.id).order_by(Ability.updated_at.desc()))).all())


@router.post("/abilities", response_model=AbilityOut, status_code=201)
async def create_ability(body: AbilityCreate, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    duplicate = await db.scalar(select(Ability.id).where(Ability.owner_id == current.id, Ability.name == body.name))
    if duplicate is not None:
        raise HTTPException(409, "奇术名称已存在")
    ability = Ability(owner_id=current.id, name=body.name, effect=body.effect, detail=body.detail)
    db.add(ability)
    await db.flush()
    await db.commit()
    await db.refresh(ability)
    _schedule(ability.id)
    return ability


@router.get("/abilities/{ability_id}", response_model=AbilityOut)
async def get_ability(ability_id: str, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    return await _get_owned_ability(ability_id, current, db)


@router.put("/abilities/{ability_id}", response_model=AbilityOut)
async def update_ability(ability_id: str, body: AbilityCreate, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    ability = await _get_owned_ability(ability_id, current, db)
    duplicate = await db.scalar(select(Ability.id).where(Ability.owner_id == current.id, Ability.name == body.name, Ability.id != ability.id))
    if duplicate is not None:
        raise HTTPException(409, "奇术名称已存在")
    ability.name = body.name
    ability.effect = body.effect
    ability.detail = body.detail
    await db.commit()
    await db.refresh(ability)
    _schedule(ability.id)
    return ability


@router.delete("/abilities/{ability_id}", status_code=204)
async def delete_ability(ability_id: str, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    ability = await _get_owned_ability(ability_id, current, db)
    # Removing an ability also removes it from every owned character.
    await db.execute(delete(CharacterAbility).where(CharacterAbility.ability_id == ability.id))
    await db.delete(ability)
    await db.commit()


@router.get("/characters", response_model=list[CharacterOut])
async def list_characters(current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    rows = list((await db.scalars(select(Character).where(Character.owner_id == current.id).order_by(Character.updated_at.desc()))).all())
    return [await _character_out(db, x) for x in rows]


@router.post("/characters", response_model=CharacterOut, status_code=201)
async def create_character(body: CharacterCreate, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    ids = list(dict.fromkeys(body.ability_ids))
    abilities = await _ability_list(db, ids, current.id)
    if len(abilities) != len(ids):
        raise HTTPException(400, "只能绑定自己拥有的奇术")
    duplicate = await db.scalar(select(Character.id).where(Character.owner_id == current.id, Character.name == body.name))
    if duplicate is not None:
        raise HTTPException(409, "奇人名称已存在")
    character = Character(owner_id=current.id, name=body.name, bio=body.bio)
    db.add(character)
    await db.flush()
    db.add_all([CharacterAbility(character_id=character.id, ability_id=aid, position=i + 1) for i, aid in enumerate(ids)])
    await db.commit()
    await db.refresh(character)
    return await _character_out(db, character)


@router.get("/characters/{character_id}", response_model=CharacterDetailOut)
async def get_character(character_id: UUID, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    character = await db.get(Character, character_id)
    if character is None or character.owner_id != current.id:
        raise HTTPException(404, "奇人不存在")
    return await _character_out(db, character, True)


@router.put("/characters/{character_id}", response_model=CharacterOut)
async def update_character(character_id: UUID, body: CharacterCreate, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    character = await db.get(Character, character_id)
    if character is None or character.owner_id != current.id:
        raise HTTPException(404, "奇人不存在")
    ids = list(dict.fromkeys(body.ability_ids))
    abilities = await _ability_list(db, ids, current.id)
    if len(abilities) != len(ids):
        raise HTTPException(400, "只能绑定自己拥有的奇术")
    duplicate = await db.scalar(select(Character.id).where(Character.owner_id == current.id, Character.name == body.name, Character.id != character.id))
    if duplicate is not None:
        raise HTTPException(409, "奇人名称已存在")
    character.name = body.name
    character.bio = body.bio
    await db.execute(delete(CharacterAbility).where(CharacterAbility.character_id == character.id))
    db.add_all([CharacterAbility(character_id=character.id, ability_id=aid, position=i + 1) for i, aid in enumerate(ids)])
    await db.commit()
    await db.refresh(character)
    return await _character_out(db, character)


@router.delete("/characters/{character_id}", status_code=204)
async def delete_character(character_id: UUID, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    character = await db.get(Character, character_id)
    if character is None or character.owner_id != current.id:
        raise HTTPException(404, "奇人不存在")
    await db.delete(character)
    await db.commit()
