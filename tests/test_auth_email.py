"""邮箱体系测试：绑定验证、密码找回。console 邮件实现下捕获发信内容做断言。"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.routes import auth as auth_routes
from app.main import app


@pytest.fixture
def outbox(monkeypatch):
    sent: list[dict] = []

    async def fake_send(to: str, subject: str, body: str) -> None:
        sent.append({"to": to, "subject": subject, "body": body})

    monkeypatch.setattr(auth_routes, "send_email", fake_send)
    return sent


def _register_and_login(client: TestClient) -> str:
    uname = "mailer_" + uuid.uuid4().hex[:8]
    assert client.post("/api/auth/register", json={"username": uname, "email": f"{uname}@test.dev", "password": "secret123"}).status_code == 201
    assert client.post("/api/auth/login", json={"username": uname, "email": f"{uname}@test.dev", "password": "secret123"}).status_code == 200
    return uname


def _token_from(body: str) -> str:
    return body.split("token=")[1].split("\n")[0].strip()


def test_bind_verify_forgot_reset(outbox):
    with TestClient(app) as client:
        uname = _register_and_login(client)

        # 绑定邮箱 → 验证链接 → 验证落库
        assert client.post("/api/auth/me/email", json={"email": f"{uname}@test.dev"}).status_code == 202
        assert client.post("/api/auth/verify-email", json={"token": _token_from(outbox[-1]["body"])}).status_code == 200
        assert client.get("/api/auth/me").json()["email"] == f"{uname}@test.dev"

    # 密码找回 → 重置 → 新密码可登录
    with TestClient(app) as anon:
        assert anon.post("/api/auth/forgot-password", json={"email": f"{uname}@test.dev"}).status_code == 202
        assert anon.post("/api/auth/reset-password", json={
            "token": _token_from(outbox[-1]["body"]), "new_password": "newpass456",
        }).status_code == 200
        assert anon.post("/api/auth/login", json={"username": uname, "password": "newpass456"}).status_code == 200
        # 旧密码失效
        assert anon.post("/api/auth/login", json={"username": uname, "email": f"{uname}@test.dev", "password": "secret123"}).status_code == 401


def test_forgot_unknown_email_still_accepted():
    with TestClient(app) as anon:
        r = anon.post("/api/auth/forgot-password", json={"email": f"nope_{uuid.uuid4().hex[:6]}@test.dev"})
    assert r.status_code == 202  # 不泄露邮箱是否存在


def test_reset_invalid_token_rejected():
    with TestClient(app) as client:
        r = client.post("/api/auth/reset-password", json={"token": "garbage", "new_password": "secret123"})
    assert r.status_code == 400


def test_bind_duplicate_email_rejected(outbox):
    with TestClient(app) as first:
        uname = _register_and_login(first)
        email = f"{uname}@shared.dev"
        first.post("/api/auth/me/email", json={"email": email})
        assert first.post("/api/auth/verify-email", json={"token": _token_from(outbox[-1]["body"])}).status_code == 200
    with TestClient(app) as second:
        _register_and_login(second)
        # 预检直接拒绝已被占用的邮箱（无需等验证环节）
        assert second.post("/api/auth/me/email", json={"email": email}).status_code == 400
