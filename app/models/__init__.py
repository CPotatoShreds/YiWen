"""ORM 模型汇总：导入即注册进 Base.metadata（供 Alembic autogenerate 发现）。"""

from app.models.ability import Ability
from app.models.battle import Battle
from app.models.friendship import Friendship
from app.models.loadout import Loadout, LoadoutAbility
from app.models.request_log import RequestLog
from app.models.user import User
from app.models.user_ability import UserAbility

__all__ = [
    "Ability",
    "Battle",
    "Friendship",
    "Loadout",
    "LoadoutAbility",
    "RequestLog",
    "User",
    "UserAbility",
]
