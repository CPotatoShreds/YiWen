"""ORM 模型汇总：导入即注册进 Base.metadata（供 Alembic autogenerate 发现）。"""

from app.models.ability import Ability
from app.models.battle import Battle
from app.models.board import BoardEntry, BoardGuessProgress
from app.models.friendship import Friendship
from app.models.llm_trace import LlmTrace
from app.models.loadout import Loadout, LoadoutAbility
from app.models.notification import Notification
from app.models.request_log import RequestLog
from app.models.test_battle import (
    TestBattle,
    TestBattleGuess,
    TestLoadout,
    TestLoadoutAbility,
    TestUser,
)
from app.models.user import User
from app.models.user_ability import UserAbility

__all__ = [
    "Ability",
    "Battle",
    "BoardEntry",
    "BoardGuessProgress",
    "Friendship",
    "LlmTrace",
    "Loadout",
    "LoadoutAbility",
    "Notification",
    "RequestLog",
    "TestBattle",
    "TestBattleGuess",
    "TestLoadout",
    "TestLoadoutAbility",
    "TestUser",
    "User",
    "UserAbility",
]
