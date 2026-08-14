"""自配 LLM 方案测试：CRUD / 激活互斥 / 属主越权 / api_key 掩码 / 加解密落库 / 模型覆盖逻辑 / 对战链路透传。"""

import asyncio
import base64
import time
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.services.deduction import DeductionResult


def _encrypt_transit(plain: str) -> str:
    """模拟前端 jsencrypt：取 RSA 公钥 PKCS1v15 加密 + base64。"""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    from app.services import profile_crypto

    pub = serialization.load_pem_public_key(profile_crypto.get_public_key_pem().encode())
    return base64.b64encode(pub.encrypt(plain.encode(), padding.PKCS1v15())).decode()


def _make_user(client, prefix="u") -> str:
    uname = f"{prefix}_" + uuid4().hex[:8]
    r = client.post("/api/auth/register", json={"username": uname, "password": "secret123"})
    assert r.status_code == 201
    r = client.post("/api/auth/login", json={"username": uname, "password": "secret123"})
    assert r.status_code == 200
    return r.json()["access_token"]


def _create_profile(client, headers=None, **over):
    body = {
        "label": "我的方案",
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com",
        "api_key": _encrypt_transit("sk-test-123"),
        "model": "deepseek-chat",
        **over,
    }
    return client.post("/api/llm-profiles", json=body, headers=headers)


def test_crud_and_activation():
    with TestClient(app) as client:
        _make_user(client)

        # 创建首个：自动激活；api_key 明文不回传，只给 has_api_key
        r = _create_profile(client)
        assert r.status_code == 201
        p1 = r.json()
        assert p1["is_active"] is True
        assert p1["has_api_key"] is True
        assert "api_key" not in p1
        assert p1["base_url"] == "https://api.deepseek.com"

        # 创建第二个：不自动激活
        p2 = _create_profile(client, label="方案二", model="gpt-4o-mini").json()
        assert p2["is_active"] is False

        # 列表：单激活指针
        lst = client.get("/api/llm-profiles").json()
        assert len(lst) == 2
        assert [p["id"] for p in lst if p["is_active"]] == [p1["id"]]

        # 激活第二个 → 互斥（第一个不再激活）
        assert client.post(f"/api/llm-profiles/{p2['id']}/activate").status_code == 200
        lst = client.get("/api/llm-profiles").json()
        assert [p["id"] for p in lst if p["is_active"]] == [p2["id"]]

        # 更新：空 api_key 保留原值
        r4 = client.put(f"/api/llm-profiles/{p2['id']}", json={"model": "gpt-4o"})
        assert r4.status_code == 200
        assert r4.json()["model"] == "gpt-4o"
        assert r4.json()["has_api_key"] is True

        # 删除激活方案 → 激活指针清空，剩余方案不再激活
        assert client.delete(f"/api/llm-profiles/{p2['id']}").status_code == 204
        lst = client.get("/api/llm-profiles").json()
        assert len(lst) == 1
        assert lst[0]["is_active"] is False

        assert client.delete(f"/api/llm-profiles/{p1['id']}").status_code == 204
        assert client.get("/api/llm-profiles").json() == []


def test_requires_api_key_and_auth():
    with TestClient(app) as client:
        # 未登录 → 401
        assert client.get("/api/llm-profiles").status_code == 401
        _make_user(client)
        # api_key 必填
        assert _create_profile(client, api_key="").status_code == 422


def test_ownership_isolation():
    with TestClient(app) as client:
        _make_user(client)  # A
        p = _create_profile(client).json()
        _make_user(client, "v")  # B（登录会替换 cookie）
        # B 看不到、也动不了 A 的方案
        assert client.get("/api/llm-profiles").json() == []
        assert client.put(f"/api/llm-profiles/{p['id']}", json={"model": "x"}).status_code == 404
        assert client.delete(f"/api/llm-profiles/{p['id']}").status_code == 404
        assert client.post(f"/api/llm-profiles/{p['id']}/activate").status_code == 404
        assert client.post(f"/api/llm-profiles/{p['id']}/test").status_code == 404


def test_test_endpoint_unreachable():
    with TestClient(app) as client:
        _make_user(client)
        p = _create_profile(client, base_url="http://127.0.0.1:1", api_key=_encrypt_transit("sk-bad"), model="m").json()
        r = client.post(f"/api/llm-profiles/{p['id']}/test")
        assert r.status_code == 200
        assert r.json()["ok"] is False  # 连接失败 → 明确返回失败而非 500


