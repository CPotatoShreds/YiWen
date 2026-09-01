"""ORM 模型汇总：导入即注册进 Base.metadata（供 Alembic autogenerate 发现）。"""

from app.models.ability import Ability
from app.models.battle import Battle
from app.models.board import BoardEntry, BoardGuessProgress
from app.models.creator_asset import (
    AbilityRevisionContent,
    AnecdoteRevisionContent,
    AssetEvent,
    AssetRevisionDerivation,
    CharacterRevisionAbility,
    CharacterRevisionContent,
    CreatorAsset,
    CreatorAssetRevision,
    CreatorAssetTag,
    CreatorTag,
    IdempotencyRecord,
    OutboxEvent,
)
from app.models.friendship import Friendship
from app.models.llm_profile import LlmProfile
from app.models.llm_trace import LlmTrace
from app.models.loadout import Loadout, LoadoutAbility
from app.models.notification import Notification
from app.models.prompt_debug import PromptDebugRun, PromptScheme
from app.models.request_log import RequestLog
from app.models.scenario import (
    CreatorScenario,
    ScenarioChallenge,
    ScenarioGuessProgress,
    ScenarioMessage,
    ScenarioRevision,
    ScenarioRevisionAbility,
    ScenarioRevisionGuardian,
    ScenarioRevisionStory,
    ScenarioWorldline,
)
from app.models.scenario_domain import (
    Scenario,
    ScenarioChallengeRun,
    ScenarioRoster,
    ScenarioRosterAbility,
    ScenarioRosterRevisionAbility,
    ScenarioRosterProgress,
    ScenarioRosterRevision,
)
from app.models.test_battle import (
    TestBattle,
    TestBattleGuess,
    TestLoadout,
    TestLoadoutAbility,
    TestUser,
)
from app.models.test_creator_asset import TestAbility, TestAbilityRevision
from app.models.user import User
from app.models.user_ability import UserAbility

__all__ = [
    "Ability",
    "AbilityRevisionContent",
    "AnecdoteRevisionContent",
    "AssetEvent",
    "AssetRevisionDerivation",
    "Battle",
    "BoardEntry",
    "BoardGuessProgress",
    "CharacterRevisionAbility",
    "CharacterRevisionContent",
    "CreatorAsset",
    "CreatorAssetRevision",
    "CreatorAssetTag",
    "CreatorScenario",
    "CreatorTag",
    "Friendship",
    "IdempotencyRecord",
    "LlmProfile",
    "LlmTrace",
    "Loadout",
    "LoadoutAbility",
    "Notification",
    "OutboxEvent",
    "PromptDebugRun",
    "PromptScheme",
    "RequestLog",
    "Scenario",
    "ScenarioChallenge",
    "ScenarioChallengeRun",
    "ScenarioGuessProgress",
    "ScenarioMessage",
    "ScenarioRevision",
    "ScenarioRevisionAbility",
    "ScenarioRevisionGuardian",
    "ScenarioRevisionStory",
    "ScenarioRoster",
    "ScenarioRosterAbility",
    "ScenarioRosterRevisionAbility",
    "ScenarioRosterProgress",
    "ScenarioRosterRevision",
    "ScenarioWorldline",
    "TestAbility",
    "TestAbilityRevision",
    "TestBattle",
    "TestBattleGuess",
    "TestLoadout",
    "TestLoadoutAbility",
    "TestUser",
    "User",
    "UserAbility",
]
