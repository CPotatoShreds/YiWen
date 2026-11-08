import json
import os
from unittest.mock import patch
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient

from app.main import app


def _user(client: TestClient, prefix: str) -> tuple[str, dict]:
    name = f"{prefix}_{uuid4().hex[:8]}"
    assert client.post("/api/auth/register", json={"username": name, "email": f"{name}@test.dev", "password": "secret123"}).status_code == 201
    token = client.post("/api/auth/login", json={"username": name, "email": f"{name}@test.dev", "password": "secret123"}).json()["access_token"]
    return name, {"Authorization": f"Bearer {token}"}


def _character(client: TestClient, headers: dict, name: str) -> str:
    ability = client.post("/api/creator/abilities", headers=headers, json={"name": f"术{name}", "effect": "留下可观察痕迹"}).json()
    character = client.post("/api/creator/characters", headers=headers, json={"name": name, "bio": "擅长追踪"}).json()
    response = client.put(
        f"/api/creator/characters/{character['id']}",
        headers=headers,
        json={"name": name, "bio": "擅长追踪", "ability_ids": [ability["id"]]},
    )
    assert response.status_code == 200, response.text
    return character["id"]


def _promote(name: str) -> None:
    with psycopg.connect(os.environ["DATABASE_URL"].replace("+asyncpg", "")) as db:
        db.execute("UPDATE users SET role='admin' WHERE username=%s", (name,))
        db.commit()


async def _no_background_work(_: object) -> None:
    return None


def _scenario_payload(name: str) -> dict:
    return {
        "name": name,
        "subtitle": "见招拆招",
        "introduction": "正面对决，击溃对手",
        "background": "双方在结界中展开对决",
        "rules": ["不得离开结界"],
        "victory_condition": "让对方失去战斗能力",
        "judgement_rules": ["双方皆失去战斗能力判定为失败"],
    }


def test_roster_is_public_and_author_trial_is_excluded_from_stats():
    with TestClient(app) as client, patch("app.services.scenario.flows.prepare_scenario_challenge", _no_background_work):
        admin_name, admin = _user(client, "scadm")
        assert client.post("/api/admin/scenarios", headers=admin, json=_scenario_payload("追捕")).status_code == 403
        _promote(admin_name)
        admin = {"Authorization": admin["Authorization"]}
        scenario = client.post("/api/admin/scenarios", headers=admin, json=_scenario_payload("追捕"))
        assert scenario.status_code == 201, scenario.text
        assert scenario.json()["subtitle"] == "见招拆招"
        assert scenario.json()["rules"] == ["不得离开结界"]
        assert scenario.json()["judgement_rules"] == ["双方皆失去战斗能力判定为失败"]
        assert scenario.json()["slug"] == "zhui-bu"
        assert client.post(f"/api/admin/scenarios/{scenario.json()['id']}/publish", headers=admin).status_code == 200
        _, author = _user(client, "scauth")
        character_id = _character(client, author, "清风")
        roster = client.post(f"/api/creator/scenarios/{scenario.json()['id']}/rosters", headers=author, json={"character_id": character_id, "guidance": "沿着脚印追踪"})
        assert roster.status_code == 201, roster.text
        assert "kind" not in roster.json()
        assert client.get(f"/api/scenarios/{scenario.json()['id']}/rosters").json()[0]["id"] == roster.json()["id"]
        assert client.get(f"/api/scenarios/{scenario.json()['slug']}").json()["id"] == scenario.json()["id"]
        assert client.get(f"/api/scenarios/{scenario.json()['slug']}/rosters").json()[0]["id"] == roster.json()["id"]
        challenge = client.post(f"/api/scenario-rosters/{roster.json()['id']}/challenges", headers=author, json={"character_id": character_id})
        assert challenge.status_code == 201, challenge.text
        assert challenge.json()["challenge_number"] == 1
        challenge_detail = client.get(f"/api/scenario-challenges/{challenge.json()['id']}", headers=author)
        assert challenge_detail.status_code == 200, challenge_detail.text
        assert challenge_detail.json()["scenario"]["rules"] == ["不得离开结界"]
        assert challenge_detail.json()["scenario"]["judgement_rules"] == ["双方皆失去战斗能力判定为失败"]
        public_roster = client.get(f"/api/scenarios/{scenario.json()['id']}/rosters").json()[0]
        assert public_roster["challenge_count"] == 0
        assert public_roster["challenger_win_rate"] is None


