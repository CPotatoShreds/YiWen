"""异能配置测试：默认配置 / 启用切换 / 装配异能 / 对战抽选 / 匹配排除。"""

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
    chain.ainvoke = AsyncMock(return_value={"narration_a": a, "narration_b": b})
    return chain


def _mk(client, prefix="testload") -> str:
    uname = f"{prefix}_" + uuid4().hex[:8]
    client.post("/api/auth/register", json={"username": uname, "password": "secret123"})
    return client.post("/api/auth/login", json={"username": uname, "password": "secret123"}).json()["access_token"]


def _give_ability(client, tok, name, effect) -> str:
    r = client.post("/api/abilities", json={"name": name, "effect": effect}, headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 201
    return r.json()["id"]


def _mk_loadout(client, tok, name) -> dict:
    """新建一位带名奇人（注册不赠送默认奇人，须显式创建）。"""
    h = {"Authorization": f"Bearer {tok}"}
    r = client.post("/api/loadouts", json={"name": name}, headers=h)
    assert r.status_code == 201
    return r.json()


def _arm_all(client, tok):
    """建一位奇人（名 = 用户名）+ 装全部异能 + 解封（参与匹配需已解封且装奇术）。"""
    h = {"Authorization": f"Bearer {tok}"}
    uname = client.get("/api/auth/me", headers=h).json()["username"]
    ld = _mk_loadout(client, tok, uname)
    for a in client.get("/api/abilities/mine", headers=h).json():
        client.post(f"/api/loadouts/{ld['id']}/abilities/{a['id']}", headers=h)
    assert client.put(f"/api/loadouts/{ld['id']}", json={"enabled": True}, headers=h).status_code == 200
    return ld


def _wait_done(client, battle_id, headers, timeout=12):
    b = None
    for _ in range(int(timeout / 0.2)):
        b = client.get(f"/api/battles/{battle_id}", headers=headers).json()
        if b["status"] != "pending":
            return b
        time.sleep(0.2)
    return b


def test_register_starts_with_empty_slots():
    """注册不再赠送默认奇人：0 位奇人，空槽位可新建。"""
    with TestClient(app) as client:
        tok = _mk(client)
        h = {"Authorization": f"Bearer {tok}"}
        assert client.get("/api/loadouts", headers=h).json() == []
        me = client.get("/api/auth/me", headers=h).json()
        assert me["max_loadouts"] == 3  # 初始解锁 3 个空槽位


def test_create_loadout_requires_name():
    """新建奇人名字必填：空名 → 400。"""
    with TestClient(app) as client:
        tok = _mk(client)
        h = {"Authorization": f"Bearer {tok}"}
        assert client.post("/api/loadouts", json={}, headers=h).status_code == 400
        assert client.post("/api/loadouts", json={"name": "  "}, headers=h).status_code == 400


def test_toggle_and_assembly():
    with TestClient(app) as client:
        tok = _mk(client)
        h = {"Authorization": f"Bearer {tok}"}
        first = _mk_loadout(client, tok, "白鹤")
        second = _mk_loadout(client, tok, "青锋")

        aid = _give_ability(client, tok, "燃烬之握", "点燃接触物")
        # 同一异能可入多套配置
        assert client.post(f"/api/loadouts/{first['id']}/abilities/{aid}", headers=h).status_code == 200
        assert client.post(f"/api/loadouts/{second['id']}/abilities/{aid}", headers=h).status_code == 200
        # 重复加入幂等
        assert client.post(f"/api/loadouts/{first['id']}/abilities/{aid}", headers=h).status_code == 200

        # 切换启用开关
        r = client.put(f"/api/loadouts/{first['id']}", json={"enabled": False}, headers=h)
        assert r.status_code == 200
        assert r.json()["enabled"] is False

        # 移出第二套配置
        assert client.delete(f"/api/loadouts/{second['id']}/abilities/{aid}", headers=h).status_code == 200
        out = client.get("/api/loadouts", headers=h).json()
        assert [a["id"] for a in out[1]["abilities"]] == []
        assert [a["id"] for a in out[0]["abilities"]] == [aid]


def test_delete_ability_removes_from_loadouts():
    """删除异能：从异能库移除，并自动从装配位移除，不留悬空引用。"""
    with TestClient(app) as client:
        tok = _mk(client)
        h = {"Authorization": f"Bearer {tok}"}
        a1 = _give_ability(client, tok, "影刃", "以暗影凝聚利刃斩杀")
        _give_ability(client, tok, "霜语", "冻结空气中的水分")
        _arm_all(client, tok)

        assert client.delete(f"/api/abilities/{a1}", headers=h).status_code == 204
        out = client.get("/api/loadouts", headers=h).json()[0]
        assert [a["name"] for a in out["abilities"]] == ["霜语"]  # 已删异能不在装配位


def test_loadout_tactic_roundtrip():
    """奇人打法：PUT 带 tactic 持久化并回读；只切 enabled 不擦除打法。"""
    with TestClient(app) as client:
        tok = _mk(client)
        h = {"Authorization": f"Bearer {tok}"}
        first = _mk_loadout(client, tok, "燃烬")
        r = client.put(f"/api/loadouts/{first['id']}", json={"tactic": "开局隐身绕后，先手突袭"}, headers=h)
        assert r.status_code == 200 and r.json()["tactic"] == "开局隐身绕后，先手突袭"
        # 只切 enabled 不擦除打法（前端开关只发 enabled）
        client.put(f"/api/loadouts/{first['id']}", json={"enabled": False}, headers=h)
        out = client.get("/api/loadouts", headers=h).json()[0]
        assert out["tactic"] == "开局隐身绕后，先手突袭" and out["enabled"] is False


def test_challenge_rejected_when_target_disabled():
    """全关启用 → 不会被约战（不会接到匹配）。"""
    with TestClient(app) as client:
        tok_a = _mk(client)
        tok_b = _mk(client)
        h_a = {"Authorization": f"Bearer {tok_a}"}
        h_b = {"Authorization": f"Bearer {tok_b}"}
        _give_ability(client, tok_a, "影刃", "以暗影凝聚利刃斩杀")
        _give_ability(client, tok_b, "血咒", "以自身鲜血为引发动诅咒")
        _arm_all(client, tok_a)
        _arm_all(client, tok_b)

        # B 关闭全部启用
        for l in client.get("/api/loadouts", headers=h_b).json():
            assert client.put(f"/api/loadouts/{l['id']}", json={"enabled": False}, headers=h_b).status_code == 200
        id_b = client.get("/api/auth/me", headers=h_b).json()["id"]

        # A 约战 B → 400
        r = client.post(f"/api/battles/challenge/{id_b}", headers=h_a)
        assert r.status_code == 400


def test_battle_requires_enabled_loadout():
    """无启用配置 → 无法发起对战。"""
    with TestClient(app) as client:
        tok = _mk(client)
        h = {"Authorization": f"Bearer {tok}"}
        _give_ability(client, tok, "影刃", "以暗影凝聚利刃斩杀")
        _arm_all(client, tok)
        # 关闭全部启用
        for l in client.get("/api/loadouts", headers=h).json():
            assert client.put(f"/api/loadouts/{l['id']}", json={"enabled": False}, headers=h).status_code == 200
        assert client.post("/api/battles", headers=h).status_code == 400


def test_battle_uses_only_chosen_loadout():
    """对战只用所选装配位的异能（未装配的异能不出战）。"""
    with TestClient(app) as client:
        tok_a = _mk(client)
        tok_b = _mk(client)
        h_a = {"Authorization": f"Bearer {tok_a}"}
        h_b = {"Authorization": f"Bearer {tok_b}"}
        # A 有 2 个异能，只装配 1 个进启用配置
        a1 = _give_ability(client, tok_a, "雷暴召来", "召唤雷霆轰击对手")
        _give_ability(client, tok_a, "隐形", "凭空消失")
        ld_a = _mk_loadout(client, tok_a, "雷霆使")
        client.post(f"/api/loadouts/{ld_a['id']}/abilities/{a1}", headers=h_a)
        client.put(f"/api/loadouts/{ld_a['id']}", json={"enabled": True}, headers=h_a)

        _give_ability(client, tok_b, "镜面反射", "将对手的攻击原样反射回去")
        _arm_all(client, tok_b)
        name_a = client.get("/api/auth/me", headers=h_a).json()["username"]
        user_b_id = client.get("/api/auth/me", headers=h_b).json()["id"]

        with (
            patch("app.services.battle._build_deduce_llm", return_value=_deduce(f"上帝视角：甲先手，雷暴落下。胜者：{name_a}")),
            patch("app.services.battle._build_transcribe_chain", return_value=_transcribe("甲视角……", "乙视角……")),
            patch("app.services.battle.pick_opponent", new=AsyncMock(return_value=user_b_id)),
        ):
            r = client.post("/api/battles", headers=h_a)
            b = _wait_done(client, r.json()["id"], h_a)

        assert b["status"] == "done"
        # A 侧只有装进启用配置的异能，「隐形」未装配不出战
        assert [x["name"] for x in b["story"]["abilities_a"]] == ["雷暴召来"]


def test_delete_loadout():
    """删除奇人：装配清理、列表移除、归属校验。"""
    with TestClient(app) as client:
        tok = _mk(client)
        h = {"Authorization": f"Bearer {tok}"}
        aid = _give_ability(client, tok, "雷暴召来", "召唤雷霆轰击对手")
        first = _mk_loadout(client, tok, "白鹤")
        _mk_loadout(client, tok, "青锋")
        _mk_loadout(client, tok, "血影")
        client.post(f"/api/loadouts/{first['id']}/abilities/{aid}", headers=h)

        assert client.delete(f"/api/loadouts/{first['id']}", headers=h).status_code == 204
        out = client.get("/api/loadouts", headers=h).json()
        assert len(out) == 2  # 已删
        # 奇术本体还在（只卸下装配），其他奇人不受影响
        assert [x["id"] for x in client.get("/api/abilities/mine", headers=h).json()] == [aid]
        assert all(l["abilities"] == [] for l in out)

        # 未拥有/不存在 → 404；他人奇人不可删
        assert client.delete("/api/loadouts/999999", headers=h).status_code == 404
        tok_b = _mk(client)
        h_b = {"Authorization": f"Bearer {tok_b}"}
        assert client.delete(f"/api/loadouts/{first['id']}", headers=h_b).status_code == 404


def test_create_loadout_with_ability_ids():
    """创建奇人一步装配：ability_ids 去重/归属校验；回读装配一致；他人奇术 → 404。"""
    with TestClient(app) as client:
        tok = _mk(client)
        h = {"Authorization": f"Bearer {tok}"}
        a1 = _give_ability(client, tok, "燃烬之握", "点燃接触物")
        a2 = _give_ability(client, tok, "霜语", "冻结空气中的水分")
        r = client.post(
            "/api/loadouts",
            json={"name": "白鹤", "style": "轻功卓绝", "ability_ids": [a1, a2, a1, a2]},
            headers=h,
        )
        assert r.status_code == 201
        out = r.json()
        assert out["style"] == "轻功卓绝"
        # 同事务插入 added_at 相同，装配顺序不定 → 只比较集合
        assert {a["id"] for a in out["abilities"]} == {a1, a2}  # 去重后恰好两门
        assert {a["id"] for a in client.get("/api/loadouts", headers=h).json()[0]["abilities"]} == {a1, a2}
        # 未拥有的奇术 → 404
        tok_b = _mk(client)
        a4 = _give_ability(client, tok_b, "血咒", "以自身鲜血为引发动诅咒")
        assert client.post("/api/loadouts", json={"name": "青锋", "ability_ids": [a4]}, headers=h).status_code == 404


def test_create_loadout_ability_ids_cap_four():
    """ability_ids 去重后超过 4 个 → 400。"""
    with TestClient(app) as client:
        tok = _mk(client)
        h = {"Authorization": f"Bearer {tok}"}
        ids = [_give_ability(client, tok, f"奇术{i}", f"效果{i}") for i in range(5)]
        assert client.post("/api/loadouts", json={"name": "青锋", "ability_ids": ids}, headers=h).status_code == 400


def test_delete_loadout_unlinks_battle_snapshot():
    """删除参与过对决的奇人：对决快照引用摘除，行迹仍可读。"""
    with TestClient(app) as client:
        tok_a = _mk(client)
        tok_b = _mk(client)
        h_a = {"Authorization": f"Bearer {tok_a}"}
        h_b = {"Authorization": f"Bearer {tok_b}"}
        aid = _give_ability(client, tok_a, "雷暴召来", "召唤雷霆轰击对手")
        uname_a = client.get("/api/auth/me", headers=h_a).json()["username"]
        ld_a = _mk_loadout(client, tok_a, uname_a)
        client.post(f"/api/loadouts/{ld_a['id']}/abilities/{aid}", headers=h_a)
        client.put(f"/api/loadouts/{ld_a['id']}", json={"enabled": True}, headers=h_a)
        _give_ability(client, tok_b, "镜面反射", "将对手的攻击原样反射回去")
        _arm_all(client, tok_b)
        name_a = client.get("/api/auth/me", headers=h_a).json()["username"]
        user_b_id = client.get("/api/auth/me", headers=h_b).json()["id"]

        with (
            patch("app.services.battle._build_deduce_llm", return_value=_deduce(f"上帝视角：甲先手，雷暴落下。胜者：{name_a}")),
            patch("app.services.battle._build_transcribe_chain", return_value=_transcribe("甲视角……", "乙视角……")),
            patch("app.services.battle.pick_opponent", new=AsyncMock(return_value=user_b_id)),
        ):
            r = client.post("/api/battles", headers=h_a)
            b = _wait_done(client, r.json()["id"], h_a)
        assert b["status"] == "done"

        # 删除 A 出战的奇人 → 行迹仍可读（快照名回退异闻师名）
        assert client.delete(f"/api/loadouts/{ld_a['id']}", headers=h_a).status_code == 204
        b2 = client.get(f"/api/battles/{b['id']}", headers=h_a).json()
        assert b2["status"] == "done"
