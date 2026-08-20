"""好友系统测试：申请 / 接受 / 列表 / 切磋（切磋局不计名望）。"""

import re
import time
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def _deduce(text):
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=text)
    return llm


def _transcribe(a: str, b: str):
    chain = MagicMock()

    async def _ainvoke(kwargs):
        m_a = re.search(r"发起方奇人：([^\n【】]+)", kwargs.get("info", ""))
        m_b = re.search(r"对手奇人：([^\n【】]+)", kwargs.get("info", ""))
        name_a = (m_a.group(1).strip() if m_a else "") or "甲"
        name_b = (m_b.group(1).strip() if m_b else "") or "乙"
        return a if kwargs.get("viewer_name") == name_a else b

    chain.ainvoke = AsyncMock(side_effect=_ainvoke)
    return chain


def _wait_done(client, battle_id, headers, timeout=12):
    b = None
    for _ in range(int(timeout / 0.2)):
        b = client.get(f"/api/battles/{battle_id}", headers=headers).json()
        if b["status"] != "pending":
            return b
        time.sleep(0.2)
    return b


def _mk(client) -> str:
    uname = "testfr_" + uuid4().hex[:8]
    client.post("/api/auth/register", json={"username": uname, "password": "secret123"})
    return client.post("/api/auth/login", json={"username": uname, "password": "secret123"}).json()["access_token"]


def _arm(client, tok):
    """立起一位出战奇人（名 = 异闻师用户名）+ 装全部异能 + 解封。"""
    h = {"Authorization": f"Bearer {tok}"}
    uname = client.get("/api/auth/me", headers=h).json()["username"]
    ld = client.post("/api/loadouts", json={"name": uname}, headers=h).json()
    for a in client.get("/api/abilities/mine", headers=h).json():
        client.post(f"/api/loadouts/{ld['id']}/abilities/{a['id']}", headers=h)
    assert client.put(f"/api/loadouts/{ld['id']}", json={"enabled": True}, headers=h).status_code == 200
    return ld


def test_friends_and_challenge():
    with TestClient(app) as client:
        tok_a = _mk(client)
        tok_b = _mk(client)
        h_a = {"Authorization": f"Bearer {tok_a}"}
        h_b = {"Authorization": f"Bearer {tok_b}"}
        id_a = client.get("/api/auth/me", headers=h_a).json()["id"]
        id_b = client.get("/api/auth/me", headers=h_b).json()["id"]

        # A 申请 B
        assert client.post("/api/friends/request", json={"friend_id": id_b}, headers=h_a).status_code == 200
        # 重复申请 → 400
        assert client.post("/api/friends/request", json={"friend_id": id_b}, headers=h_a).status_code == 400
        # B 看到待处理
        reqs = client.get("/api/friends/requests", headers=h_b).json()
        assert len(reqs) == 1 and reqs[0]["id"] == id_a
        # B 接受
        assert client.post(f"/api/friends/{id_a}/accept", headers=h_b).status_code == 200
        # 双方好友列表互通
        assert any(f["id"] == id_b for f in client.get("/api/friends", headers=h_a).json())
        assert any(f["id"] == id_a for f in client.get("/api/friends", headers=h_b).json())

        # 两人各设定异能并装配 → 切磋（切磋局不计名望，但照常结算经验/首次对战）
        for tok, (nm, ef) in ((tok_a, ("影刃", "以暗影凝聚利刃斩杀敌人")), (tok_b, ("血咒", "以自身鲜血为引发动诅咒"))):
            assert client.post("/api/abilities", json={"name": nm, "effect": ef}, headers={"Authorization": f"Bearer {tok}"}).status_code == 201
        _arm(client, tok_a)
        _arm(client, tok_b)
        name_a = client.get("/api/auth/me", headers=h_a).json()["username"]
        with (
            patch("app.services.battle.lifecycle._build_deduce_llm", return_value=_deduce(f"上帝视角：双方周旋，A 击杀 B。胜者：{name_a}")),
            patch("app.services.battle.lifecycle._build_transcribe_side_chain", return_value=_transcribe("A 视角……", "B 视角……")),
        ):
            r = client.post(f"/api/battles/challenge/{id_b}", headers=h_a)
            assert r.status_code == 200
            assert r.json()["status"] == "pending"
            # 轮询期间后台任务才执行，patch 必须保持生效
            b = _wait_done(client, r.json()["id"], h_a)
        assert b["status"] == "done"
        assert b["rank_delta_a"] == 0
        assert b["rank_delta_b"] == 0
        # 见闻：签到10 + 对战5 + 首次5 = 20
        me_a = client.get("/api/auth/me", headers=h_a).json()
        me_b = client.get("/api/auth/me", headers=h_b).json()
        assert me_a["exp"] == 20 and me_b["exp"] == 20