def test_challenge_prepares_before_actions_and_accepts_action_asynchronously():
    with TestClient(app) as client, patch("app.services.scenario.flows.prepare_scenario_challenge", _no_background_work), patch("app.services.scenario.flows.run_scenario_deduction", _no_background_work):
        admin_name, admin = _user(client, "streamadm")
        _promote(admin_name)
        scenario = client.post("/api/admin/scenarios", headers=admin, json=_scenario_payload("流式追捕")).json()
        assert client.post(f"/api/admin/scenarios/{scenario['id']}/publish", headers=admin).status_code == 200
        _, author = _user(client, "streamusr")
        character_id = _character(client, author, "流影")
        roster = client.post(f"/api/creator/scenarios/{scenario['id']}/rosters", headers=author, json={"character_id": character_id, "guidance": "沿着脚印追踪"}).json()
        challenge = client.post(f"/api/scenario-rosters/{roster['id']}/challenges", headers=author, json={"character_id": character_id}).json()
        assert challenge["status"] == "preparing"

        with psycopg.connect(os.environ["DATABASE_URL"].replace("+asyncpg", "")) as db:
            db.execute("UPDATE scenario_challenge_runs SET status='active' WHERE id=%s", (challenge["id"],))
            db.commit()
        action = client.post(f"/api/scenario-challenges/{challenge['id']}/actions", headers=author, json={"text": "翻墙越过城门"})
        assert action.status_code == 202, action.text
        detail = client.get(f"/api/scenario-challenges/{challenge['id']}", headers=author).json()
        assert detail["status"] == "resolving"
        assert detail["messages"][-1]["text"] == "翻墙越过城门"


def test_roster_detail_scopes_history_and_progress_to_viewer():
    with TestClient(app) as client, patch("app.services.scenario.flows.prepare_scenario_challenge", _no_background_work):
        admin_name, admin = _user(client, "detailadm")
        _promote(admin_name)
        scenario = client.post("/api/admin/scenarios", headers=admin, json=_scenario_payload("详情追捕")).json()
        assert client.post(f"/api/admin/scenarios/{scenario['id']}/publish", headers=admin).status_code == 200
        _, author = _user(client, "dauthor")
        _, challenger = _user(client, "dchallenger")
        author_character = _character(client, author, "守风")
        challenger_character = _character(client, challenger, "逐影")
        roster = client.post(f"/api/creator/scenarios/{scenario['id']}/rosters", headers=author, json={"character_id": author_character, "guidance": "沿脚印追踪"}).json()
        run = client.post(f"/api/scenario-rosters/{roster['id']}/challenges", headers=challenger, json={"character_id": challenger_character}).json()
        detail = client.get(f"/api/scenarios/{scenario['id']}/rosters/{roster['id']}", headers=challenger)
        assert detail.status_code == 200, detail.text
        assert detail.json()["viewer_role"] == "challenger"
        assert [item["id"] for item in detail.json()["my_challenges"]] == [run["id"]]
        # 作者侧不再有「他人来打」的汇总列表：这条数据通路是挑战者策略原文唯一的越权载体，已整块移除
        assert "owner_challenges" not in detail.json()
        assert "next_cursor" not in detail.json()
        owner_detail = client.get(f"/api/scenarios/{scenario['id']}/rosters/{roster['id']}", headers=author)
        assert owner_detail.status_code == 200, owner_detail.text
        assert owner_detail.json()["viewer_role"] == "owner"
        # 作者在这个页面上只能看到自己发起的对局（这条数据里是零），看不到别人那一局
        assert owner_detail.json()["my_challenges"] == []
        assert "owner_challenges" not in owner_detail.json()
        assert "next_cursor" not in owner_detail.json()
        assert client.get(f"/api/scenarios/{scenario['id']}/rosters/{run['id']}", headers=challenger).status_code == 404


def test_scenario_slug_uses_a_short_suffix_on_collision():
    with TestClient(app) as client:
        admin_name, admin = _user(client, "slugadm")
        _promote(admin_name)
        first = client.post("/api/admin/scenarios", headers=admin, json=_scenario_payload("山 河")).json()
        second = client.post("/api/admin/scenarios", headers=admin, json=_scenario_payload("山-河")).json()

        assert first["slug"] == "shan-he"
        assert second["slug"].startswith("shan-he-")
        assert len(second["slug"].rsplit("-", 1)[1]) == 8


