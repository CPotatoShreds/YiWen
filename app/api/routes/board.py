"""奇人榜路由：上榜（冻结刻印）/ 下榜 / 榜单 / 点将挑战。

上榜 = 把奇人当前状态（名字/风格/战术 + 所装奇术快照）冻结为一条榜单条目；
任何异闻师可点他人榜上奇人发起切磋（点将：先自选出战奇人）。删除奇人不清榜。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.base import get_db
from app.models.board import BoardEntry
from app.models.loadout import Loadout
from app.models.user import User
from app.schemas.board import BoardChallengeIn, BoardEntryIn, BoardEntryOut
from app.services.battle import start_board_challenge
from app.services.loadouts import loadout_abilities

router = APIRouter(prefix="/board", tags=["board"])


async def _to_out(db: AsyncSession, entry: BoardEntry, user_name: str, mine: bool) -> BoardEntryOut:
    return BoardEntryOut(
        id=entry.id,
        user=user_name,
        name=entry.name,
        style=entry.style,
        ability_count=len(entry.abilities or []),
        mine=mine,
        created_at=entry.created_at,
    )


@router.get("", response_model=list[BoardEntryOut])
async def list_board(
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[BoardEntryOut]:
    """奇人榜：按刻印时间倒序全量（奇术保密，仅展示数量）。"""
    rows = await db.execute(
        select(BoardEntry, User)
        .join(User, User.id == BoardEntry.user_id)
        .order_by(BoardEntry.created_at.desc())
    )
    out = []
    for entry, user in rows.all():
        out.append(await _to_out(db, entry, user.username, mine=(user.id == current.id)))
    return out


@router.post("", response_model=BoardEntryOut, status_code=status.HTTP_201_CREATED)
async def put_on_board(
    body: BoardEntryIn,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BoardEntryOut:
    """上榜：冻结当前奇人状态为刻印（一奇人可多席）。需归属本人且装有 ≥1 奇术。"""
    loadout = await db.get(Loadout, body.loadout_id)
    if loadout is None or loadout.user_id != current.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="奇人不存在")
    abilities = await loadout_abilities(db, loadout.id)
    if not abilities:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="奇人还没有奇术，无法上榜")
    entry = BoardEntry(
        user_id=current.id,
        loadout_id=loadout.id,
        name=loadout.name,
        style=loadout.style,
        tactic=loadout.tactic,
        abilities=[
            {
                "name": a.name,
                "effect": a.effect,
                "detail": a.detail,
                "tactic": a.tactic,
                "understanding": a.understanding,
            }
            for a in abilities
        ],
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return await _to_out(db, entry, current.username, mine=True)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def take_off_board(
    entry_id: int,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """下榜：仅榜主。"""
    entry = await db.get(BoardEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="榜单条目不存在")
    if entry.user_id != current.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只能下自己的榜单")
    await db.delete(entry)
    await db.commit()


@router.post("/{entry_id}/challenge", response_model=dict)
async def challenge_entry(
    entry_id: int,
    body: BoardChallengeIn,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """点将挑战：自选出战奇人（已解封且装奇术）vs 榜上冻结刻印，建切磋局（不计名望）。"""
    entry = await db.get(BoardEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="榜单条目不存在")
    if entry.user_id == current.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能挑战自己榜上的奇人")
    chosen = await db.get(Loadout, body.loadout_id)
    if chosen is None or chosen.user_id != current.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="出战奇人不存在")
    if not chosen.enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="出战奇人需已解封")
    if not await loadout_abilities(db, chosen.id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="出战奇人还没有奇术")
    battle = await start_board_challenge(db, current, entry, chosen)
    if battle is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="你已有一场在途对决，请先待其落定")
    return {"battle_id": battle.id}
