"""奇人榜路由：上榜（冻结刻印）/ 下榜 / 榜单 / 点将挑战 / 榜主追踪挑战者。

上榜 = 把奇人当前状态（名字/风格/战术 + 所装奇术快照）冻结为一条榜单条目；
任何异闻师可点他人榜上奇人发起切磋（点将：先自选出战奇人）。删除奇人不清榜。
榜主可在自己的刻印详情追踪挑战者：搜索挑战者、查看其逐条猜词记录。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.battles import (
    _to_out as battle_to_out,  # 复用单场序列化（无环：battles 不 import board 路由）
)
from app.core.security import get_current_user
from app.db.base import get_db
from app.models.battle import Battle
from app.models.board import BoardEntry, BoardGuessProgress
from app.models.loadout import Loadout
from app.models.user import User
from app.schemas.board import (
    BoardAbilityOut,
    BoardChallengeIn,
    BoardChallengerOut,
    BoardDetailOut,
    BoardEntryIn,
    BoardEntryOut,
    GuessPathRecordOut,
)
from app.services.battle.lifecycle import start_board_challenge
from app.services.loadouts.service import loadout_abilities

router = APIRouter(prefix="/board", tags=["board"])


async def _to_out(
    db: AsyncSession,
    entry: BoardEntry,
    user_name: str,
    mine: bool,
    challenge_count: int = 0,
    win_rate: float | None = None,
    avg_crack_attempts: float | None = None,
    cracked: bool = False,
) -> BoardEntryOut:
    return BoardEntryOut(
        id=entry.id,
        user=user_name,
        name=entry.name,
        style=entry.style,
        ability_count=len(entry.abilities or []),
        challenge_count=challenge_count,
        win_rate=win_rate,
        avg_crack_attempts=avg_crack_attempts,
        mine=mine,
        cracked=cracked,
        created_at=entry.created_at,
    )


async def _crack_stats(db: AsyncSession, entry_ids: list[int]) -> dict[int, float | None]:
    """每刻印的平均每门看破花费次数：Σattempts_used（有≥1看破的行）÷ Σ看破门数。

    只统计「至少看破过一门」的挑战者（未看破者的猜测不摊入任何一门的成本）。
    """
    if not entry_ids:
        return {}
    rows = (
        await db.execute(
            select(BoardGuessProgress).where(BoardGuessProgress.board_entry_id.in_(entry_ids))
        )
    ).scalars().all()
    acc: dict[int, list[int]] = {}  # entry_id -> [总猜测次数, 总看破门数]
    for r in rows:
        cracked_n = sum(1 for c in (r.cards or []) if c.get("cracked"))
        if cracked_n <= 0:
            continue
        d = acc.setdefault(r.board_entry_id, [0, 0])
        d[0] += r.attempts_used or 0
        d[1] += cracked_n
    return {eid: (t / c if c else None) for eid, (t, c) in acc.items()}


@router.get("", response_model=list[BoardEntryOut])
async def list_board(
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[BoardEntryOut]:
    """奇人榜：按刻印时间倒序全量（奇术保密，仅展示数量；被点将次数/刻印胜场一次 outerjoin 算好）。"""
    rows = await db.execute(
        select(
            BoardEntry,
            User,
            func.count(Battle.id).label("challenge_count"),
            func.sum(case((Battle.winner_id == BoardEntry.user_id, 1), else_=0)).label("poster_wins"),
        )
        .join(User, User.id == BoardEntry.user_id)
        .outerjoin(Battle, Battle.board_entry_id == BoardEntry.id)
        .group_by(BoardEntry.id, User.id)
        .order_by(BoardEntry.created_at.desc())
    )
    all_rows = rows.all()
    crack_stats = await _crack_stats(db, [entry.id for entry, *_ in all_rows])
    flipped_ids: set[int] = set()
    if all_rows:
        flipped = await db.execute(
            select(BoardGuessProgress.board_entry_id)
            .where(
                BoardGuessProgress.challenger_id == current.id,
                BoardGuessProgress.board_entry_id.in_([entry.id for entry, *_ in all_rows]),
                BoardGuessProgress.flipped == True,
            )
        )
        flipped_ids = set(flipped.scalars().all())
    out = []
    for entry, user, challenge_count, poster_wins in all_rows:
        win_rate = (poster_wins or 0) / challenge_count if challenge_count else None
        out.append(
            await _to_out(
                db,
                entry,
                user.username,
                mine=(user.id == current.id),
                challenge_count=challenge_count,
                win_rate=win_rate,
                avg_crack_attempts=crack_stats.get(entry.id),
                cracked=(entry.id in flipped_ids),
            )
        )
    return out


@router.get("/{entry_id}", response_model=BoardDetailOut)
async def board_detail(
    entry_id: int,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BoardDetailOut:
    """榜单条目详情：查看者视角的看破进度 + 与该刻印的对战记录 + 胜率/看破统计。

    榜主看刻印全貌 + 全部挑战局行迹（掩码猜词，只显示对方与胜负）；第三方未点将 → 全保密 + 空记录。
    只读进度，绝不因看详情而创建进度行。
    """
    entry = await db.get(BoardEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="榜单条目不存在")
    mine = entry.user_id == current.id
    owner = await db.get(User, entry.user_id)
    challenge_count = (
        await db.execute(select(func.count(Battle.id)).where(Battle.board_entry_id == entry_id))
    ).scalar_one()
    poster_wins = (
        await db.execute(
            select(func.count(Battle.id)).where(
                Battle.board_entry_id == entry_id, Battle.winner_id == entry.user_id
            )
        )
    ).scalar_one()
    win_rate = (poster_wins or 0) / challenge_count if challenge_count else None
    avg_crack_attempts = (await _crack_stats(db, [entry_id])).get(entry_id)
    abilities = entry.abilities or []

    progress: list[BoardAbilityOut] = []
    viewer_cracked = False  # 当前查看者是否已看破该刻印全部奇术（榜主对自己刻印恒 False）
    if mine:
        for i, a in enumerate(abilities):
            progress.append(BoardAbilityOut(index=i + 1, cracked=True, name=a["name"], effect=a["effect"]))
    else:
        prog = await db.get(BoardGuessProgress, (current.id, entry_id))
        viewer_cracked = bool(prog and prog.flipped)
        cards = prog.cards if prog else [{"cracked": False} for _ in abilities]
        for i, (card, a) in enumerate(zip(cards, abilities)):
            cracked = bool(card.get("cracked"))
            progress.append(
                BoardAbilityOut(
                    index=i + 1,
                    cracked=cracked,
                    missing=card.get("missing") or "",
                    name=a["name"] if cracked else None,
                    effect=a["effect"] if cracked else None,
                )
            )

    if mine:
        # 榜主开放全部挑战局行迹：只看自己视角、不开放猜词（_to_out 已按榜主掩码）
        rows = (
            await db.execute(
                select(Battle)
                .where(Battle.board_entry_id == entry_id)
                .order_by(Battle.created_at.desc())
            )
        ).scalars().all()
    else:
        rows = (
            await db.execute(
                select(Battle)
                .where(Battle.board_entry_id == entry_id, Battle.user_a_id == current.id)
                .order_by(Battle.created_at.desc())
            )
        ).scalars().all()
    battles = [await battle_to_out(db, b, viewer_id=current.id) for b in rows]

    return BoardDetailOut(
        id=entry.id,
        user=owner.username if owner else "?",
        name=entry.name,
        style=entry.style,
        ability_count=len(abilities),
        challenge_count=challenge_count,
        win_rate=win_rate,
        avg_crack_attempts=avg_crack_attempts,
        mine=mine,
        cracked=viewer_cracked,
        created_at=entry.created_at,
        progress=progress,
        battles=battles,
    )


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


@router.get("/{entry_id}/tracking/challengers", response_model=list[BoardChallengerOut])
async def entry_challengers(
    entry_id: int,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    search: str = "",
) -> list[BoardChallengerOut]:
    """榜主追踪：某刻印的挑战者列表（按名号搜索，有猜词记录者）。仅榜主可查。"""
    entry = await db.get(BoardEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="榜单条目不存在")
    if entry.user_id != current.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有榜主可追踪挑战者")
    q = select(BoardGuessProgress, User).join(User, User.id == BoardGuessProgress.challenger_id)
    q = q.where(BoardGuessProgress.board_entry_id == entry_id)
    if search:
        q = q.where(User.username.contains(search))
    q = q.order_by(User.username)
    rows = (await db.execute(q)).all()
    total = len(entry.abilities or [])
    return [
        BoardChallengerOut(
            user_id=user.id,
            username=user.username,
            total_guesses=len(prog.guess_log or []),
            cracked=sum(1 for c in (prog.cards or []) if c.get("cracked")),
            total=total,
        )
        for prog, user in rows
    ]


@router.get("/{entry_id}/tracking/challengers/{challenger_id}/guess-path", response_model=list[GuessPathRecordOut])
async def challenger_guess_path(
    entry_id: int,
    challenger_id: int,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[GuessPathRecordOut]:
    """榜主追踪：某挑战者对该刻印的逐条猜词记录（时间升序，含每条爆出的线索/当时看破门数/对应战报）。"""
    entry = await db.get(BoardEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="榜单条目不存在")
    if entry.user_id != current.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有榜主可追踪挑战者")
    prog = await db.get(BoardGuessProgress, (challenger_id, entry_id))
    if prog is None or not prog.guess_log:
        return []
    records = sorted(prog.guess_log, key=lambda r: r.get("at", ""))
    return [GuessPathRecordOut(**r) for r in records]
