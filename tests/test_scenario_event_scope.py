"""SSE 职责收缩验收：god 遮挡流（真实文本不出站）、stage 退场、按侧别投递。

不经过 HTTP 缓冲层：直接驱动真实的 `resolve_scenario_action` 后台任务与
`challenge_stream` 端点生成器（SSE 需要真实流式传输，TestClient 会缓冲整包）。
不调用真实 LLM：桩掉比对/上帝/双方转写/检定节点（延迟桩保证订阅先建立）。
"""

import asyncio
import json
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.api.routes import scenario_domain
from app.db.base import Base, async_session_factory, engine
from app.models.scenario_domain import (
    Scenario,
    ScenarioChallengeRun,
    ScenarioRoster,
    ScenarioRosterProgress,
)
from app.models.user import User
from app.services.scenario import flows
from app.services.scenario import stream as stream_module

_GOD_TEXT = "上帝真实全文不可出站"
_CHALLENGER_TEXT = "挑战者视角全文"
_GUARDIAN_TEXT = "守方视角全文"


@pytest.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


class _FakeChain:
    """非 Runnable 桩：astream_with_reliability 回退单块产出，ainvoke 直接返回。"""

    def __init__(self, value, delay: float = 0.05):
        self._value, self._delay = value, delay

    async def ainvoke(self, kwargs):
        await asyncio.sleep(self._delay)
        return self._value


def _llm_patches() -> list:
    return [
        patch("app.services.scenario.flows.compare_scenario_abilities", lambda *a, **k: _noop_compare()),
        patch("app.services.scenario.flows.build_scenario_god_llm", lambda *a, **k: _FakeChain(_GOD_TEXT)),
        patch("app.services.scenario.flows.build_scenario_challenger_view_stream_llm", lambda *a, **k: _FakeChain(_CHALLENGER_TEXT)),
        patch("app.services.scenario.flows.build_scenario_guardian_view_stream_llm", lambda *a, **k: _FakeChain(_GUARDIAN_TEXT)),
        patch(
            "app.services.scenario.flows.build_scenario_judge_llm",
            lambda *a, **k: _FakeChain(SimpleNamespace(achieved=True, reason="达成目标")),
        ),
    ]


async def _noop_compare():
    return "（测试比对报告）"


async def _seed_resolving_challenge(*, roster_abilities: list[dict] | None = None, cracked: list[dict] | None = None,
                                    status: str = "resolving", messages: list[dict] | None = None) -> tuple[ScenarioChallengeRun, User, User]:
    """落库最小闭环数据：挑战者/守方/卷/阵容/挑战，返回 (挑战, 挑战者, 守方)。"""
    async with async_session_factory() as db:
        tag = uuid4().hex[:8]
        challenger = User(username=f"sct_c_{tag}", password_hash="x")
        owner = User(username=f"sct_o_{tag}", password_hash="x")
        db.add_all([challenger, owner])
        await db.flush()
        scenario = Scenario(
            created_by=owner.id, name=f"职责卷{tag}", slug=f"scope-{tag}", normalized_name=f"职责卷{tag}",
            subtitle="遮挡", introduction="验收", background="结界对决", rules=["不得离开结界"],
            victory_condition="让对方失去战斗能力", judgement_rules=["同时失去能力判负"],
        )
        db.add(scenario)
        await db.flush()
        roster = ScenarioRoster(
            scenario_id=scenario.id, owner_id=owner.id, name=f"阵容{tag}", character_name="守风",
        )
        db.add(roster)
        await db.flush()
        challenge = ScenarioChallengeRun(
            roster_id=roster.id, challenger_id=challenger.id, status=status,
            scenario_snapshot={"name": "职责卷", "rules": [], "judgement_rules": [], "victory_condition": "胜", "background": "开场"},
            roster_snapshot={"character_name": "守风", "guidance": "守住结界", "abilities": roster_abilities or []},
            challenger_snapshot={"character_name": "逐影", "abilities": []},
            messages=messages or [{"role": "challenger", "text": "正面突进"}],
        )
        db.add(challenge)
        if cracked is not None:
            db.add(ScenarioRosterProgress(roster_id=roster.id, challenger_id=challenger.id, cracked_cards=cracked))
        await db.commit()
        await db.refresh(challenge)
        return challenge, challenger, owner


