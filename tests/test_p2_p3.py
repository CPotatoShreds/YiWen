"""P2/P3 验收测试：管理审计、错误码信封、RBAC 角色映射、注销/导出、保留策略、/metrics。"""

import os
import uuid
from datetime import UTC, datetime, timedelta

import psycopg
from fastapi.testclient import TestClient

from app.core.metrics import record_llm_call
from app.core.retention import purge_expired
from app.db.base import async_session_factory
from app.main import app
from app.models.llm_trace import LlmTrace
from app.models.request_log import RequestLog


def _register(client: TestClient, prefix: str = "p2p3") -> str:
    name = f"{prefix}_{uuid.uuid4().hex[:8]}"
    assert client.post("/api/auth/register", json={"username": name, "email": f"{name}@test.dev", "password": "secret123"}).status_code == 201
    return name


def _login(client: TestClient, name: str) -> dict[str, str]:
    r = client.post("/api/auth/login", json={"username": name, "email": f"{name}@test.dev", "password": "secret123"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _promote(name: str) -> None:
    with psycopg.connect(os.environ["DATABASE_URL"].replace("+asyncpg", "")) as db:
        db.execute("UPDATE users SET role='admin' WHERE username=%s", (name,))
        db.commit()


def test_rbac_role_mapping_and_error_envelope():
    with TestClient(app) as client:
        name = _register(client)
        headers = _login(client, name)

        # 错误码信封：错误密码登录 → {detail, code}
        r = client.post("/api/auth/login", json={"username": name, "password": "wrong-password"})
        assert r.status_code == 401
        assert r.json()["code"] == "AUTH_INVALID_CREDENTIALS"
        assert r.headers["X-Error-Code"] == "AUTH_INVALID_CREDENTIALS"

        # 管理端建号 is_admin=true → role=admin，响应 is_admin=true（属性兼容）
        _promote(name)
        r2 = client.post("/api/admin/users", headers=headers, json={"username": "rbac_" + uuid.uuid4().hex[:6], "password": "secret123", "is_admin": True})
        assert r2.status_code == 201 and r2.json()["is_admin"] is True

        # 审计留痕可查
        logs = client.get("/api/admin/audit-logs", headers=headers).json()
        actions = [entry["action"] for entry in logs]
        assert "user.create" in actions


def test_account_deletion_and_export():
    with TestClient(app) as client:
        name = _register(client, "deleteme")
        headers = _login(client, name)

        # 导出：包含 profile 与空集合结构
        exported = client.get("/api/auth/me/export", headers=headers)
        assert exported.status_code == 200
        data = exported.json()
        assert data["profile"]["username"] == name
        assert "abilities" in data and "challenges" in data

        # 注销（口令确认）→ 204
        r = client.request("DELETE", "/api/auth/me", headers=headers, json={"password": "secret123"})
        assert r.status_code == 204

        # 旧 access token 立即失效（deleted_at 拦截）；旧名号登录被拒（名号已匿名化）
        assert client.get("/api/auth/me", headers=headers).status_code == 401
        r2 = client.post("/api/auth/login", json={"username": name, "email": f"{name}@test.dev", "password": "secret123"})
        assert r2.status_code == 401 and r2.json()["code"] == "AUTH_INVALID_CREDENTIALS"


def test_retention_purge_expired_rows():
    async def _seed():
        async with async_session_factory() as db:
            old = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=400)
            db.add(LlmTrace(kind="test", operation="retention_test", status="ok", created_at=old))
            db.add(RequestLog(method="GET", path="/api/x", status_code=200, duration_ms=1, created_at=old))
            await db.commit()

    import asyncio

    asyncio.run(_seed())
    counts = asyncio.run(purge_expired(datetime.now(UTC).replace(tzinfo=None)))
    assert counts.get("llm_traces", 0) >= 1
    assert counts.get("request_logs", 0) >= 1


def test_metrics_endpoint_exposed():
    record_llm_call("metrics_probe", "ok")
    with TestClient(app) as client:
        r = client.get("/metrics")
    assert r.status_code == 200
    assert "ynfight_llm_calls_total" in r.text
