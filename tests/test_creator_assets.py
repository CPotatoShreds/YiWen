from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def _auth(client: TestClient, prefix: str) -> dict[str, str]:
    username = f"{prefix}_{uuid4().hex[:8]}"
    assert client.post("/api/auth/register", json={"username": username, "email": f"{username}@test.dev", "password": "secret123"}).status_code == 201
    token = client.post("/api/auth/login", json={"username": username, "email": f"{username}@test.dev", "password": "secret123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _ability(client: TestClient, headers: dict[str, str], name: str = "星火") -> dict:
    response = client.post("/api/creator/abilities", headers=headers, json={"name": name, "effect": "留下火痕"})
    assert response.status_code == 201, response.text
    return response.json()


def test_user_assets_are_private_and_mutable_without_revisions():
    with TestClient(app) as client:
        owner = _auth(client, "asset_owner")
        other = _auth(client, "asset_other")
        ability = _ability(client, owner)
        character = client.post("/api/creator/characters", headers=owner, json={"name": "逐影", "ability_ids": [ability["id"]]}).json()

        assert client.get(f"/api/creator/abilities/{ability['id']}", headers=other).status_code == 404
        assert client.get(f"/api/creator/characters/{character['id']}", headers=other).status_code == 404
        saved = client.put(f"/api/creator/abilities/{ability['id']}", headers=owner, json={"name": "新名", "effect": "新效果", "detail": "限制"})
        assert saved.status_code == 200
        assert saved.json()["name"] == "新名"
        assert client.get(f"/api/creator/assets/{ability['id']}/revisions", headers=owner).status_code == 404


def test_character_binding_requires_owned_abilities_and_replaces_order():
    with TestClient(app) as client:
        owner = _auth(client, "bindown")
        other = _auth(client, "bindoth")
        first = _ability(client, owner, "第一门")
        second = _ability(client, owner, "第二门")
        foreign = _ability(client, other, "他人术")
        character = client.post("/api/creator/characters", headers=owner, json={"name": "守望", "ability_ids": [first["id"]]}).json()

        denied = client.put(f"/api/creator/characters/{character['id']}", headers=owner, json={"name": "守望", "ability_ids": [foreign["id"]]})
        assert denied.status_code == 400
        updated = client.put(f"/api/creator/characters/{character['id']}", headers=owner, json={"name": "守望", "ability_ids": [second["id"], first["id"], second["id"]]})
        assert updated.status_code == 200
        assert updated.json()["ability_ids"] == [second["id"], first["id"]]


def test_character_allows_at_most_four_abilities_and_deleting_ability_unbinds():
    with TestClient(app) as client:
        owner = _auth(client, "bindlim")
        abilities = [_ability(client, owner, f"术{i}") for i in range(5)]
        too_many = client.post("/api/creator/characters", headers=owner, json={"name": "五术", "ability_ids": [a["id"] for a in abilities]})
        assert too_many.status_code == 422
        character = client.post("/api/creator/characters", headers=owner, json={"name": "四术", "ability_ids": [a["id"] for a in abilities[:4]]}).json()
        assert client.delete(f"/api/creator/abilities/{abilities[0]['id']}", headers=owner).status_code == 204
        detail = client.get(f"/api/creator/characters/{character['id']}", headers=owner)
        assert detail.status_code == 200
        assert abilities[0]["id"] not in detail.json()["ability_ids"]