async def _drain(queue: asyncio.Queue, timeout: float = 10.0) -> list[dict]:
    events: list[dict] = []
    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout)
        except TimeoutError:
            break
        events.append(event)
        if event.get("type") in ("done", "error"):
            break
    return events


async def test_resolve_publishes_shielded_god_and_side_scoped_events():
    """真实后台任务的发布契约：god 只发 chars、view_chunk 带侧、turn 按侧拆分、stage 退场。"""
    challenge, _, _ = await _seed_resolving_challenge()
    stream = stream_module.get_scenario_stream(challenge.id)
    challenger_queue, _ = await stream.subscribe(side="challenger")
    guardian_queue, _ = await stream.subscribe(side="guardian")

    with ExitStack() as stack:
        for p in _llm_patches():
            stack.enter_context(p)
        await asyncio.wait_for(flows.resolve_scenario_action(challenge.id), timeout=15)

    challenger_events = await _drain(challenger_queue)
    guardian_events = await _drain(guardian_queue)

    # 挑战者侧：字体契约
    c_types = [e["type"] for e in challenger_events]
    assert "stage" not in c_types and "god" not in c_types
    assert "god_progress" in c_types and "turn" in c_types and "done" in c_types
    c_blob = json.dumps(challenger_events, ensure_ascii=False)
    assert _GOD_TEXT not in c_blob  # 核心：上帝明文全程不出站（未看破全部门控锁死）
    progress = [e for e in challenger_events if e["type"] == "god_progress"]
    assert all(set(e.keys()) == {"type", "chars"} for e in progress) and progress[-1]["chars"] > 0
    c_chunks = [e for e in challenger_events if e["type"] == "view_chunk"]
    assert c_chunks and all(e["side"] == "challenger" for e in c_chunks)
    c_turn = next(e["turn"] for e in challenger_events if e["type"] == "turn")
    # 门控（未看破全部）：挑战者 turn 只含己方正文，无守方正文、无上帝全文
    assert c_turn["challenger_text"] == _CHALLENGER_TEXT
    assert "guardian_text" not in c_turn and "omniscient" not in c_turn
    assert c_turn["achieved"] is True and c_turn["reason"]

    # 守方侧：无挑战者正文、无上帝文本，turn 为守方形状
    g_blob = json.dumps(guardian_events, ensure_ascii=False)
    assert _GOD_TEXT not in g_blob and _CHALLENGER_TEXT not in g_blob
    g_chunks = [e for e in guardian_events if e["type"] == "view_chunk"]
    assert g_chunks and all(e["side"] == "guardian" for e in g_chunks)
    g_turn = next(e["turn"] for e in guardian_events if e["type"] == "turn")
    assert g_turn == {"role": "guardian", "text": _GUARDIAN_TEXT, "created_at": g_turn["created_at"]}
    assert "done" in [e["type"] for e in guardian_events]

    # 落库的回合仍含两侧与上帝全文（归档授权逻辑不变）
    async with async_session_factory() as db:
        stored = await db.get(ScenarioChallengeRun, challenge.id)
        assert stored.status == "won"
        assert stored.messages[-1]["omniscient"] == _GOD_TEXT