def test_self_challenge_returns_both_views_with_deduction():
    """自己打自己的刻印：两边都是己方，视为全部看破，推演与双方正文一起下发。"""
    with TestClient(app) as client, patch("app.services.scenario.flows.prepare_scenario_challenge", _no_background_work):
        admin_name, admin = _user(client, "selfadm")
        _promote(admin_name)
        scenario = client.post("/api/admin/scenarios", headers=admin, json=_scenario_payload("自试卷")).json()
        assert client.post(f"/api/admin/scenarios/{scenario['id']}/publish", headers=admin).status_code == 200
        _, author = _user(client, "selfauthor")
        guardian = _character(client, author, "守风")
        challenger = _character(client, author, "逐影")
        roster = client.post(
            f"/api/creator/scenarios/{scenario['id']}/rosters",
            headers=author,
            json={"character_id": guardian, "guidance": "守着"},
        ).json()
        run = client.post(
            f"/api/scenario-rosters/{roster['id']}/challenges",
            headers=author,
            json={"character_id": challenger},
        ).json()
        assert run["is_trial"] is True

        turn = {
            "role": "views",
            "challenger_text": "己方所见",
            "guardian_text": "刻印所见",
            "omniscient": "推演全文",
            "achieved": True,
            "reason": "达成",
            "created_at": "seed",
        }
        with psycopg.connect(os.environ["DATABASE_URL"].replace("+asyncpg", "")) as db:
            db.execute(
                "UPDATE scenario_challenge_runs SET messages = (messages::jsonb || %s::jsonb) WHERE id = %s",
                (json.dumps([turn], ensure_ascii=False), run["id"]),
            )
            db.commit()

        detail = client.get(f"/api/scenario-challenges/{run['id']}", headers=author).json()
        assert detail["viewer_role"] == "both"
        assert detail["god_unlocked"] is True
        views = detail["messages"][-1]
        assert views["challenger_text"] == "己方所见"
        assert views["guardian_text"] == "刻印所见"
        assert views["omniscient"] == "推演全文"


def test_roster_detail_gives_author_every_card_as_known():
    """作者看自己的刻印：卡面恒为已知——判据是"你是这套刻印的作者"，不是看破进度，也不看试炼标记。"""
    with TestClient(app) as client:
        admin_name, admin = _user(client, "ownadm")
        _promote(admin_name)
        scenario = client.post("/api/admin/scenarios", headers=admin, json=_scenario_payload("自识卷"))
        assert scenario.status_code == 201, scenario.text
        assert client.post(f"/api/admin/scenarios/{scenario.json()['id']}/publish", headers=admin).status_code == 200
        _, author = _user(client, "ownauthor")
        guardian = _character(client, author, "守风")
        roster = client.post(
            f"/api/creator/scenarios/{scenario.json()['id']}/rosters",
            headers=author,
            json={"character_id": guardian, "guidance": "守着"},
        )
        assert roster.status_code == 201, roster.text

        # 作者一次挑战都没发起过，也不该看到"未看破"
        detail = client.get(f"/api/scenarios/{scenario.json()['slug']}/rosters/{roster.json()['id']}", headers=author)
        assert detail.status_code == 200, detail.text
        assert detail.json()["viewer_role"] == "owner"
        cards = detail.json()["my_progress"]["cracked_cards"]
        assert cards and all(card["cracked"] and card["name"] for card in cards)

        # 旁人同一份刻印仍是未看破（没有进度就没有卡面）
        _, stranger = _user(client, "ownother")
        other = client.get(f"/api/scenarios/{scenario.json()['slug']}/rosters/{roster.json()['id']}", headers=stranger)
        assert other.status_code == 200, other.text
        assert other.json()["viewer_role"] == "challenger"
        assert other.json()["my_progress"] is None


