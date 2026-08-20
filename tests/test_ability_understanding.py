"""奇术因果槽位测试：异步生成结构化 JSON 槽位落库、创建/更新奇术触发后台任务、推演渲染喂槽位。

槽位（时序三相因果守恒律的 JSON 解析）是后续推演对战的主要依据；路由在创建/更新奇术后台调度
生成。conftest 已对 build_understanding_chain 打桩默认空槽位，本文件用局部 override 验证落库与轮询。
"""

import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from cryptography.fernet import InvalidToken
from fastapi.testclient import TestClient

from app.db.base import async_session_factory
from app.main import app
from app.models.ability import Ability
from app.services.ability.understanding import (
    AbilitySlot,
    Phase,
    SlotVerdict,
    ensure_ability_understanding,
)
from app.services.battle.deduction import _render_ability


def _mk(client, prefix="testund") -> str:
    uname = f"{prefix}_" + uuid4().hex[:8]
    client.post("/api/auth/register", json={"username": uname, "password": "secret123"})
    return client.post("/api/auth/login", json={"username": uname, "password": "secret123"}).json()["access_token"]


def _slot(summary="力量来自显相运作机制", mid_text="释放由混乱灵力构成的微观干扰波") -> AbilitySlot:
    """典型显相型槽位桩：无契相无果相，显相机制 + 破局接口。"""
    return AbilitySlot(
        verdict=SlotVerdict(zero_phase=False, source_phases=["mid"], summary=summary),
        pre=Phase(present=False),
        mid=Phase(present=True, text=mid_text),
        post=Phase(present=False),
    )


async def _read_understanding(aid: str) -> str:
    async with async_session_factory() as db:
        ability = await db.get(Ability, aid)
        return ability.understanding


def test_ensure_ability_understanding_writes_slot():
    """ensure 生成结构化 JSON 槽位 → 落库到 understanding；生成链拿到效果与详细解释。"""
    with TestClient(app) as client:
        tok = _mk(client)
        h = {"Authorization": f"Bearer {tok}"}
        aid = client.post(
            "/api/abilities",
            json={"name": "燃烬之握", "effect": "接触的物体被点燃为不会熄灭的火焰", "detail": "需与对方掌心相对接触一息方可点燃"},
            headers=h,
        ).json()["id"]
        chain = MagicMock()
        chain.ainvoke = AsyncMock(return_value=_slot())
        with patch("app.services.ability.understanding.build_understanding_chain", return_value=chain):
            asyncio.run(ensure_ability_understanding(aid))

        parsed = AbilitySlot.model_validate_json(asyncio.run(_read_understanding(aid)))
        assert parsed.verdict.source_phases == ["mid"]
        assert parsed.mid.present and parsed.mid.text == "释放由混乱灵力构成的微观干扰波"
        assert not parsed.pre.present and not parsed.post.present
        # 生成链拿到的是效果与详细解释（user 消息取 .content）
        msgs = chain.ainvoke.await_args.args[0]
        user_text = msgs[1].content
        assert "接触的物体被点燃" in user_text
        assert "掌心相对接触一息" in user_text


def test_ensure_falls_back_to_default_when_profile_key_undecryptable():
    """方案 api_key 解密失败（InvalidToken）→ 回退默认模型生成，不 abort，槽位照常落库。"""
    with TestClient(app) as client:
        tok = _mk(client)
        h = {"Authorization": f"Bearer {tok}"}
        aid = client.post(
            "/api/abilities",
            json={"name": "燃烬之握", "effect": "接触的物体被点燃为不会熄灭的火焰", "detail": "需与对方掌心相对接触一息方可点燃"},
            headers=h,
        ).json()["id"]
        chain = MagicMock()
        chain.ainvoke = AsyncMock(return_value=_slot())
        with patch("app.services.ability.understanding.build_understanding_chain", return_value=chain), patch(
            "app.services.ability.understanding.profile_to_llm_config",
            side_effect=InvalidToken("signature did not match digest"),
        ):
            asyncio.run(ensure_ability_understanding(aid))

        parsed = AbilitySlot.model_validate_json(asyncio.run(_read_understanding(aid)))
        assert parsed.mid.present and parsed.mid.text == "释放由混乱灵力构成的微观干扰波"
        assert chain.ainvoke.await_args.args[0][1].content  # 仍用默认配置调生成链，槽位落库


