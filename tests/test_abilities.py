"""用户自定义异能测试：创建 / 列表 / 更新 / 删除。"""

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def _new_user(client) -> str:
    uname = "testabil_" + uuid4().hex[:8]
    client.post("/api/auth/register", json={"username": uname, "password": "secret123"})
    return client.post("/api/auth/login", json={"username": uname, "password": "secret123"}).json()["access_token"]


def test_create_list_update_delete():
    with TestClient(app) as client:
        tok = _new_user(client)
        h = {"Authorization": f"Bearer {tok}"}

        # 空名称 → 400
        assert client.post("/api/abilities", json={"name": "", "effect": "x"}, headers=h).status_code == 400

        # 创建
        r = client.post("/api/abilities", json={"name": "燃烬之握", "effect": "接触的物体被点燃为不灭的火焰"}, headers=h)
        assert r.status_code == 201
        aid = r.json()["id"]
        assert r.json()["name"] == "燃烬之握"

        # 重复创建同内容 → 幂等（不新增一条）
        r2 = client.post("/api/abilities", json={"name": "燃烬之握", "effect": "接触的物体被点燃为不灭的火焰"}, headers=h)
        assert r2.status_code == 201 and r2.json()["id"] == aid
        assert len(client.get("/api/abilities/mine", headers=h).json()) == 1

        # 再建一个
        client.post("/api/abilities", json={"name": "霜语", "effect": "冻结空气中的水分"}, headers=h)
        mine = client.get("/api/abilities/mine", headers=h).json()
        assert len(mine) == 2

        # 更新
        r3 = client.put(f"/api/abilities/{aid}", json={"name": "燃烬之握·改", "effect": "火焰温度随心念升降"}, headers=h)
        assert r3.status_code == 200 and r3.json()["effect"] == "火焰温度随心念升降"

        # 删除
        assert client.delete(f"/api/abilities/{aid}", headers=h).status_code == 204
        assert len(client.get("/api/abilities/mine", headers=h).json()) == 1

        # 删除不存在的 → 404
        assert client.delete(f"/api/abilities/{aid}", headers=h).status_code == 404
