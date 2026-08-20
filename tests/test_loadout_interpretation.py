"""奇人风格/战术解读测试：异步生成清洗文本落库、剔除装配清单外奇术引用、推演上下文喂解读（回退原文）。

注册不赠送默认奇人，测例用 POST 新建带名奇人（名字必填）。
"""

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.base import async_session_factory
from app.main import app
from app.models.loadout import Loadout
from app.services.loadouts.interpretation import LoadoutInterpretation, ensure_loadout_interpretation


def _mk(client, prefix="testli") -> str:
    uname = f"{prefix}_" + uuid4().hex[:8]
    client.post("/api/auth/register", json={"username": uname, "password": "secret123"})
    return client.post("/api/auth/login", json={"username": uname, "password": "secret123"}).json()["access_token"]


def _ability(name, effect):
    return SimpleNamespace(name=name, effect=effect, detail="", understanding="", tactic="")


async def _read_interpretation(lid: int) -> tuple[str, str]:
    async with async_session_factory() as db:
        l = await db.get(Loadout, lid)
        return l.style_interpretation, l.tactic_interpretation


def _stub_interpretation(style, tactic):
    """解读链桩：返回固定清洗文本（内部 with 覆盖 conftest 的全量空文本桩）。"""
    chain = MagicMock()
    chain.ainvoke = AsyncMock(return_value=LoadoutInterpretation(style=style, tactic=tactic))
    return chain


def test_interpretation_corrects_and_caches():
    """解读 LLM 输出清洗文本（剔除清单外「火球」引用）→ 落库到解读列；输入含原文本与已装配清单。"""
    with TestClient(app) as client:
        tok = _mk(client)
        h = {"Authorization": f"Bearer {tok}"}
        aid = client.post("/api/abilities", json={"name": "索命咒", "effect": "命中即死"}, headers=h).json()["id"]
        chain = _stub_interpretation("远程压制流", "保持距离，远程消耗")
        with patch("app.services.loadouts.interpretation.build_interpretation_chain", return_value=chain):
            # 整段置于 override 内：POST 建奇人触发的后台解读任务也走同一桩，避免竞态回写空文本
            lid = client.post(
                "/api/loadouts",
                json={"name": "青锋", "style": "火球大师", "tactic": "保持距离，火球消耗"},
                headers=h,
            ).json()["id"]
            client.post(f"/api/loadouts/{lid}/abilities/{aid}", headers=h)
            asyncio.run(ensure_loadout_interpretation(lid))

            style_i, tactic_i = asyncio.run(_read_interpretation(lid))
            assert style_i == "远程压制流"
            assert tactic_i == "保持距离，远程消耗"
            # 解读链拿到的是原风格/战术与已装配清单（format_messages 返回消息列表，user 消息取 .content）
            msgs = chain.ainvoke.await_args.args[0]
            user_text = msgs[1].content
            assert "保持距离，火球消耗" in user_text
            assert "索命咒：命中即死" in user_text


def test_ensure_clears_when_no_style_tactic():
    """风格战术皆空 → 清空解读缓存，不触发 LLM。"""
    with TestClient(app) as client:
        tok = _mk(client)
        h = {"Authorization": f"Bearer {tok}"}
        lid = client.post("/api/loadouts", json={"name": "青锋"}, headers=h).json()["id"]  # 风格战术皆空

        async def _dirty():
            async with async_session_factory() as db:
                l = await db.get(Loadout, lid)
                l.style_interpretation = "脏缓存"
                l.tactic_interpretation = "脏缓存"
                await db.commit()

        asyncio.run(_dirty())
        chain = MagicMock()
        with patch("app.services.loadouts.interpretation.build_interpretation_chain", return_value=chain):
            asyncio.run(ensure_loadout_interpretation(lid))
            assert chain.ainvoke.call_count == 0  # 未调用 LLM
            style_i, tactic_i = asyncio.run(_read_interpretation(lid))
            assert style_i == "" and tactic_i == ""


def test_combat_info_uses_interpretation_fallback():
    """_combat_info：解读非空用解读；解读为空回退原文；风格进上下文（空则（未设定））。"""
    from app.services.battle.deduction import _combat_info

    abs_a = [_ability("索命咒", "命中即死")]
    abs_b = [_ability("镜面反射", "反射攻击")]
    # 解读为空（模拟解读尚未生成）→ 回退原文战术
    info = _combat_info("青锋", "血影", abs_a, abs_b, tactic_a="保持距离，火球消耗", tactic_b="")
    assert "保持距离，火球消耗" in info
    assert "战斗风格：（未设定）" in info  # style 空
    # 解读非空 → 用解读文本，风格进上下文
    info2 = _combat_info(
        "青锋", "血影", abs_a, abs_b,
        tactic_a="保持距离，远程消耗", tactic_b="",
        style_a="远程压制流", style_b="潜行流",
    )
    assert "保持距离，远程消耗" in info2
    assert "保持距离，火球消耗" not in info2
    assert "战斗风格：远程压制流" in info2
    assert "战斗风格：潜行流" in info2


def test_update_loadout_schedules_interpretation():
    """更新战术触发后台解读 → 解读列被写入（轮询后台任务落库）。"""
    with TestClient(app) as client:
        tok = _mk(client)
        h = {"Authorization": f"Bearer {tok}"}
        lid = client.post("/api/loadouts", json={"name": "青锋"}, headers=h).json()["id"]
        chain = _stub_interpretation("远程压制流", "保持距离，远程消耗")
        with patch("app.services.loadouts.interpretation.build_interpretation_chain", return_value=chain):
            r = client.put(f"/api/loadouts/{lid}", json={"tactic": "保持距离，火球消耗"}, headers=h)
            assert r.status_code == 200
            style_i = tactic_i = None
            for _ in range(50):  # 后台任务异步落库，轮询最多 5s
                style_i, tactic_i = asyncio.run(_read_interpretation(lid))
                if tactic_i:
                    break
                time.sleep(0.1)
        assert tactic_i == "保持距离，远程消耗"
        assert style_i == "远程压制流"
