import asyncio
from types import SimpleNamespace

from app.services.guess import pipeline
from app.services.scenario import flows
from app.services.scenario.views import public_cards, public_guess_rounds


def test_public_verification_history_exposes_only_identity_order_and_boolean():
    payload = public_cards([{
        "index": 1, "cracked": False,
        "verifies": [{"id": "verify-1", "round": 2, "created_at": "2026-11-16T01:00:00", "cracked": False, "missing": "秘密条件", "reason": "内部分析"}, "old-invalid"],
    }])
    assert payload[0]["verifies"] == [{"id": "verify-1", "round": 2, "created_at": "2026-11-16T01:00:00", "cracked": False}]
    assert "秘密条件" not in str(payload)
    assert "内部分析" not in str(payload)


def test_verification_uses_one_id_and_fixed_guess_round_for_all_card_results(monkeypatch):
    from contextlib import asynccontextmanager

    from app.models.scenario_domain import ScenarioChallengeRun

    challenge = SimpleNamespace(roster_id="roster-1", challenger_id=1, roster_snapshot={"abilities": [{"name": "甲", "effect": "甲"}, {"name": "乙", "effect": "乙"}]}, verify_in_flight=True)
    progress = SimpleNamespace(cracked_cards=[], guess_rounds=[{"text": "猜测一"}, {"text": "猜测二"}])
    saved = []

    class Session:
        async def get(self, model, _key):
            return challenge if model is ScenarioChallengeRun else progress

        async def commit(self):
            pass

    @asynccontextmanager
    async def session():
        yield Session()

    async def verification(**kwargs):
        progress.guess_rounds.append({"text": "后来新增"})
        await kwargs["on_result"](1, {"cracked": False, "missing": "内部"})
        await kwargs["on_result"](0, {"cracked": True, "missing": ""})

    async def save(_challenge_id, index, _verdict, **metadata):
        saved.append({"index": index, **metadata})

    monkeypatch.setattr(flows, "async_session_factory", session)
    monkeypatch.setattr(flows, "run_guess_verification", verification)
    monkeypatch.setattr(flows, "save_verify_result", save)
    asyncio.run(flows.run_guess_verify("challenge-1", "verification-1"))
    assert [item["verification_id"] for item in saved] == ["verification-1", "verification-1"]
    assert [item["round_no"] for item in saved] == [2, 2]
    assert saved[0]["created_at"] == saved[1]["created_at"]
    assert challenge.verify_in_flight is False


def test_public_guess_payload_hides_missing_and_normalizes_uncertain_verdict():
    cards = public_cards(
        [
            {
                "index": 1,
                "cracked": False,
                "name": "不应公开",
                "missing": "不应公开",
                "feedback": [{"text": "范围", "verdict": "不能确定", "reason": "内部"}],
            },
            {"index": 2, "cracked": True, "name": "墨影", "effect": "留痕", "missing": ""},
        ]
    )
    assert cards == [
        {"index": 1, "cracked": False, "feedback": [{"text": "范围", "verdict": "不确定", "round": None}]},
        {"index": 2, "cracked": True, "name": "墨影", "effect": "留痕"},
    ]

    rounds = public_guess_rounds(
        [{"id": "r1", "text": "全图", "comments": [{"index": 1, "items": [{"text": "范围", "verdict": "不能确定", "reason": "内部"}]}], "missing": "不应公开"}]
    )
    assert rounds[0]["comments"][0]["items"] == [{"text": "范围", "verdict": "不确定"}]
    assert "missing" not in str(rounds)


def test_matching_runs_every_atom_card_pair_and_streams_results(monkeypatch):
    calls = []

    async def fake_invoke(chain, messages, **kwargs):
        calls.append(str(messages))
        return SimpleNamespace(text="原子命中", verdict="部分是", reason="内部")

    monkeypatch.setattr(pipeline, "ainvoke_with_reliability", fake_invoke)
    streamed = []

    async def on_match(match):
        streamed.append(match)

    result = asyncio.run(
        pipeline.run_guess_matching(
            items=["线索一", "线索二", "线索三", "线索四"],
            abilities=[{"name": f"术{i}", "effect": "效果"} for i in range(4)],
            cards=[{"cracked": False} for _ in range(4)],
            build_pair=lambda **_: object(),
            on_match=on_match,
        )
    )
    assert len(calls) == 16
    assert len(result) == len(streamed) == 16
    assert {item["verdict"] for item in result} == {"部分是"}
