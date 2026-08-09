"""养成结算：见闻（唯一养成属性）、名望（Elo 天梯分）。

对决纯机制对抗、无数值强度，因此没有任何提升战斗力的数值消耗。
- 见闻：唯一养成属性，开张与对决获得，满档解锁更多奇人槽位（见 models.user.loadout_capacity）。
- 名望：Elo 天梯分（起始 1000，K=32），仅排名，与见闻无关。
"""

from __future__ import annotations

from datetime import UTC, datetime

DAILY_LOGIN_EXP = 10
FIRST_BATTLE_EXP = 5
BATTLE_EXP = 5
INITIAL_RANK = 1000
ELO_K = 32


def today() -> str:
    return datetime.now(UTC).date().isoformat()


def apply_daily_login(user) -> bool:
    """每日开张奖励：+10 见闻。返回是否刚领取（当日首次）。"""
    if user.last_login_date != today():
        user.exp += DAILY_LOGIN_EXP
        user.last_login_date = today()
        return True
    return False


def apply_battle_rewards(user) -> bool:
    """对决后结算：+5 见闻；当日首次对决额外 +5 见闻。返回是否首次。"""
    user.exp += BATTLE_EXP
    first = user.last_battle_date != today()
    if first:
        user.exp += FIRST_BATTLE_EXP
        user.last_battle_date = today()
    return first


def elo_update(ra: int, rb: int, a_score: float) -> tuple[int, int]:
    """Elo 名望变化，返回 (delta_a, delta_b)。a_score：1=胜 0.5=和 0=负。"""
    ea = 1 / (1 + 10 ** ((rb - ra) / 400))
    eb = 1 - ea
    da = round(ELO_K * (a_score - ea))
    db = round(ELO_K * ((1 - a_score) - eb))
    return da, db