async def test_god_gate_detail_locked_then_unlocked():
    """看破门控（详情接口）：未全破无上帝/守方正文；全破后附上帝全文；守方始终只见自己。"""
    abilities = [{"name": "术一", "effect": "e1"}, {"name": "术二", "effect": "e2"}]
    turn = {"role": "views", "challenger_text": _CHALLENGER_TEXT, "guardian_text": _GUARDIAN_TEXT,
            "omniscient": _GOD_TEXT, "achieved": True, "reason": "达成", "created_at": "seed"}
    challenge, challenger, owner = await _seed_resolving_challenge(
        roster_abilities=abilities, status="won",
        messages=[{"role": "challenger", "text": "突进"}, turn],
        cracked=[{"index": 1, "cracked": True}, {"index": 2, "cracked": False}],
    )

    async with async_session_factory() as db:
        detail = await scenario_domain.challenge_detail(challenge.id, current=challenger, db=db)
    assert detail["god_unlocked"] is False
    view = detail["messages"][-1]
    assert view["challenger_text"] == _CHALLENGER_TEXT
    assert "omniscient" not in view and "guardian_text" not in view

    # 全破 → 永久解锁（附上帝全文；守方正文仍不给）
    async with async_session_factory() as db:
        progress = await db.get(ScenarioRosterProgress, {"roster_id": challenge.roster_id, "challenger_id": challenger.id})
        progress.cracked_cards = [{"index": 1, "cracked": True}, {"index": 2, "cracked": True}]
        await db.commit()
    async with async_session_factory() as db:
        detail = await scenario_domain.challenge_detail(challenge.id, current=challenger, db=db)
    assert detail["god_unlocked"] is True
    view = detail["messages"][-1]
    assert view["omniscient"] == _GOD_TEXT and "guardian_text" not in view

    # 守方：只见自己正文、无上帝
    async with async_session_factory() as db:
        owner_detail = await scenario_domain.challenge_detail(challenge.id, current=owner, db=db)
    assert owner_detail["viewer_role"] == "owner"
    assert owner_detail["messages"] == [{"role": "guardian", "text": _GUARDIAN_TEXT, "created_at": "seed"}]
    assert _GOD_TEXT not in json.dumps(owner_detail, ensure_ascii=False, default=str)


async def test_resolve_turn_carries_god_only_when_unlocked():
    """SSE turn 门控：全破的挑战者回合携带上帝全文（仍无守方正文）。"""
    challenge, _, _ = await _seed_resolving_challenge(
        roster_abilities=[{"name": "术一", "effect": "e1"}], cracked=[{"index": 1, "cracked": True}],
    )
    stream = stream_module.get_scenario_stream(challenge.id)
    challenger_queue, _ = await stream.subscribe(side="challenger")

    with ExitStack() as stack:
        for p in _llm_patches():
            stack.enter_context(p)
        await asyncio.wait_for(flows.resolve_scenario_action(challenge.id), timeout=15)

    events = await _drain(challenger_queue)
    turn = next(e["turn"] for e in events if e["type"] == "turn")
    assert turn["omniscient"] == _GOD_TEXT
    assert "guardian_text" not in turn


async def test_stream_endpoint_passes_subscriber_side():
    """端点按订阅者角色传侧别：挑战者→challenger，守方→guardian。"""
    challenge, challenger, owner = await _seed_resolving_challenge()

    recorded: list[str | None] = []
    probe_queue: asyncio.Queue = asyncio.Queue()
    await probe_queue.put({"type": "done", "status": "won"})

    class _SpyStream:
        async def subscribe(self, side=None):
            recorded.append(side)
            return probe_queue, []

        def unsubscribe(self, queue):
            pass

    with patch.object(scenario_domain, "get_scenario_stream", lambda _: _SpyStream()):
        async with async_session_factory() as db:
            challenger_row = await db.get(User, challenger.id)
            owner_row = await db.get(User, owner.id)
        response = await scenario_domain.challenge_stream(challenge.id, current=challenger_row)
        generator = response.body_iterator
        assert (await generator.__anext__())  # 推进到首个事件，触发订阅
        await generator.aclose()
        response = await scenario_domain.challenge_stream(challenge.id, current=owner_row)
        generator = response.body_iterator
        assert (await generator.__anext__())
        await generator.aclose()
        # 无关用户 → 404
        async with async_session_factory() as db:
            stranger = User(username=f"sct_s_{uuid4().hex[:8]}", password_hash="x")
            db.add(stranger)
            await db.commit()
            await db.refresh(stranger)
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as excinfo:
            await scenario_domain.challenge_stream(challenge.id, current=stranger)
        assert excinfo.value.status_code == 404

    assert recorded == ["challenger", "guardian"]