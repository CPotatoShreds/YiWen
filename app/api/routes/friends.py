"""故人路由：递拜帖 / 应帖 / 名录 / 待收。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.base import get_db
from app.models.friendship import Friendship
from app.models.user import User
from app.schemas.friend import FriendOut, FriendRequest

router = APIRouter(prefix="/friends", tags=["friends"])


async def _existing(db: AsyncSession, a: int, b: int) -> Friendship | None:
    result = await db.execute(
        select(Friendship).where(
            or_(
                and_(Friendship.user_id == a, Friendship.friend_id == b),
                and_(Friendship.user_id == b, Friendship.friend_id == a),
            )
        )
    )
    return result.scalar_one_or_none()


@router.post("/request")
async def request_friend(
    body: FriendRequest,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    if body.friend_id == current.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能与自己结为故人")
    target = await db.get(User, body.friend_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="异闻师不存在")
    if await _existing(db, current.id, body.friend_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="已是故人或拜帖已递出")
    db.add(Friendship(user_id=current.id, friend_id=body.friend_id, status="pending"))
    await db.commit()
    return {"message": "拜帖已递出"}


@router.post("/{friend_id}/accept")
async def accept_friend(
    friend_id: int,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    result = await db.execute(
        select(Friendship).where(
            Friendship.user_id == friend_id,
            Friendship.friend_id == current.id,
            Friendship.status == "pending",
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="没有待收的拜帖")
    row.status = "accepted"
    await db.commit()
    return {"message": "已成为故人"}


@router.get("", response_model=list[FriendOut])
async def list_friends(
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[FriendOut]:
    """我的故人（含待收拜帖）。"""
    result = await db.execute(
        select(Friendship).where(
            or_(
                and_(Friendship.user_id == current.id, Friendship.status == "accepted"),
                and_(Friendship.friend_id == current.id, Friendship.status == "accepted"),
            )
        )
    )
    out = []
    for f in result.scalars().all():
        other_id = f.friend_id if f.user_id == current.id else f.user_id
        other = await db.get(User, other_id)
        if other:
            out.append(FriendOut(id=other.id, username=other.username, status=f.status))
    return out


@router.get("/requests", response_model=list[FriendOut])
async def pending_requests(
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[FriendOut]:
    """递来的待收拜帖。"""
    result = await db.execute(
        select(Friendship).where(
            Friendship.friend_id == current.id,
            Friendship.status == "pending",
        )
    )
    out = []
    for f in result.scalars().all():
        requester = await db.get(User, f.user_id)
        if requester:
            out.append(FriendOut(id=requester.id, username=requester.username, status=f.status))
    return out
