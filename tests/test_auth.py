"""用户系统测试：注册 / 登录 / 当前用户。"""

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def test_register_login_me():
    with TestClient(app) as client:
        uname = "testuser_" + uuid4().hex[:8]

        # 注册
        r = client.post("/api/auth/register", json={"username": uname, "password": "secret123"})
        assert r.status_code == 201
        body = r.json()
        assert body["username"] == uname
        assert body["rank_points"] == 1000  # 名望起始 1000
        assert body["max_loadouts"] == 3  # 初始 3 个奇人槽位

        # 重名
        r2 = client.post("/api/auth/register", json={"username": uname, "password": "secret123"})
        assert r2.status_code == 400

        # 密码过短
        r3 = client.post("/api/auth/register", json={"username": "x" + uuid4().hex[:8], "password": "123"})
        assert r3.status_code == 422

        # 登录
        r4 = client.post("/api/auth/login", json={"username": uname, "password": "secret123"})
        assert r4.status_code == 200
        token = r4.json()["access_token"]

        # 错误密码
        r5 = client.post("/api/auth/login", json={"username": uname, "password": "wrongpass"})
        assert r5.status_code == 401

        # 当前用户（带 token）
        r6 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r6.status_code == 200
        me = r6.json()
        assert me["username"] == uname
        assert me["exp"] == 10  # 每日开张 +10 见闻
        assert me["rank_points"] == 1000
        assert me["max_loadouts"] == 3

        # 无 cookie / token
        with TestClient(app) as anonymous:
            r7 = anonymous.get("/api/auth/me")
        assert r7.status_code == 401