def test_create_ability_schedules_understanding():
    """创建奇术触发后台生成 → 轮询 understanding 非空（conftest 空槽位桩落库为合法 JSON）。"""
    with TestClient(app) as client:
        tok = _mk(client)
        h = {"Authorization": f"Bearer {tok}"}
        aid = client.post("/api/abilities", json={"name": "燃烬之握", "effect": "点燃接触物"}, headers=h).json()["id"]
        raw = None
        for _ in range(50):  # 后台任务异步落库，轮询最多 5s
            raw = asyncio.run(_read_understanding(aid))
            if raw:
                break
            time.sleep(0.1)
        assert raw
        parsed = AbilitySlot.model_validate_json(raw)
        assert parsed.verdict.zero_phase is False


def test_update_ability_regenerates_understanding():
    """更新奇术触发后台重算 → understanding 被覆盖为新槽位（先等创建时的默认桩落库，避免竞态覆盖）。"""
    with TestClient(app) as client:
        tok = _mk(client)
        h = {"Authorization": f"Bearer {tok}"}
        aid = client.post("/api/abilities", json={"name": "燃烬之握", "effect": "点燃接触物"}, headers=h).json()["id"]
        for _ in range(50):  # 等创建触发的后台任务（默认桩）落库完成，杜绝后写覆盖
            if asyncio.run(_read_understanding(aid)):
                break
            time.sleep(0.1)
        chain = MagicMock()
        chain.ainvoke = AsyncMock(return_value=_slot(summary="更新后的定位"))
        with patch("app.services.ability.understanding.build_understanding_chain", return_value=chain):
            r = client.put(
                f"/api/abilities/{aid}",
                json={"name": "燃烬之握", "effect": "点燃接触物", "detail": "需掌心相对一息"},
                headers=h,
            )
            assert r.status_code == 200
            raw = None
            for _ in range(50):
                raw = asyncio.run(_read_understanding(aid))
                if raw and json.loads(raw)["verdict"]["summary"] == "更新后的定位":
                    break
                time.sleep(0.1)
        assert raw and json.loads(raw)["verdict"]["summary"] == "更新后的定位"


def test_update_ability_unchanged_skips_reasoning():
    """修订全字段无变化：不触发因果推演（understanding 保持原样）；任一字段变化才触发。"""
    with TestClient(app) as client:
        tok = _mk(client)
        h = {"Authorization": f"Bearer {tok}"}
        aid = client.post(
            "/api/abilities",
            json={"name": "燃烬之握", "effect": "点燃接触物", "detail": "需掌心相对一息"},
            headers=h,
        ).json()["id"]
        for _ in range(50):  # 等创建触发的后台任务（默认桩）落库，杜绝竞态
            if asyncio.run(_read_understanding(aid)):
                break
            time.sleep(0.1)
        before = asyncio.run(_read_understanding(aid))
        assert before

        with patch("app.api.routes.abilities._schedule_understanding") as sched:
            # 全字段不变 → 不调度
            r = client.put(
                f"/api/abilities/{aid}",
                json={"name": "燃烬之握", "effect": "点燃接触物", "detail": "需掌心相对一息"},
                headers=h,
            )
            assert r.status_code == 200
            assert sched.call_count == 0
            # 任一字段变化 → 调度一次
            r = client.put(
                f"/api/abilities/{aid}",
                json={"name": "燃烬之握", "effect": "点燃接触物", "detail": "掌心相对方可点燃"},
                headers=h,
            )
            assert r.status_code == 200
            assert sched.call_count == 1
        assert asyncio.run(_read_understanding(aid)) == before  # 调度被桩住，槽位保持原样


def test_render_ability_includes_understanding():
    """_render_ability：有槽位才输出「因果槽位」行；无 detail/槽位时仅名目效果。"""
    a = SimpleNamespace(
        name="燃烬之握", effect="点燃接触物", detail="需掌心相对一息", understanding='{"verdict":{}}', tactic=""
    )
    out = _render_ability(a)
    assert "因果槽位：{\"verdict\":{}}" in out
    assert "详细解释：需掌心相对一息" in out
    plain = SimpleNamespace(name="燃烬之握", effect="点燃接触物", detail="", understanding="", tactic="")
    assert "因果槽位" not in _render_ability(plain)
