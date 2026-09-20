"""用户系统测试：注册 / 登录 / 当前用户。"""

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def test_register_login_me():
    with TestClient(app) as client:
        uname = "testuser_" + uuid4().hex[:8]

        # 注册
        r = client.post("/api/auth/register", json={"username": uname, "email": f"{uname}@test.dev", "password": "secret123"})
        assert r.status_code == 201
        body = r.json()
        assert body["username"] == uname
        assert "rank_points" not in body
        assert "max_loadouts" not in body

        # 重名
        r2 = client.post("/api/auth/register", json={"username": uname, "email": f"{uname}@test.dev", "password": "secret123"})
        assert r2.status_code == 400

        # 密码过短
        r3 = client.post("/api/auth/register", json={"username": "x" + uuid4().hex[:8], "email": "x" + uuid4().hex[:8] + "@test.dev", "password": "123"})
        assert r3.status_code == 422

        # 登录
        r4 = client.post("/api/auth/login", json={"username": uname, "email": f"{uname}@test.dev", "password": "secret123"})
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
        assert "exp" not in me
        assert "rank_points" not in me
        assert "max_loadouts" not in me

        # 无 cookie / token
        with TestClient(app) as anonymous:
            r7 = anonymous.get("/api/auth/me")
        assert r7.status_code == 401


def test_refresh_rotation_reuse_detection_and_logout_revocation():
    with TestClient(app) as client:
        uname = "refresher_" + uuid4().hex[:8]
        assert client.post("/api/auth/register", json={"username": uname, "email": f"{uname}@test.dev", "password": "secret123"}).status_code == 201
        r = client.post("/api/auth/login", json={"username": uname, "email": f"{uname}@test.dev", "password": "secret123"})
        assert r.status_code == 200
        refresh1 = r.json()["refresh_token"]
        assert refresh1

        # 旋转：旧令牌作废，签发新对
        r2 = client.post("/api/auth/refresh", json={"refresh_token": refresh1})
        assert r2.status_code == 200
        refresh2 = r2.json()["refresh_token"]
        assert refresh2 and refresh2 != refresh1

        # 已旋转的 refresh1 再次出现 → 401，且按泄露处理撤销该用户全部令牌
        with TestClient(app) as bare:  # 无 cookie 的裸客户端，精确控制出示哪个令牌
            assert bare.post("/api/auth/refresh", json={"refresh_token": refresh1}).status_code == 401
            assert bare.post("/api/auth/refresh", json={"refresh_token": refresh2}).status_code == 401

        # 全撤销后重新登录 → 登出吊销 refresh → 再刷新 401
        r3 = client.post("/api/auth/login", json={"username": uname, "email": f"{uname}@test.dev", "password": "secret123"})
        assert r3.status_code == 200
        assert client.post("/api/auth/logout", json={"refresh_token": r3.json()["refresh_token"]}).status_code == 204
        assert client.post("/api/auth/refresh").status_code == 401
