import os
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient

from app.main import app


def _user(client: TestClient, prefix: str = "admin_test") -> tuple[str, dict[str, str]]:
    name = f"{prefix}_{uuid4().hex[:8]}"
    assert client.post("/api/auth/register", json={"username": name, "email": f"{name}@test.dev", "password": "secret123"}).status_code == 201
    token = client.post("/api/auth/login", json={"username": name, "email": f"{name}@test.dev", "password": "secret123"}).json()["access_token"]
    return name, {"Authorization": f"Bearer {token}"}


def _promote(name: str) -> None:
    with psycopg.connect(os.environ["DATABASE_URL"].replace("+asyncpg", "")) as db:
        db.execute("UPDATE users SET role='admin' WHERE username=%s", (name,))
        db.commit()


def test_admin_guard_and_user_crud():
    with TestClient(app) as client:
        _, user_headers = _user(client, "ordinary")
        assert client.get("/api/admin/users", headers=user_headers).status_code == 403
        name, admin_headers = _user(client, "adminuser")
        _promote(name)
        assert client.get("/api/admin/users", headers=admin_headers).status_code == 200
        created = client.post("/api/admin/users", headers=admin_headers, json={"username": "managed_user", "password": "secret123"})
        assert created.status_code == 201
        assert created.json()["ability_count"] == 0


def test_admin_ability_crud_uses_admin_as_default_owner():
    with TestClient(app) as client:
        name, headers = _user(client, "abiladmin")
        _promote(name)
        created = client.post("/api/admin/abilities", headers=headers, json={"name": "天火", "effect": "灼烧目标"})
        assert created.status_code == 201, created.text
        ability = created.json()
        me = client.get("/api/auth/me", headers=headers).json()
        assert ability["owner_id"] == me["id"]
        updated = client.put(f"/api/admin/abilities/{ability['id']}", headers=headers, json={"name": "天火改", "effect": "灼烧目标", "detail": "范围有限"})
        assert updated.status_code == 200 and updated.json()["name"] == "天火改"
        assert client.delete(f"/api/admin/abilities/{ability['id']}", headers=headers).status_code == 204


def test_admin_stats_and_llm_trace_endpoints():
    with TestClient(app) as client:
        name, headers = _user(client, "statsadm")
        _promote(name)
        assert client.get("/api/admin/stats", headers=headers).status_code == 200
        assert client.get("/api/admin/traffic", headers=headers).status_code == 200
        assert client.get("/api/admin/llm-traces", headers=headers).status_code == 200
        assert client.get("/api/admin/llm-traces/stats", headers=headers).status_code == 200
