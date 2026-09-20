"""ORM 模型汇总：导入即注册进 Base.metadata（供 Alembic autogenerate 发现）。"""

from app.models.ability import Ability
from app.models.admin_audit import AdminAuditLog
from app.models.character import Character, CharacterAbility
from app.models.llm_profile import LlmProfile
from app.models.llm_trace import LlmTrace
from app.models.refresh_token import RefreshToken
from app.models.request_log import RequestLog
from app.models.scenario_domain import (
    Scenario,
    ScenarioChallengeRun,
    ScenarioRoster,
    ScenarioRosterAbility,
    ScenarioRosterProgress,
    ScenarioRosterRevision,
    ScenarioRosterRevisionAbility,
)
from app.models.user import User

__all__ = [
    "Ability",
    "AdminAuditLog",
    "Character",
    "CharacterAbility",
    "LlmProfile",
    "LlmTrace",
    "RefreshToken",
    "RequestLog",
    "Scenario",
    "ScenarioChallengeRun",
    "ScenarioRoster",
    "ScenarioRosterAbility",
    "ScenarioRosterProgress",
    "ScenarioRosterRevision",
    "ScenarioRosterRevisionAbility",
    "User",
]
