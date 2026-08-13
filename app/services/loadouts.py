"""奇人服务：对决登场奇人抽选、奇人所装奇术。

- pick_battle_loadout：随机抽一位已解封且装有奇术的奇人（己方与对家共用）。
- loadout_abilities：某位奇人装入的奇术（按加入顺序）。

奇人由异闻师自行创建（名字必填，见 api/routes/loadouts.py），注册不赠送默认奇人。
"""

from __future__ import annotations

import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ability import Ability
from app.models.loadout import Loadout, LoadoutAbility


async def pick_battle_loadout(db: AsyncSession, user_id: int) -> Loadout | None:
    """随机抽该异闻师一位已解封且装有奇术的奇人。

    只考虑装有至少一个奇术的奇人；无可抽返回 None。
    """
    result = await db.execute(
        select(Loadout)
        .join(LoadoutAbility, LoadoutAbility.loadout_id == Loadout.id)
        .where(Loadout.user_id == user_id, Loadout.enabled.is_(True))
        .distinct()
    )
    pool = list(result.scalars().all())
    return random.choice(pool) if pool else None


async def loadout_abilities(db: AsyncSession, loadout_id: int) -> list[Ability]:
    """某位奇人装入的奇术（按加入顺序）。"""
    result = await db.execute(
        select(Ability)
        .join(LoadoutAbility, LoadoutAbility.ability_id == Ability.id)
        .where(LoadoutAbility.loadout_id == loadout_id)
        .order_by(LoadoutAbility.added_at)
    )
    return list(result.scalars().all())


async def loadout_snapshot(db: AsyncSession, loadout: Loadout) -> dict:
    """冻结奇人当前状态为快照 dict（含所装奇术完整字段），供对局/上榜刻印与再战复刻使用。"""
    abilities = await loadout_abilities(db, loadout.id)
    return {
        "name": loadout.name,
        "style": loadout.style,
        "tactic": loadout.tactic,
        "style_interpretation": loadout.style_interpretation,
        "tactic_interpretation": loadout.tactic_interpretation,
        "abilities": [
            {
                "name": a.name,
                "effect": a.effect,
                "detail": a.detail,
                "tactic": a.tactic,
                "understanding": a.understanding,
            }
            for a in abilities
        ],
    }


def abilities_from_snapshot(snap_abilities: list[dict]) -> list[Ability]:
    """把快照里的奇术 dict 重建为瞬时 Ability 对象（供推演/猜词读取，不落库）。"""
    return [
        Ability(
            name=a["name"],
            effect=a["effect"],
            detail=a.get("detail", ""),
            tactic=a.get("tactic", ""),
            understanding=a.get("understanding", ""),
        )
        for a in snap_abilities
    ]
