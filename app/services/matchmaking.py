"""摇签服务：从台下听客中抽选对家（数据快照，无需对方在线）。

只抽「有 ≥1 位已解封奇人（且装有奇术）」的其他异闻师——全部未解封的异闻师不会被摇签点名。
"""

from __future__ import annotations

import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.loadout import Loadout, LoadoutAbility
from app.models.user import User


async def pick_opponent(db: AsyncSession, exclude_user_id: int) -> int | None:
    """从有已解封奇人（装有奇术）的其他异闻师中随机抽一位；无人可摇签返回 None。"""
    rows = await db.execute(
        select(User.id)
        .join(Loadout, Loadout.user_id == User.id)
        .where(User.id != exclude_user_id, Loadout.enabled.is_(True))
        .join(LoadoutAbility, LoadoutAbility.loadout_id == Loadout.id)
        .distinct()
    )
    pool = list(rows.scalars().all())
    return random.choice(pool) if pool else None
