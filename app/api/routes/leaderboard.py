"""异闻榜路由：按名望（Elo 天梯分）排名。小圈子，全量排序即可。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.base import get_db
from app.models.user import User
from app.schemas.leaderboard import LeaderboardEntry, LeaderboardOut

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])

TOP_N = 50  # 榜上席位：名望前 50


@router.get("", response_model=LeaderboardOut)
async def leaderboard(
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LeaderboardOut:
    """异闻榜：名望降序（同分按注册先后），附当前异闻师自己的名次（榜外也返回 me）。"""
    result = await db.execute(select(User).order_by(User.rank_points.desc(), User.id.asc()))
    users = result.scalars().all()
    entries = [
        LeaderboardEntry(rank=i + 1, username=u.username, rank_points=u.rank_points, exp=u.exp)
        for i, u in enumerate(users[:TOP_N])
    ]
    me = None
    for i, u in enumerate(users):
        if u.id == current.id:
            me = LeaderboardEntry(rank=i + 1, username=u.username, rank_points=u.rank_points, exp=u.exp)
            break
    return LeaderboardOut(entries=entries, me=me)
