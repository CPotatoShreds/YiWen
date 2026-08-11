"""异闻榜测试：名望降序、榜上席位、榜外也能查到自己的名次。"""

import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import update

from app.db.base import async_session_factory
from app.main import app
from app.models.user import User


def _mk(client, prefix="testlb") -> tuple[str, str]:
    """注册 + 登录，返回 (用户名, token)。"""
    uname = f"{prefix}_" + uuid4().hex[:8]
    client.post("/api/auth/register", json={"username": uname, "password": "secret123"})
    tok = client.post("/api/auth/login", json={"username": uname, "password": "secret123"}).json()["access_token"]
    return uname, tok


async def _set_rank(username: str, rank_points: int) -> None:
    """直接改写名望（无对外改分接口，测试造榜用）。"""
    async with async_session_factory() as db:
        await db.execute(update(User).where(User.username == username).values(rank_points=rank_points))
        await db.commit()


def test_leaderboard_orders_and_reports_me():
    with TestClient(app) as client:
        a, tok_a = _mk(client)
        b, tok_b = _mk(client)
        asyncio.run(_set_rank(a, 1200))
        asyncio.run(_set_rank(b, 800))

        # 名望最高者居榜首；榜上附带见闻列
        data = client.get("/api/leaderboard", headers={"Authorization": f"Bearer {tok_a}"}).json()
        entries = data["entries"]
        assert entries[0]["username"] == a and entries[0]["rank"] == 1 and entries[0]["rank_points"] == 1200
        assert "exp" in entries[0]
        assert data["me"]["username"] == a and data["me"]["rank"] == 1

        # 名望降序：a（1200）一定排在 b（800）之前；若 b 在前 50 名内，验证榜内顺序
        a_index = next(i for i, e in enumerate(entries) if e["username"] == a)
        b_index = next((i for i, e in enumerate(entries) if e["username"] == b), None)
        if b_index is not None:
            assert a_index < b_index

        # 垫底异闻师即使榜外也能查到自己的名次，且必在 a 之后
        data2 = client.get("/api/leaderboard", headers={"Authorization": f"Bearer {tok_b}"}).json()
        assert data2["me"]["username"] == b and data2["me"]["rank"] > data["me"]["rank"]

        # 未登录不可见
        with TestClient(app) as anonymous:
            assert anonymous.get("/api/leaderboard").status_code == 401
