"""七项新功能测试：奇人榜（上榜/点将挑战）、启程不匹配、行迹再战、和局双方猜词结算。

对局/猜词打桩方式与 test_battles.py 一致：conftest 全局打桩 usage/validate/discuss/理解，
推演（_build_deduce_llm）与转写（_build_transcribe_chain）、猜词点评/检定（_build_commentary/verify_llm）
在此按测试作用域打桩。
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.services.nodes.guess_matcher import CommentaryItem, CommentaryRound, Verification

GOD = "上帝视角：甲以影刃潜行逼近，先手斩落乙。"
NAR_A = "A 视角叙述：甲循着阴影逼近，一刀斩落乙。"
NAR_B = "B 视角叙述：乙措手不及，被一击击倒。"


def _deduce(text):
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=text)
    return llm


def _transcribe(nar_a: str, nar_b: str):
    chain = MagicMock()

    async def _ainvoke(kwargs):
        return {"narration_a": nar_a, "narration_b": nar_b}

    chain.ainvoke = AsyncMock(side_effect=_ainvoke)
    return chain


def _guess_pipeline(verify_fn=None):
    commentary_chain = MagicMock()

    async def _commentary_ainvoke(kwargs):
        return CommentaryRound(items=[CommentaryItem(text="收到你的猜测。", verdict="是", reason="")])

    commentary_chain.ainvoke = AsyncMock(side_effect=_commentary_ainvoke)
    verify_chain = MagicMock()

    async def _verify_ainvoke(kwargs):
        text = "\n".join(m.content for m in kwargs)
        if verify_fn:
            return verify_fn(text)
        return Verification(cracked=False, missing="")

    verify_chain.ainvoke = AsyncMock(side_effect=_verify_ainvoke)
    return commentary_chain, verify_chain


def _mk_user(client, prefix="testfeat") -> str:
    uname = f"{prefix}_" + uuid4().hex[:8]
    client.post("/api/auth/register", json={"username": uname, "password": "secret123"})
    return client.post("/api/auth/login", json={"username": uname, "password": "secret123"}).json()["access_token"]


def _give_ability(client, headers, name, effect):
    r = client.post("/api/abilities", json={"name": name, "effect": effect}, headers=headers)
    assert r.status_code == 201


def _arm(client, headers):
    """立起一位出战奇人（名 = 异闻师用户名）+ 装全部异能 + 解封。"""
    uname = client.get("/api/auth/me", headers=headers).json()["username"]
    ld = client.post("/api/loadouts", json={"name": uname}, headers=headers).json()
    for a in client.get("/api/abilities/mine", headers=headers).json():
        client.post(f"/api/loadouts/{ld['id']}/abilities/{a['id']}", headers=headers)
    assert client.put(f"/api/loadouts/{ld['id']}", json={"enabled": True}, headers=headers).status_code == 200
    return ld


def _wait_done(client, battle_id, headers, timeout=12):
    b = None
    for _ in range(int(timeout / 0.2)):
        b = client.get(f"/api/battles/{battle_id}", headers=headers).json()
        if b["status"] != "pending":
            return b
        time.sleep(0.2)
    return b


def _wait_guess(client, battle_id, headers, attempts_before, timeout=12):
    b = None
    for _ in range(int(timeout / 0.2)):
        b = client.get(f"/api/battles/{battle_id}", headers=headers).json()
        if b["guess_attempts_used"] > attempts_before:
            return b
        time.sleep(0.2)
    return b


def _post_guess(client, url, headers, text=None):
    """POST 猜词接口（点评/检定），撞上 409「仍在判定中」时重试数次。

    点评/检定皆为后台任务，落库先于判定锁（_guess_inflight）释放：连续快速提交可能撞上 409。
    """
    g = None
    for _ in range(20):
        kw = {"headers": headers}
        if text is not None:
            kw["json"] = {"text": text}
        g = client.post(url, **kw)
        if g.status_code != 409:
            return g
        time.sleep(0.2)
    return g


def _mk_draw_battle(client, h_a, h_b):
    """建一局和局对战（A×B 各 1 门奇术），返回 (battle_dict, name_a, name_b)。"""
    name_a = client.get("/api/auth/me", headers=h_a).json()["username"]
    name_b = client.get("/api/auth/me", headers=h_b).json()["username"]
    user_b_id = client.get("/api/auth/me", headers=h_b).json()["id"]
    with (
        patch("app.services.battle._build_deduce_llm", return_value=_deduce("双方僵持周旋，谁也没有彻底失去作战能力。平局")),
        patch("app.services.battle._build_transcribe_chain", return_value=_transcribe(NAR_A, NAR_B)),
        patch("app.services.battle.pick_opponent", new=AsyncMock(return_value=user_b_id)),
    ):
        r = client.post("/api/battles", headers=h_a)
        b = _wait_done(client, r.json()["id"], h_a)
    return b, name_a, name_b


def _mk_two_users(client, prefix):
    tok_a = _mk_user(client, prefix)
    tok_b = _mk_user(client, prefix)
    h_a = {"Authorization": f"Bearer {tok_a}"}
    h_b = {"Authorization": f"Bearer {tok_b}"}
    return h_a, h_b


# ---------------------------------------------------------------------------
# 奇人榜
# ---------------------------------------------------------------------------


def test_board_put_on_list_challenge_take_off():
    """上榜冻结刻印 → 榜单展示（奇术保密只露门数）→ 他人点将切磋（不计名望）→ 非榜主不能下榜。"""
    with TestClient(app) as client:
        h_a, h_b = _mk_two_users(client, "testbrd")
        name_a = client.get("/api/auth/me", headers=h_a).json()["username"]
        name_b = client.get("/api/auth/me", headers=h_b).json()["username"]
        _give_ability(client, h_a, "影刃", "以暗影凝聚利刃斩杀敌人")
        _give_ability(client, h_b, "血咒", "以自身鲜血为引发动诅咒")
        ld_a = _arm(client, h_a)
        ld_b = _arm(client, h_b)

        # A 上榜
        r = client.post("/api/board", json={"loadout_id": ld_a["id"]}, headers=h_a)
        assert r.status_code == 201
        eid = r.json()["id"]
        assert r.json()["mine"] is True
        assert r.json()["name"] == name_a and r.json()["ability_count"] == 1

        # 榜单：B 看到他人条目（mine=False），A 看到自己的
        entry = next(e for e in client.get("/api/board", headers=h_b).json() if e["id"] == eid)
        assert entry["mine"] is False and entry["user"] == name_a
        assert next(e for e in client.get("/api/board", headers=h_a).json() if e["id"] == eid)["mine"] is True

        # 不能挑战自己榜上奇人
        assert (
            client.post(f"/api/board/{eid}/challenge", json={"loadout_id": ld_a["id"]}, headers=h_a).status_code == 400
        )

        # B 点将挑战 A 的刻印 → 切磋局（friendly、不计名望）
        with (
            patch("app.services.battle._build_deduce_llm", return_value=_deduce(f"{GOD} 胜者：{name_b}")),
            patch("app.services.battle._build_transcribe_chain", return_value=_transcribe(NAR_A, NAR_B)),
        ):
            rc = client.post(f"/api/board/{eid}/challenge", json={"loadout_id": ld_b["id"]}, headers=h_b)
            assert rc.status_code == 200
            b = _wait_done(client, rc.json()["battle_id"], h_b)
        assert b["friendly"] is True
        assert b["winner"] == name_b
        assert b["rank_delta_a"] == 0 and b["rank_delta_b"] == 0

        # 非榜主下榜 403；榜主下榜 204
        assert client.delete(f"/api/board/{eid}", headers=h_b).status_code == 403
        assert client.delete(f"/api/board/{eid}", headers=h_a).status_code == 204
        assert all(e["id"] != eid for e in client.get("/api/board", headers=h_a).json())


# ---------------------------------------------------------------------------
# 启程不匹配
# ---------------------------------------------------------------------------


def test_no_repeat_matchmaking_avoids_repeat_pair():
    """no_repeat 启程：历史同场过的「我方奇人 × 对家奇人」具体配对不再匹配。

    匹配池含全库已解封奇人（其他用例也会建号），故断言「不再匹配到 B」而非精确到某人；
    若 no_repeat 空池兜底普通随机，pick_opponent 抛错显式失败。
    """
    with TestClient(app) as client:
        h_a, h_b = _mk_two_users(client, "testnr")
        name_a = client.get("/api/auth/me", headers=h_a).json()["username"]
        name_b = client.get("/api/auth/me", headers=h_b).json()["username"]
        _give_ability(client, h_a, "影刃", "以暗影凝聚利刃斩杀敌人")
        _give_ability(client, h_b, "血咒", "以自身鲜血为引发动诅咒")
        _arm(client, h_a)
        _arm(client, h_b)
        user_b_id = client.get("/api/auth/me", headers=h_b).json()["id"]

        # 第一场：A×B（具体配对 LA1×LB1）
        with (
            patch("app.services.battle._build_deduce_llm", return_value=_deduce(f"{GOD} 胜者：{name_a}")),
            patch("app.services.battle._build_transcribe_chain", return_value=_transcribe(NAR_A, NAR_B)),
            patch("app.services.battle.pick_opponent", new=AsyncMock(return_value=user_b_id)),
        ):
            r = client.post("/api/battles", headers=h_a)
            first = _wait_done(client, r.json()["id"], h_a)
        assert first["user_b"] == name_b

        # 第二场 no_repeat：LB1 已被 LA1 打过 → 不再匹配到 B
        def _fail(*_a, **_k):
            raise AssertionError("no_repeat 不应兜底普通随机")

        with (
            patch("app.services.battle._build_deduce_llm", return_value=_deduce(f"{GOD} 胜者：{name_a}")),
            patch("app.services.battle._build_transcribe_chain", return_value=_transcribe(NAR_A, NAR_B)),
            patch("app.services.battle.pick_opponent", new=AsyncMock(side_effect=_fail)),
        ):
            r2 = client.post("/api/battles", json={"no_repeat": True}, headers=h_a)
            assert r2.status_code == 200
            second = _wait_done(client, r2.json()["id"], h_a)
        assert second["user_b"] != name_b  # 不重复同配对（LA1 不再对 LB1）


# ---------------------------------------------------------------------------
# 行迹再战
# ---------------------------------------------------------------------------


def test_rematch_copies_snapshot_and_guess_state():
    """再战复刻原局：快照带入（奇术一致）、猜词进度带入（可续猜）、一律切磋不计名望。"""
    with TestClient(app) as client:
        h_a, h_b = _mk_two_users(client, "testrm")
        name_a = client.get("/api/auth/me", headers=h_a).json()["username"]
        name_b = client.get("/api/auth/me", headers=h_b).json()["username"]
        _give_ability(client, h_a, "影刃", "以暗影凝聚利刃斩杀敌人")
        _give_ability(client, h_b, "血咒", "以自身鲜血为引发动诅咒")
        _arm(client, h_a)
        _arm(client, h_b)
        user_b_id = client.get("/api/auth/me", headers=h_b).json()["id"]

        with (
            patch("app.services.battle._build_deduce_llm", return_value=_deduce(f"{GOD} 胜者：{name_a}")),
            patch("app.services.battle._build_transcribe_chain", return_value=_transcribe(NAR_A, NAR_B)),
            patch("app.services.battle.pick_opponent", new=AsyncMock(return_value=user_b_id)),
        ):
            r = client.post("/api/battles", headers=h_a)
            orig = _wait_done(client, r.json()["id"], h_b)
        assert orig["winner"] == name_a and orig["can_guess"] is True

        # B 猜一次（仅点评，未看破，不设次数上限）→ 进度留待再战带入
        commentary, verify = _guess_pipeline()
        with (
            patch("app.services.battle._build_commentary_llm", return_value=commentary),
            patch("app.services.battle._build_verify_llm", return_value=verify),
        ):
            g = _post_guess(client, f"/api/battles/{orig['id']}/guess", h_b, text="控制重力")
            assert g.status_code == 202
            og = _wait_guess(client, orig["id"], h_b, attempts_before=0)
        assert og["my_guess"]["attempts_used"] == 1
        assert og["my_guess"]["comments"] == [
            [{"index": 1, "items": [{"text": "收到你的猜测。", "verdict": "是"}]}]
        ]

        # A 发起再战
        with (
            patch("app.services.battle._build_deduce_llm", return_value=_deduce(f"{GOD} 胜者：{name_a}")),
            patch("app.services.battle._build_transcribe_chain", return_value=_transcribe(NAR_A, NAR_B)),
        ):
            rm = client.post(f"/api/battles/{orig['id']}/rematch", headers=h_a)
            assert rm.status_code == 200
            new_id = rm.json()["id"]
            nb = _wait_done(client, new_id, h_a)
        assert nb["friendly"] is True
        assert nb["rank_delta_a"] == 0 and nb["rank_delta_b"] == 0
        assert nb["user_a"] == name_a and nb["user_b"] == name_b

        # B 视角：快照奇术一致 + 猜词进度带入（次数/历史/点评保留、可续猜）
        nb_b = client.get(f"/api/battles/{new_id}", headers=h_b).json()
        assert nb_b["story"]["abilities_b"] == orig["story"]["abilities_b"]
        assert nb_b["my_guess"]["attempts_used"] == 1
        assert nb_b["my_guess"]["history"] == ["控制重力"]
        assert nb_b["my_guess"]["comments"] == [
            [{"index": 1, "items": [{"text": "收到你的猜测。", "verdict": "是"}]}]
        ]
        assert nb_b["can_guess"] is True  # 未收手、未耗尽 → 新局可续猜


# ---------------------------------------------------------------------------
# 和局双方猜词结算
# ---------------------------------------------------------------------------


def test_draw_guess_one_crack_wins_and_rank_recalc():
    """和局一方全破 + 另一方收手 → 全破方翻胜，名望重算（回滚 0.5/0.5 后按 1/0 结算）。"""
    with TestClient(app) as client:
        h_a, h_b = _mk_two_users(client, "testdw")
        name_a = client.get("/api/auth/me", headers=h_a).json()["username"]
        _give_ability(client, h_a, "影刃", "以暗影凝聚利刃斩杀敌人")
        _give_ability(client, h_b, "血咒", "以自身鲜血为引发动诅咒，反噬攻击者")
        _arm(client, h_a)
        _arm(client, h_b)
        b, name_a, _ = _mk_draw_battle(client, h_a, h_b)

        assert b["guess_by"] is None
        assert b["can_guess"] is True  # 和局双方皆可猜
        assert b["my_guess"]["total"] == 1

        # A 点评 + 检定一次全破 B 的血咒 → 本行翻转；B 未收手前不结算
        commentary, verify = _guess_pipeline(
            lambda text: Verification(cracked=True, missing="") if "血咒" in text else Verification(cracked=False, missing="")
        )
        with (
            patch("app.services.battle._build_commentary_llm", return_value=commentary),
            patch("app.services.battle._build_verify_llm", return_value=verify),
        ):
            g = _post_guess(client, f"/api/battles/{b['id']}/guess", h_a, text="以血引咒反噬")
            assert g.status_code == 202
            _wait_guess(client, b["id"], h_a, attempts_before=0)
            gv = _post_guess(client, f"/api/battles/{b['id']}/guess/verify", h_a)
            assert gv.status_code == 202
            ga = _wait_guess(client, b["id"], h_a, attempts_before=1)
        assert ga["my_guess"]["flipped"] is True and ga["my_guess"]["done"] is True
        assert ga["winner"] is None  # 对方未收手，尚在和局

        # B 收手 → 结算：恰一方全破 → A 胜 + 名望重算
        rj = client.post(f"/api/battles/{b['id']}/give-up", headers=h_b).json()
        assert rj["winner"] == name_a
        assert rj["guess_hit"] is True
        assert rj["rank_delta_a"] == 16 and rj["rank_delta_b"] == -16
        me_a = client.get("/api/auth/me", headers=h_a).json()
        me_b = client.get("/api/auth/me", headers=h_b).json()
        assert me_a["rank_points"] == 1016 and me_b["rank_points"] == 984


def test_draw_guess_both_crack_keeps_draw():
    """和局双方都全破 → 保持和局，名望不变。"""
    with TestClient(app) as client:
        h_a, h_b = _mk_two_users(client, "testdd")
        _give_ability(client, h_a, "影刃", "以暗影凝聚利刃斩杀敌人")
        _give_ability(client, h_b, "血咒", "以自身鲜血为引发动诅咒，反噬攻击者")
        _arm(client, h_a)
        _arm(client, h_b)
        b, _, _ = _mk_draw_battle(client, h_a, h_b)

        # A 点评 + 检定全破 B 的血咒
        commentary_a, verify_a = _guess_pipeline(
            lambda text: Verification(cracked=True, missing="") if "血咒" in text else Verification(cracked=False, missing="")
        )
        with (
            patch("app.services.battle._build_commentary_llm", return_value=commentary_a),
            patch("app.services.battle._build_verify_llm", return_value=verify_a),
        ):
            assert _post_guess(client, f"/api/battles/{b['id']}/guess", h_a, text="血咒").status_code == 202
            _wait_guess(client, b["id"], h_a, attempts_before=0)
            assert _post_guess(client, f"/api/battles/{b['id']}/guess/verify", h_a).status_code == 202
            _wait_guess(client, b["id"], h_a, attempts_before=1)

        # B 点评 + 检定全破 A 的影刃
        commentary_b, verify_b = _guess_pipeline(
            lambda text: Verification(cracked=True, missing="") if "影刃" in text else Verification(cracked=False, missing="")
        )
        with (
            patch("app.services.battle._build_commentary_llm", return_value=commentary_b),
            patch("app.services.battle._build_verify_llm", return_value=verify_b),
        ):
            assert _post_guess(client, f"/api/battles/{b['id']}/guess", h_b, text="影刃").status_code == 202
            _wait_guess(client, b["id"], h_b, attempts_before=0)
            assert _post_guess(client, f"/api/battles/{b['id']}/guess/verify", h_b).status_code == 202
            _wait_guess(client, b["id"], h_b, attempts_before=1)

        final = client.get(f"/api/battles/{b['id']}", headers=h_a).json()
        assert final["winner"] is None
        assert final["guess_hit"] is False
        assert final["rank_delta_a"] == 0 and final["rank_delta_b"] == 0
        assert final["my_guess"]["flipped"] is True and final["opp_guess"]["flipped"] is True


def test_draw_guess_both_give_up_keeps_draw():
    """和局双方都收手未全破 → 保持和局，名望不变。"""
    with TestClient(app) as client:
        h_a, h_b = _mk_two_users(client, "testdg")
        _give_ability(client, h_a, "影刃", "以暗影凝聚利刃斩杀敌人")
        _give_ability(client, h_b, "血咒", "以自身鲜血为引发动诅咒，反噬攻击者")
        _arm(client, h_a)
        _arm(client, h_b)
        b, _, _ = _mk_draw_battle(client, h_a, h_b)

        rj1 = client.post(f"/api/battles/{b['id']}/give-up", headers=h_a).json()
        assert rj1["winner"] is None  # 对方未收手，尚在和局
        rj2 = client.post(f"/api/battles/{b['id']}/give-up", headers=h_b).json()
        assert rj2["winner"] is None
        assert rj2["guess_hit"] is False
        assert rj2["rank_delta_a"] == 0 and rj2["rank_delta_b"] == 0
        assert rj2["my_guess"]["done"] is True and rj2["my_guess"]["flipped"] is False
