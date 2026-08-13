"""经济系统测试：每日签到（一日一次）/ 见闻槽位解锁 / 设置项。"""

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.models.user import loadout_capacity


def _mk(client, prefix="testeco") -> str:
    uname = f"{prefix}_" + uuid4().hex[:8]
    client.post("/api/auth/register", json={"username": uname, "password": "secret123"})
    return client.post("/api/auth/login", json={"username": uname, "password": "secret123"}).json()["access_token"]


def test_daily_login_once_per_day():
    with TestClient(app) as client:
        tok = _mk(client)
        h = {"Authorization": f"Bearer {tok}"}
        me = client.get("/api/auth/me", headers=h).json()
        assert me["exp"] == 10  # 每日开张 +10 见闻
        assert me["max_loadouts"] == 3
        # 同日重复签到不叠加
        me2 = client.get("/api/auth/me", headers=h).json()
        assert me2["exp"] == 10


def test_loadout_capacity():
    assert loadout_capacity(0) == 3
    assert loadout_capacity(49) == 3
    assert loadout_capacity(50) == 4  # 满 50 见闻解锁 +1 槽
    assert loadout_capacity(150) == 6
    assert loadout_capacity(250) == 8
    assert loadout_capacity(99999) == 99  # 封顶 99


def test_settings_reveal_on_miss():
    with TestClient(app) as client:
        tok = _mk(client)
        h = {"Authorization": f"Bearer {tok}"}
        assert client.get("/api/auth/me", headers=h).json()["reveal_on_miss"] is False
        r = client.put("/api/auth/settings", json={"reveal_on_miss": False}, headers=h)
        assert r.status_code == 200 and r.json()["reveal_on_miss"] is False
        assert client.get("/api/auth/me", headers=h).json()["reveal_on_miss"] is False