def test_test_endpoint_hits_real_inference():
    """/test 走真实推理：POST /chat/completions（带配置的 model），中转站仅放行 GET /models 时能查出 403。"""
    from app.api.routes import llm_profiles as routes

    captured = {}

    class _Resp:
        def __init__(self, status_code, text, payload=None):
            self.status_code = status_code
            self.text = text
            self._payload = payload

        def json(self):
            if self._payload is None:
                raise ValueError("not json")
            return self._payload

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, **kwargs):
            captured["url"] = url
            captured["json"] = kwargs["json"]
            captured["headers"] = kwargs["headers"]
            return _Resp(403, "Your request was blocked.")

    with TestClient(app) as client:
        _make_user(client)
        p = _create_profile(client, base_url="https://relay.example/v1", api_key=_encrypt_transit("k"), model="m").json()
        with patch.object(routes.httpx, "AsyncClient", _Client):
            r = client.post(f"/api/llm-profiles/{p['id']}/test")
        assert captured["url"] == "https://relay.example/v1/chat/completions"
        assert captured["json"] == {
            "model": "m",
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 5,
        }
        assert captured["headers"]["User-Agent"] == "ynfight/0.2"  # 与实战链路 UA 一致，防 WAF 差异
        assert r.status_code == 200
        assert r.json() == {"ok": False, "detail": "HTTP 403: Your request was blocked."}

    with TestClient(app) as client:
        _make_user(client)
        p = _create_profile(client, base_url="https://relay.example/v1", api_key=_encrypt_transit("k"), model="m").json()

        class _OkClient(_Client):
            async def post(self, url, **kwargs):
                return _Resp(200, "ok", payload={"choices": [{"message": {"role": "assistant", "content": "pong"}}]})

        with patch.object(routes.httpx, "AsyncClient", _OkClient):
            r = client.post(f"/api/llm-profiles/{p['id']}/test")
        assert r.json() == {"ok": True, "detail": "连接成功"}

        # 200 但返回网页 HTML（常见于 base_url 缺 /v1）→ 必须报失败，不能假"连接成功"
        class _HtmlClient(_Client):
            async def post(self, url, **kwargs):
                return _Resp(200, "<!doctype html>...", payload=None)

        with patch.object(routes.httpx, "AsyncClient", _HtmlClient):
            r = client.post(f"/api/llm-profiles/{p['id']}/test")
        assert r.json() == {"ok": False, "detail": "HTTP 200 但返回的不是有效聊天补全（可能 base_url 缺 /v1，命中网页）"}


def test_build_chat_model_override():
    """build_chat_model 用 llm_config 覆盖 api_key/base_url/model；空字段/未配回退 env 默认。"""
    from app.services import llm

    s = llm.get_settings()
    with patch.object(llm, "ChatOpenAI", return_value="client") as mock:
        llm.build_chat_model(llm_config={"api_key": "sk-u", "base_url": "https://x/v1", "model": "m1"})
        kw = mock.call_args.kwargs
        assert kw["api_key"] == "sk-u"
        assert kw["base_url"] == "https://x/v1"
        assert kw["model"] == "m1"
        assert kw["default_headers"] == {"User-Agent": "ynfight/0.2"}  # 中立 UA，防中转站 WAF 拦 SDK 官方 UA

        llm.build_chat_model()
        kw = mock.call_args.kwargs
        assert kw["api_key"] == s.LLM_API_KEY
        assert kw["base_url"] == (s.LLM_BASE_URL or None)
        assert kw["model"] == s.LLM_MODEL

        llm.build_chat_model(llm_config={"api_key": "sk-y", "base_url": "", "model": ""})
        kw = mock.call_args.kwargs
        assert kw["api_key"] == "sk-y"
        assert kw["base_url"] == (s.LLM_BASE_URL or None)
        assert kw["model"] == s.LLM_MODEL


def test_profile_to_llm_config():
    from app.services import profile_crypto
    from app.services.llm import profile_to_llm_config

    assert profile_to_llm_config(None) is None

    class P:
        api_key = ""
        base_url = "https://x"
        model = "m"

    assert profile_to_llm_config(P()) is None  # 空 key → None（回退服务器默认）
    P.api_key = profile_crypto.encrypt_storage("k")  # 落库是密文，使用时解密
    assert profile_to_llm_config(P()) == {"api_key": "k", "base_url": "https://x", "model": "m"}


