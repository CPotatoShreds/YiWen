"""启动自愈测试：僵尸挑战清理的阈值与状态边界。"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.db.base import Base, async_session_factory, engine
from app.models.scenario_domain import Scenario, ScenarioChallengeRun, ScenarioRoster
from app.models.user import User
from app.services.scenario.recovery import recover_stale_challenges


@pytest.fixture(autouse=True)
async def _schema():
    """建表独立于 TestClient lifespan：本文件可能先于其他测试运行。"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


async def _make_challenge(db, *, status: str, age_minutes: int) -> ScenarioChallengeRun:
    user = User(username=f"recov_{uuid4().hex[:8]}", password_hash="x")
    db.add(user)
    await db.flush()
    tag = uuid4().hex[:8]
    scenario = Scenario(
        created_by=user.id, name=f"自愈卷{tag}", slug=f"recovery-{tag}", normalized_name=f"自愈卷{tag}",
        subtitle="", introduction="", background="", rules=[], victory_condition="", judgement_rules=[],
    )
    db.add(scenario)
    await db.flush()
    roster = ScenarioRoster(scenario_id=scenario.id, owner_id=user.id, name=f"阵容{tag}", character_name="守方")
    db.add(roster)
    await db.flush()
    challenge = ScenarioChallengeRun(
        roster_id=roster.id, challenger_id=user.id, status=status,
        scenario_snapshot={}, roster_snapshot={}, challenger_snapshot={},
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=age_minutes),
        guess_in_flight=status == "resolving",
    )
    db.add(challenge)
    await db.flush()
    return challenge


async def test_recover_only_stale_preparing_resolving():
    async with async_session_factory() as db:
        stale = await _make_challenge(db, status="resolving", age_minutes=60)
        fresh = await _make_challenge(db, status="preparing", age_minutes=5)
        done = await _make_challenge(db, status="won", age_minutes=60)
        await db.commit()

        await recover_stale_challenges()

        async with async_session_factory() as db2:
            assert (await db2.get(ScenarioChallengeRun, stale.id)).status == "failed"
            assert (await db2.get(ScenarioChallengeRun, stale.id)).guess_in_flight is False
            assert (await db2.get(ScenarioChallengeRun, fresh.id)).status == "preparing"  # 新挑战不误杀
            assert (await db2.get(ScenarioChallengeRun, done.id)).status == "won"  # 终态不动
