import asyncio
from types import SimpleNamespace

from app.services.guess import pipeline
from app.services.scenario.views import public_cards, public_guess_rounds


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