def test_api_key_encrypted_at_rest():
    """落库 api_key 是 Fernet 密文（不含明文），且能解回原明文（运输→落库→使用全链路）。"""
    from sqlalchemy import select

    from app.db.base import async_session_factory
    from app.models.llm_profile import LlmProfile
    from app.services import profile_crypto

    async def _stored_key(profile_id: int) -> str:
        async with async_session_factory() as session:
            row = await session.scalar(select(LlmProfile.api_key).where(LlmProfile.id == profile_id))
            return row

    with TestClient(app) as client:
        _make_user(client)
        plaintext = "sk-rot13-明文-abc"
        p = _create_profile(client, api_key=_encrypt_transit(plaintext)).json()

        stored = asyncio.run(_stored_key(p["id"]))
        assert plaintext not in stored  # 明文绝不落库
        assert profile_crypto.decrypt_storage(stored) == plaintext  # 可解回原值

    # 明文 api_key 会被拒绝（只接受加密传输）
    with TestClient(app) as client:
        _make_user(client)
        r = _create_profile(client, api_key="sk-plaintext-attempt")
        assert r.status_code == 400
        assert "加密" in r.json()["detail"]


# ---------- 对战链路：发起方激活方案 → run_deduction 的 llm_config ----------

def _arm(client, tok, prefix):
    """新建一位带名奇人（名 = 用户名）+ 造一门异能 + 装进装配 + 解封。"""
    h = {"Authorization": f"Bearer {tok}"}
    name = client.get("/api/auth/me", headers=h).json()["username"]
    r = client.post("/api/abilities", json={"name": f"{prefix}之刃", "effect": "暗影利刃斩杀"}, headers=h)
    assert r.status_code == 201
    ld = client.post("/api/loadouts", json={"name": name}, headers=h).json()
    for a in client.get("/api/abilities/mine", headers=h).json():
        client.post(f"/api/loadouts/{ld['id']}/abilities/{a['id']}", headers=h)
    assert client.put(f"/api/loadouts/{ld['id']}", json={"enabled": True}, headers=h).status_code == 200
    return name


def _wait_done(client, battle_id, headers, timeout=12):
    b = None
    for _ in range(int(timeout / 0.2)):
        b = client.get(f"/api/battles/{battle_id}", headers=headers).json()
        if b["status"] != "pending":
            return b
        time.sleep(0.2)
    return b


def _deduce_result(user_a_id: int, fighter_a: str) -> DeductionResult:
    return DeductionResult(
        god="上帝视角：甲胜。",
        narration_a="A 视角：胜。",
        narration_b="B 视角：败。",
        winner_side="A",
        winner_id=user_a_id,
        result=fighter_a,
    )


def test_battle_uses_challenger_active_profile():
    """发起方配置了激活方案 → run_deduction 收到 profile_to_llm_config(profile) 作为 llm_config。"""
    with TestClient(app) as client:
        tok_a = _make_user(client)
        tok_b = _make_user(client, "w")
        h_a = {"Authorization": f"Bearer {tok_a}"}
        fighter_a = _arm(client, tok_a, "甲")
        _arm(client, tok_b, "乙")
        user_b_id = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok_b}"}).json()["id"]
        user_a_id = client.get("/api/auth/me", headers=h_a).json()["id"]

        p = _create_profile(client, headers=h_a, label="自定义方案", base_url="http://127.0.0.1:9/v1", api_key=_encrypt_transit("sk-e2e"), model="e2e-model").json()
        assert p["is_active"] is True

        with (
            patch("app.services.battle.run_deduction", new=AsyncMock(return_value=_deduce_result(user_a_id, fighter_a))) as rd,
            patch("app.services.battle.pick_opponent", new=AsyncMock(return_value=user_b_id)),
        ):
            r = client.post("/api/battles", headers=h_a)
            assert r.status_code == 200
            b = _wait_done(client, r.json()["id"], h_a)

        assert b["status"] == "done"
        assert rd.await_count >= 1
        assert rd.await_args.kwargs["llm_config"] == {
            "api_key": "sk-e2e",
            "base_url": "http://127.0.0.1:9/v1",
            "model": "e2e-model",
        }


def test_battle_falls_back_when_no_profile():
    """发起方未配置任何方案 → run_deduction 收到 llm_config=None（回退服务器默认）。"""
    with TestClient(app) as client:
        tok_a = _make_user(client)
        tok_b = _make_user(client, "z")
        h_a = {"Authorization": f"Bearer {tok_a}"}
        fighter_a = _arm(client, tok_a, "丙")
        _arm(client, tok_b, "丁")
        user_b_id = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok_b}"}).json()["id"]
        user_a_id = client.get("/api/auth/me", headers=h_a).json()["id"]

        with (
            patch("app.services.battle.run_deduction", new=AsyncMock(return_value=_deduce_result(user_a_id, fighter_a))) as rd,
            patch("app.services.battle.pick_opponent", new=AsyncMock(return_value=user_b_id)),
        ):
            r = client.post("/api/battles", headers=h_a)
            assert r.status_code == 200
            b = _wait_done(client, r.json()["id"], h_a)

        assert b["status"] == "done"
        assert rd.await_args.kwargs["llm_config"] is None