def test_roster_snapshot_accepts_legacy_long_ability_effect():
    """存量奇术效果可能超过 50 字（2026-09-02 前入参无长度校验），刻印不应 500。

    回归：scenario_roster_abilities.effect 曾是 varchar(50)，快照这类奇术时
    asyncpg 抛 StringDataRightTruncationError，接口直接 500。
    """
    long_effect = "经验+3，这个奇术会让拥有者忍不住想对着别人说“经验+3”这个短语。只要出现“经验+3”，就视为该奇术已被看破"
    assert len(long_effect) > 50
    with TestClient(app) as client:
        admin_name, admin = _user(client, "wdeadm")
        _promote(admin_name)
        scenario = client.post("/api/admin/scenarios", headers=admin, json=_scenario_payload("刻印长文"))
        assert scenario.status_code == 201, scenario.text
        assert client.post(f"/api/admin/scenarios/{scenario.json()['id']}/publish", headers=admin).status_code == 200

        _, author = _user(client, "wdeauth")
        ability = client.post("/api/creator/abilities", headers=author, json={"name": "经验术", "effect": "占位效果"}).json()
        with psycopg.connect(os.environ["DATABASE_URL"].replace("+asyncpg", "")) as db:
            db.execute("UPDATE abilities SET effect=%s WHERE id=%s", (long_effect, ability["id"]))
            db.commit()
        character = client.post("/api/creator/characters", headers=author, json={"name": "长文客", "bio": "写得长"}).json()
        assert client.put(
            f"/api/creator/characters/{character['id']}",
            headers=author,
            json={"name": "长文客", "bio": "写得长", "ability_ids": [ability["id"]]},
        ).status_code == 200

        roster = client.post(
            f"/api/creator/scenarios/{scenario.json()['id']}/rosters",
            headers=author,
            json={"character_id": character["id"], "guidance": "守着"},
        )
        assert roster.status_code == 201, roster.text
        with psycopg.connect(os.environ["DATABASE_URL"].replace("+asyncpg", "")) as db:
            snapshot = db.execute(
                "SELECT effect FROM scenario_roster_abilities WHERE roster_id=%s ORDER BY position",
                (roster.json()["id"],),
            ).fetchall()
            revision = db.execute(
                "SELECT a.effect FROM scenario_roster_revision_abilities a"
                " JOIN scenario_roster_revisions r ON r.id = a.revision_id"
                " WHERE r.roster_id=%s ORDER BY a.position",
                (roster.json()["id"],),
            ).fetchall()
        assert [row[0] for row in snapshot] == [long_effect]
        assert [row[0] for row in revision] == [long_effect]


def test_roster_snapshot_accepts_legacy_long_ability_name_and_detail():
    """存量奇术的名字/说明可能超过快照列宽，刻印不应 500。

    回归：快照表 name 曾是 varchar(10)、detail 曾是 varchar(500)，而源表
    abilities.name 是 varchar(50)、detail 是 text。刻印原样复制、不做截断，
    源表更宽就会撞列宽（asyncpg StringDataRightTruncationError）。
    """
    long_name = "太上忘情万象归元大法诀"
    long_detail = "此术以血为引，引雷入体，三息为限；逾时雷意反噬己身，故须在雷光未散前收势。\n" * 15
    assert len(long_name) > 10 and len(long_detail) > 500
    with TestClient(app) as client:
        admin_name, admin = _user(client, "wddadm")
        _promote(admin_name)
        scenario = client.post("/api/admin/scenarios", headers=admin, json=_scenario_payload("刻印长文二"))
        assert scenario.status_code == 201, scenario.text
        assert client.post(f"/api/admin/scenarios/{scenario.json()['id']}/publish", headers=admin).status_code == 200

        _, author = _user(client, "wdaauth")
        ability = client.post("/api/creator/abilities", headers=author, json={"name": "归元术", "effect": "占位效果"}).json()
        with psycopg.connect(os.environ["DATABASE_URL"].replace("+asyncpg", "")) as db:
            db.execute("UPDATE abilities SET name=%s, detail=%s WHERE id=%s", (long_name, long_detail, ability["id"]))
            db.commit()
        character = client.post("/api/creator/characters", headers=author, json={"name": "归元客", "bio": "写得长"}).json()
        assert client.put(
            f"/api/creator/characters/{character['id']}",
            headers=author,
            json={"name": "归元客", "bio": "写得长", "ability_ids": [ability["id"]]},
        ).status_code == 200

        roster = client.post(
            f"/api/creator/scenarios/{scenario.json()['id']}/rosters",
            headers=author,
            json={"character_id": character["id"], "guidance": "守着"},
        )
        assert roster.status_code == 201, roster.text
        with psycopg.connect(os.environ["DATABASE_URL"].replace("+asyncpg", "")) as db:
            snapshot = db.execute(
                "SELECT name, detail FROM scenario_roster_abilities WHERE roster_id=%s ORDER BY position",
                (roster.json()["id"],),
            ).fetchall()
            revision = db.execute(
                "SELECT a.name, a.detail FROM scenario_roster_revision_abilities a"
                " JOIN scenario_roster_revisions r ON r.id = a.revision_id"
                " WHERE r.roster_id=%s ORDER BY a.position",
                (roster.json()["id"],),
            ).fetchall()
        assert snapshot == [(long_name, long_detail)]
        assert revision == [(long_name, long_detail)]
