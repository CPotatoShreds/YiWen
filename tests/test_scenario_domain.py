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
    with TestClient(app) as client, patch("app.services.scenario.flows.prepare_scenario_challenge", _no_background_work), patch("app.services.scenario.flows.resolve_scenario_action", _no_background_work):
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
        challenger_name, challenger = _user(client, "dchallenger")
        author_character = _character(client, author, "守风")
        challenger_character = _character(client, challenger, "逐影")
        roster = client.post(f"/api/creator/scenarios/{scenario['id']}/rosters", headers=author, json={"character_id": author_character, "guidance": "沿脚印追踪"}).json()
        run = client.post(f"/api/scenario-rosters/{roster['id']}/challenges", headers=challenger, json={"character_id": challenger_character}).json()
        detail = client.get(f"/api/scenarios/{scenario['id']}/rosters/{roster['id']}", headers=challenger)
        assert detail.status_code == 200, detail.text
        assert detail.json()["viewer_role"] == "challenger"
        assert [item["id"] for item in detail.json()["my_challenges"]] == [run["id"]]
        assert detail.json()["owner_challenges"] == []
        owner_detail = client.get(f"/api/scenarios/{scenario['id']}/rosters/{roster['id']}", headers=author)
        assert owner_detail.status_code == 200, owner_detail.text
        assert owner_detail.json()["viewer_role"] == "owner"
        assert owner_detail.json()["owner_challenges"][0]["challenger_name"] == challenger_name
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
