from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def _token(client: TestClient, prefix: str) -> str:
    username = f"{prefix}_{uuid4().hex[:8]}"
    assert client.post("/api/auth/register", json={"username": username, "password": "secret123"}).status_code == 201
    return client.post("/api/auth/login", json={"username": username, "password": "secret123"}).json()["access_token"]


def test_private_components_are_current_and_have_no_revision_api():
    with TestClient(app) as client:
        token = _token(client, "creator")
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post("/api/creator/abilities", headers=headers, json={"name": "星火", "effect": "点燃目标", "detail": "留下火痕"})
        assert created.status_code == 201
        asset_id = created.json()["id"]
        assert client.post("/api/creator/abilities", headers=headers, json={"name": "星火", "effect": "效果"}).status_code == 409
        assert client.put(f"/api/creator/abilities/{asset_id}", headers=headers, json={"name": "更新", "effect": "效果", "lock_version": 99}).status_code == 409
        saved = client.put(f"/api/creator/abilities/{asset_id}", headers=headers, json={"name": "更新", "effect": "效果", "detail": "更新后的详述", "lock_version": 1})
        assert saved.status_code == 200
        assert saved.json()["lock_version"] == 2
        listed = client.get("/api/creator/abilities", headers=headers)
        assert listed.status_code == 200
        assert listed.json()[0]["content"] == {"name": "更新", "effect": "效果", "detail": "更新后的详述"}
        assert client.get(f"/api/creator/assets/{asset_id}/revisions", headers=headers).status_code == 404
