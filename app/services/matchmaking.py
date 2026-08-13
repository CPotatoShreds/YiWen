"""摇签服务：从台下听客中抽选对家（数据快照，无需对方在线）。

只抽「有 ≥1 位已解封奇人（且装有奇术）」的其他异闻师——全部未解封的异闻师不会被摇签点名。
"""

from __future__ import annotations

import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.battle import Battle
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


async def pick_opponent_no_repeat(
    db: AsyncSession, user_a_id: int, loadout_a_id: int
) -> tuple[int, Loadout] | None:
    """摇签时避免「我方奇人 × 对家奇人」的具体配对：返回 (对家 id, 对家奇人)，可配则 None。

    检索行迹里与本方奇人（loadout_a_id）同场过的另一侧奇人 id（双向匹配），从剩余候选里随机挑；
    无剩余候选返回 None（调用方兜底普通随机，保证启程始终可用）。
    """
    result = await db.execute(
        select(User.id, Loadout)
        .join(Loadout, Loadout.user_id == User.id)
        .where(User.id != user_a_id, Loadout.enabled.is_(True))
        .join(LoadoutAbility, LoadoutAbility.loadout_id == Loadout.id)
        .distinct()
    )
    candidates = [(uid, ld) for uid, ld in result.all()]
    if not candidates:
        return None

    played = await db.execute(
        select(Battle.loadout_b_id)
        .where(Battle.loadout_a_id == loadout_a_id)
        .union(select(Battle.loadout_a_id).where(Battle.loadout_b_id == loadout_a_id))
    )
    excluded = {lid for lid in played.scalars().all() if lid is not None}
    pool = [(uid, ld) for uid, ld in candidates if ld.id not in excluded]
    return random.choice(pool) if pool else None
