"""奇人榜点将局「挑战者记忆」测试：挑战者对同一刻印的看破进度跨场累积。

点将局非对称：挑战者(user_a)主动、刻印(entry 冻结快照)被动。挑战者每场都可猜刻印
实际用术（无论本场胜负）；进度按 (挑战者 × 刻印) 用户级跨场累积；全部看破 → 后续点将
不再启动猜词、解锁完整三视角。榜主被动：+5 见闻但行迹隐藏、不能查看单场，只看到聚合的
被挑战次数。

打桩方式与 test_seven_features.py 一致：conftest 全局打桩 usage/validate/discuss/理解，
推演（_build_deduce_llm）与转写（_build_transcribe_chain）、猜词配对/检定
（_build_pair/verify_llm）在此按测试作用域打桩。直连库用 psycopg（同 test_admin.py）。
"""

import os
import time
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient

from app.main import app
from app.services.nodes.guess_matcher import PairMatch, Verification

GOD = "上帝视角：甲以影刃潜行逼近，先手斩落乙。"
NAR_A = "A 视角叙述：甲循着阴影逼近，一刀斩落乙。"
NAR_B = "B 视角叙述：乙措手不及，被一击击倒。"

DRAW = "双方僵持周旋，谁也没有彻底失去作战能力。平局"


def _sqlite() -> psycopg.Connection:
    """直连 pytest 临时测试库（PG），同 test_admin.py。"""
    return psycopg.connect(os.environ["DATABASE_URL"].replace("+asyncpg", ""))


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


def _guess_pipeline(pair_fn, verify_guessed):
    pair_chain = MagicMock()

    async def _pair_ainvoke(kwargs):
        text = "\n".join(m.content for m in kwargs)
        return pair_fn(text)

    pair_chain.ainvoke = AsyncMock(side_effect=_pair_ainvoke)
    verify_chain = MagicMock()
    verify_chain.ainvoke = AsyncMock(return_value=Verification(guessed=verify_guessed, reason="检定"))
    return pair_chain, verify_chain


def _pair_only(fragment: str, snippet: str):
    """配对打桩：仅当奇术原文含 fragment 时才贴片段（其余卡不命中 → 不触发检定）。"""

    def _pair(text: str):
        return PairMatch(snippet=snippet) if fragment in text else PairMatch(snippet="")

    return _pair


def _mk_user(client, prefix="testprog") -> str:
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


def _mk_two_users(client, prefix):
    tok_a = _mk_user(client, prefix)
    tok_b = _mk_user(client, prefix)
    return (
        {"Authorization": f"Bearer {tok_a}"},
        {"Authorization": f"Bearer {tok_b}"},
    )


def _board_entry(client, h_poster, loadout_id):
    r = client.post("/api/board", json={"loadout_id": loadout_id}, headers=h_poster)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _challenge(client, entry_id, h_challenger, loadout_id, god_text, usage_indices=None):
    """点将挑战（打桩推演/转写/可选 usage 子集），等待落定后返回行迹 dict。"""
    patches = [
        patch("app.services.battle._build_deduce_llm", return_value=_deduce(god_text)),
        patch("app.services.battle._build_transcribe_chain", return_value=_transcribe(NAR_A, NAR_B)),
    ]
    if usage_indices is not None:
        from app.services.nodes.usage_judge import UsedAbilities

        usage_chain = MagicMock()
        usage_chain.ainvoke = AsyncMock(return_value=UsedAbilities(indices=usage_indices))
        patches.append(patch("app.services.battle._build_usage_llm", return_value=usage_chain))
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        rc = client.post(f"/api/board/{entry_id}/challenge", json={"loadout_id": loadout_id}, headers=h_challenger)
        assert rc.status_code == 200, rc.text
        return _wait_done(client, rc.json()["battle_id"], h_challenger)


def _guess(client, battle, headers, text, pair_fn, verify_guessed):
    """对一场点将局提交猜测（打桩配对/检定），等待落库后返回行迹 dict。"""
    pair, verify = _guess_pipeline(pair_fn, verify_guessed)
    with (
        patch("app.services.battle._build_pair_llm", return_value=pair),
        patch("app.services.battle._build_verify_llm", return_value=verify),
    ):
        g = client.post(f"/api/battles/{battle['id']}/guess", json={"text": text}, headers=headers)
        assert g.status_code == 202, g.text
        return _wait_guess(client, battle["id"], headers, attempts_before=battle.get("guess_attempts_used", 0))


# ---------------------------------------------------------------------------
# 猜词者恒为挑战者（三态）
# ---------------------------------------------------------------------------


def test_board_challenger_is_always_the_guesser():
    """点将局猜词者恒为挑战者（无论本场胜负/和局），只猜刻印侧，替代「败方猜胜者」。"""
    with TestClient(app) as client:
        h_a, h_b = _mk_two_users(client, "tbga")
        name_a = client.get("/api/auth/me", headers=h_a).json()["username"]
        name_b = client.get("/api/auth/me", headers=h_b).json()["username"]
        _give_ability(client, h_a, "影刃", "以暗影凝聚利刃斩杀敌人")
        _give_ability(client, h_b, "天雷", "引九天之雷轰击敌人")
        ld_a = _arm(client, h_a)
        ld_b = _arm(client, h_b)
        eid = _board_entry(client, h_a, ld_a["id"])

        # 挑战者胜：标准流程「败方（榜主）猜」，点将局改为挑战者猜
        b = _challenge(client, eid, h_b, ld_b["id"], f"{GOD} 胜者：{name_b}")
        assert b["board_entry_id"] == eid
        assert b["winner"] == name_b
        assert b["guess_by"] == name_b  # 恒挑战者
        assert b["can_guess"] is True
        assert b["guess_total"] == 1  # 刻印实际用术（1 门）

        # 榜主胜：挑战者仍可猜
        b = _challenge(client, eid, h_b, ld_b["id"], f"{GOD} 胜者：{name_a}")
        assert b["winner"] == name_a
        assert b["guess_by"] == name_b

        # 和局：标准流程双方皆可猜（guess_by None），点将局仍为挑战者
        b = _challenge(client, eid, h_b, ld_b["id"], DRAW)
        assert b["winner"] is None
        assert b["guess_by"] == name_b


# ---------------------------------------------------------------------------
# 跨场累积
# ---------------------------------------------------------------------------


def test_board_progress_prefills_next_battle():
    """跨场累积：场 1 看破一卡 → 场 2 猜词行预填该卡已看破，history/次数带入，未看破卡仍保密。"""
    with TestClient(app) as client:
        h_a, h_b = _mk_two_users(client, "tbpf")
        name_b = client.get("/api/auth/me", headers=h_b).json()["username"]
        _give_ability(client, h_a, "影刃", "以暗影凝聚利刃斩杀敌人")
        _give_ability(client, h_a, "血咒", "以自身鲜血为引发动诅咒")
        _give_ability(client, h_b, "天雷", "引九天之雷轰击敌人")
        ld_a = _arm(client, h_a)
        ld_b = _arm(client, h_b)
        eid = _board_entry(client, h_a, ld_a["id"])

        b1 = _challenge(client, eid, h_b, ld_b["id"], f"{GOD} 胜者：{name_b}")
        assert b1["guess_total"] == 2
        assert b1["my_guess"]["cards"][0]["cracked"] is False

        # 只看破影刃（卡 0）：血咒未破 → 进度未全破，不揭示
        g1 = _guess(client, b1, h_b, "影刃化形，遁入暗影", _pair_only("以暗影凝聚", "影刃以暗影凝刃"), True)
        assert g1["my_guess"]["cards"][0]["cracked"] is True
        assert g1["my_guess"]["cards"][0]["name"] == "影刃"
        assert g1["my_guess"]["cards"][1]["cracked"] is False
        assert g1["revealed"] is False

        # 场 2：预填卡 0 已看破、次数/历史带入，仍可续猜
        b2 = _challenge(client, eid, h_b, ld_b["id"], f"{GOD} 胜者：{name_b}")
        assert b2["my_guess"]["cards"][0]["cracked"] is True
        assert b2["my_guess"]["cards"][0]["name"] == "影刃"
        assert b2["my_guess"]["cards"][1]["cracked"] is False
        assert b2["my_guess"]["history"] == ["影刃化形，遁入暗影"]
        assert b2["my_guess"]["attempts_used"] == 1
        assert b2["can_guess"] is True


def test_board_subset_crack_does_not_early_reveal_or_flip():
    """本场用术子集全破 ≠ 刻印全破：不提前揭示整张刻印表，也不翻转胜负。"""
    with TestClient(app) as client:
        h_a, h_b = _mk_two_users(client, "tbsub")
        name_a = client.get("/api/auth/me", headers=h_a).json()["username"]
        name_b = client.get("/api/auth/me", headers=h_b).json()["username"]
        _give_ability(client, h_a, "影刃", "以暗影凝聚利刃斩杀敌人")
        _give_ability(client, h_a, "血咒", "以自身鲜血为引发动诅咒")
        _give_ability(client, h_a, "天雷", "引九天之雷轰击敌人")
        _give_ability(client, h_b, "火遁", "以火焰掩身遁走")
        ld_a = _arm(client, h_a)
        ld_b = _arm(client, h_b)
        eid = _board_entry(client, h_a, ld_a["id"])

        # 本场仅用影刃+血咒（usage 下标 1、2）；全部看破这 2 门
        b1 = _challenge(client, eid, h_b, ld_b["id"], f"{GOD} 胜者：{name_b}", usage_indices=[1, 2])
        assert b1["guess_total"] == 2
        g1 = _guess(client, b1, h_b, "影刃与血咒尽数", lambda kw: PairMatch(snippet="命中"), True)
        assert g1["my_guess"]["cards"][0]["cracked"] is True
        assert g1["my_guess"]["cards"][1]["cracked"] is True
        assert g1["my_guess"]["done"] is True
        # 子集全破但天雷未看破 → 不揭示刻印表、不翻转胜负
        assert g1["revealed"] is False
        assert g1["winner"] == name_b
        assert g1["guess_hit"] is None
        assert g1["unlocked"] is False

        # 场 2 全量用术（3 门）：前两门已预填看破，天雷仍保密 → 仍未全破
        b2 = _challenge(client, eid, h_b, ld_b["id"], f"{GOD} 胜者：{name_a}")
        assert b2["my_guess"]["cards"][0]["cracked"] is True
        assert b2["my_guess"]["cards"][1]["cracked"] is True
        assert b2["my_guess"]["cards"][2]["cracked"] is False
        assert b2["revealed"] is False
        assert b2["unlocked"] is False


def test_board_full_crack_skips_guess_and_unlocks_story():
    """全部看破：后续点将不再启动猜词、刻印全揭示，解锁上帝视角 + 刻印视角。"""
    with TestClient(app) as client:
        h_a, h_b = _mk_two_users(client, "tbfc")
        name_a = client.get("/api/auth/me", headers=h_a).json()["username"]
        name_b = client.get("/api/auth/me", headers=h_b).json()["username"]
        _give_ability(client, h_a, "影刃", "以暗影凝聚利刃斩杀敌人")
        _give_ability(client, h_b, "天雷", "引九天之雷轰击敌人")
        ld_a = _arm(client, h_a)
        ld_b = _arm(client, h_b)
        eid = _board_entry(client, h_a, ld_a["id"])

        # 场 1：一次全破唯一刻印奇术 → 本行结束，但不翻转胜负（猜词是研究不是反杀）
        b1 = _challenge(client, eid, h_b, ld_b["id"], f"{GOD} 胜者：{name_b}")
        g1 = _guess(client, b1, h_b, "影刃化形", lambda kw: PairMatch(snippet="影刃以暗影凝刃"), True)
        assert g1["my_guess"]["flipped"] is True and g1["my_guess"]["done"] is True
        assert g1["winner"] == name_b  # 全破不逆转
        assert g1["guess_hit"] is None
        assert g1["revealed"] is True  # 全破揭示
        assert g1["unlocked"] is True
        assert g1["story"]["narration"]  # 上帝视角解锁
        assert g1["story"]["narration_b"]  # 刻印视角解锁
        assert g1["story"]["abilities_b"]  # 刻印奇术表解锁

        # 场 2：不再启动猜词，直接三视角
        b2 = _challenge(client, eid, h_b, ld_b["id"], f"{GOD} 胜者：{name_a}")
        assert b2["unlocked"] is True
        assert b2["can_guess"] is False
        assert b2["guess_total"] == 0
        assert b2["my_guess"] is None
        assert b2["revealed"] is True
        assert b2["story"]["narration"]
        assert b2["story"]["narration_b"]
        assert b2["story"]["abilities_b"]


def test_board_give_up_keeps_progress():
    """收手未全破：进度保留、不置 done，下场仍可猜、未看破卡继续保密。"""
    with TestClient(app) as client:
        h_a, h_b = _mk_two_users(client, "tbgu")
        name_b = client.get("/api/auth/me", headers=h_b).json()["username"]
        _give_ability(client, h_a, "影刃", "以暗影凝聚利刃斩杀敌人")
        _give_ability(client, h_a, "血咒", "以自身鲜血为引发动诅咒")
        _give_ability(client, h_b, "天雷", "引九天之雷轰击敌人")
        ld_a = _arm(client, h_a)
        ld_b = _arm(client, h_b)
        eid = _board_entry(client, h_a, ld_a["id"])

        b1 = _challenge(client, eid, h_b, ld_b["id"], f"{GOD} 胜者：{name_b}")
        g1 = _guess(client, b1, h_b, "影刃化形", _pair_only("以暗影凝聚", "影刃以暗影凝刃"), True)
        rj = client.post(f"/api/battles/{g1['id']}/give-up", headers=h_b).json()
        assert rj["my_guess"]["done"] is True
        assert rj["my_guess"]["flipped"] is False
        assert rj["revealed"] is False  # 收手不揭示

        b2 = _challenge(client, eid, h_b, ld_b["id"], f"{GOD} 胜者：{name_b}")
        assert b2["my_guess"]["cards"][0]["cracked"] is True  # 已看破卡保留
        assert b2["my_guess"]["cards"][1]["cracked"] is False
        assert b2["can_guess"] is True  # 下场仍可猜


def test_board_progress_not_shared_across_entries():
    """不同刻印（不同快照）不共享进度：换一个 entry 从头开始。"""
    with TestClient(app) as client:
        h_a, h_b = _mk_two_users(client, "tbsh")
        name_a = client.get("/api/auth/me", headers=h_a).json()["username"]
        name_b = client.get("/api/auth/me", headers=h_b).json()["username"]
        _give_ability(client, h_a, "影刃", "以暗影凝聚利刃斩杀敌人")
        _give_ability(client, h_b, "天雷", "引九天之雷轰击敌人")
        ld_a = _arm(client, h_a)
        ld_b = _arm(client, h_b)
        # 同一奇人可多席：两次上榜 = 两个独立刻印
        eid1 = _board_entry(client, h_a, ld_a["id"])
        eid2 = _board_entry(client, h_a, ld_a["id"])

        b1 = _challenge(client, eid1, h_b, ld_b["id"], f"{GOD} 胜者：{name_b}")
        g1 = _guess(client, b1, h_b, "影刃化形", lambda kw: PairMatch(snippet="影刃以暗影凝刃"), True)
        assert g1["unlocked"] is True

        b2 = _challenge(client, eid2, h_b, ld_b["id"], f"{GOD} 胜者：{name_a}")
        assert b2["unlocked"] is False
        assert b2["can_guess"] is True
        assert b2["my_guess"]["cards"][0]["cracked"] is False


# ---------------------------------------------------------------------------
# 榜主被动 + 挑战者视角
# ---------------------------------------------------------------------------


def test_board_poster_passive_and_rewards():
    """榜主：行迹不含点将局、单场/流/再战/榜主侧传阅全禁；双方 +5 见闻照发。"""
    with TestClient(app) as client:
        h_a, h_b = _mk_two_users(client, "tbpp")
        name_b = client.get("/api/auth/me", headers=h_b).json()["username"]
        _give_ability(client, h_a, "影刃", "以暗影凝聚利刃斩杀敌人")
        _give_ability(client, h_b, "天雷", "引九天之雷轰击敌人")
        ld_a = _arm(client, h_a)
        ld_b = _arm(client, h_b)
        eid = _board_entry(client, h_a, ld_a["id"])

        exp_a_before = client.get("/api/auth/me", headers=h_a).json()["exp"]
        exp_b_before = client.get("/api/auth/me", headers=h_b).json()["exp"]
        b = _challenge(client, eid, h_b, ld_b["id"], f"{GOD} 胜者：{name_b}")
        assert b["winner"] == name_b
        # 双方 +5 见闻
        assert client.get("/api/auth/me", headers=h_a).json()["exp"] >= exp_a_before + 5
        assert client.get("/api/auth/me", headers=h_b).json()["exp"] >= exp_b_before + 5

        # 行迹：挑战者有点将局，榜主没有
        mine_a = client.get("/api/battles", headers=h_a).json()
        mine_b = client.get("/api/battles", headers=h_b).json()
        assert all(x["id"] != b["id"] for x in mine_a)
        assert any(x["id"] == b["id"] and x["board_entry_id"] == eid for x in mine_b)

        # 榜主不能查看单场 / 订阅流 / 再战（点将局一律不可再战） / 榜主侧传阅
        assert client.get(f"/api/battles/{b['id']}", headers=h_a).status_code == 403
        assert client.get(f"/api/battles/{b['id']}/stream", headers=h_a).status_code == 404
        assert client.post(f"/api/battles/{b['id']}/rematch", headers=h_a).status_code == 400
        assert client.post(f"/api/battles/{b['id']}/rematch", headers=h_b).status_code == 400
        assert client.get(f"/api/battles/share/{b['share_token_b']}").status_code == 404
        assert client.get(f"/api/battles/share/{b['share_token']}").status_code == 200  # 挑战者侧传阅可用


def test_board_challenge_count_grows():
    """榜单条目「被挑战次数」随点将增长（浏览量语义）。"""
    with TestClient(app) as client:
        h_a, h_b = _mk_two_users(client, "tbcc")
        name_a = client.get("/api/auth/me", headers=h_a).json()["username"]
        name_b = client.get("/api/auth/me", headers=h_b).json()["username"]
        _give_ability(client, h_a, "影刃", "以暗影凝聚利刃斩杀敌人")
        _give_ability(client, h_b, "天雷", "引九天之雷轰击敌人")
        ld_a = _arm(client, h_a)
        ld_b = _arm(client, h_b)
        eid = _board_entry(client, h_a, ld_a["id"])

        def _count():
            return next(e for e in client.get("/api/board", headers=h_b).json() if e["id"] == eid)[
                "challenge_count"
            ]

        assert _count() == 0
        _challenge(client, eid, h_b, ld_b["id"], f"{GOD} 胜者：{name_b}")
        assert _count() == 1
        _challenge(client, eid, h_b, ld_b["id"], f"{GOD} 胜者：{name_a}")
        assert _count() == 2


# ---------------------------------------------------------------------------
# 进度清理
# ---------------------------------------------------------------------------


def test_admin_delete_user_clears_challenger_progress():
    """admin 删挑战者 → 其点将看破进度清空。"""
    with TestClient(app) as client:
        h_a, h_b = _mk_two_users(client, "tbdel")
        name_b = client.get("/api/auth/me", headers=h_b).json()["username"]
        user_b_id = client.get("/api/auth/me", headers=h_b).json()["id"]
        _give_ability(client, h_a, "影刃", "以暗影凝聚利刃斩杀敌人")
        _give_ability(client, h_b, "天雷", "引九天之雷轰击敌人")
        ld_a = _arm(client, h_a)
        ld_b = _arm(client, h_b)
        eid = _board_entry(client, h_a, ld_a["id"])

        b1 = _challenge(client, eid, h_b, ld_b["id"], f"{GOD} 胜者：{name_b}")
        _guess(client, b1, h_b, "影刃化形", lambda kw: PairMatch(snippet="影刃以暗影凝刃"), True)

        con = _sqlite()
        cur = con.execute(
            "SELECT 1 FROM board_guess_progress WHERE challenger_id=%s AND board_entry_id=%s",
            (user_b_id, eid),
        )
        assert cur.fetchone() is not None  # 进度已落
        con.close()

        # 提管理员后删挑战者
        adm = _mk_user(client, "tbadm")
        h_adm = {"Authorization": f"Bearer {adm}"}
        adm_name = client.get("/api/auth/me", headers=h_adm).json()["username"]
        con = _sqlite()
        con.execute("UPDATE users SET is_admin=TRUE WHERE username=%s", (adm_name,))
        con.commit()
        con.close()
        assert client.delete(f"/api/admin/users/{user_b_id}", headers=h_adm).status_code == 204

        con = _sqlite()
        cur = con.execute(
            "SELECT 1 FROM board_guess_progress WHERE challenger_id=%s AND board_entry_id=%s",
            (user_b_id, eid),
        )
        assert cur.fetchone() is None  # 进度已清
        con.close()


def test_take_off_board_cascades_progress():
    """榜主下榜 → 该刻印的挑战者进度级联删除。"""
    with TestClient(app) as client:
        h_a, h_b = _mk_two_users(client, "tbcas")
        name_b = client.get("/api/auth/me", headers=h_b).json()["username"]
        user_b_id = client.get("/api/auth/me", headers=h_b).json()["id"]
        _give_ability(client, h_a, "影刃", "以暗影凝聚利刃斩杀敌人")
        _give_ability(client, h_b, "天雷", "引九天之雷轰击敌人")
        ld_a = _arm(client, h_a)
        ld_b = _arm(client, h_b)
        eid = _board_entry(client, h_a, ld_a["id"])

        b1 = _challenge(client, eid, h_b, ld_b["id"], f"{GOD} 胜者：{name_b}")
        _guess(client, b1, h_b, "影刃化形", lambda kw: PairMatch(snippet="影刃以暗影凝刃"), True)

        con = _sqlite()
        cur = con.execute(
            "SELECT 1 FROM board_guess_progress WHERE challenger_id=%s AND board_entry_id=%s",
            (user_b_id, eid),
        )
        assert cur.fetchone() is not None
        con.close()

        # 榜主下榜 → FK CASCADE 清进度
        assert client.delete(f"/api/board/{eid}", headers=h_a).status_code == 204
        con = _sqlite()
        cur = con.execute(
            "SELECT 1 FROM board_guess_progress WHERE challenger_id=%s AND board_entry_id=%s",
            (user_b_id, eid),
        )
        assert cur.fetchone() is None
        con.close()


# ---------------------------------------------------------------------------
# 条目详情页
# ---------------------------------------------------------------------------


def test_board_detail_progress_and_battles():
    """详情页：挑战者视角看破进度（已看破亮出名/效果，未看破保密）+ 自己的对局记录倒序。"""
    with TestClient(app) as client:
        h_a, h_b = _mk_two_users(client, "tbdt")
        name_b = client.get("/api/auth/me", headers=h_b).json()["username"]
        _give_ability(client, h_a, "影刃", "以暗影凝聚利刃斩杀敌人")
        _give_ability(client, h_a, "血咒", "以自身鲜血为引发动诅咒")
        _give_ability(client, h_b, "天雷", "引九天之雷轰击敌人")
        ld_a = _arm(client, h_a)
        ld_b = _arm(client, h_b)
        eid = _board_entry(client, h_a, ld_a["id"])

        b1 = _challenge(client, eid, h_b, ld_b["id"], f"{GOD} 胜者：{name_b}")
        _guess(client, b1, h_b, "影刃化形，遁入暗影", _pair_only("以暗影凝聚", "影刃以暗影凝刃"), True)
        b2 = _challenge(client, eid, h_b, ld_b["id"], f"{GOD} 胜者：{name_b}")

        d = client.get(f"/api/board/{eid}", headers=h_b).json()
        assert d["mine"] is False
        assert d["ability_count"] == 2
        assert d["challenge_count"] == 2
        # 已看破卡亮出真实名/效果，未看破保密
        assert d["progress"][0]["cracked"] is True
        assert d["progress"][0]["name"] == "影刃"
        assert d["progress"][0]["effect"] == "以暗影凝聚利刃斩杀敌人"
        assert d["progress"][0]["matched"]  # 线索片段保留
        assert d["progress"][1]["cracked"] is False
        assert d["progress"][1]["name"] is None
        assert d["progress"][1]["effect"] is None
        # 对局记录：自己的点将局，倒序
        assert [x["id"] for x in d["battles"]] == [b2["id"], b1["id"]]
        assert all(x["board_entry_id"] == eid for x in d["battles"])


def test_board_detail_fresh_viewer_all_hidden():
    """未点将过的第三方：进度全保密、无对局记录（不泄漏挑战者的看破进度）。"""
    with TestClient(app) as client:
        h_a, h_b = _mk_two_users(client, "tbdf")
        name_b = client.get("/api/auth/me", headers=h_b).json()["username"]
        h_c = {"Authorization": f"Bearer {_mk_user(client, 'tbdf_c')}"}
        _give_ability(client, h_a, "影刃", "以暗影凝聚利刃斩杀敌人")
        _give_ability(client, h_a, "血咒", "以自身鲜血为引发动诅咒")
        _give_ability(client, h_b, "天雷", "引九天之雷轰击敌人")
        ld_a = _arm(client, h_a)
        ld_b = _arm(client, h_b)
        eid = _board_entry(client, h_a, ld_a["id"])

        b1 = _challenge(client, eid, h_b, ld_b["id"], f"{GOD} 胜者：{name_b}")
        _guess(client, b1, h_b, "影刃化形", _pair_only("以暗影凝聚", "影刃以暗影凝刃"), True)

        d = client.get(f"/api/board/{eid}", headers=h_c).json()
        assert d["mine"] is False
        assert all(not c["cracked"] and c["name"] is None for c in d["progress"])
        assert d["battles"] == []


def test_board_detail_poster_reveals_all_no_battles():
    """榜主视角：刻印全貌可见、无任何挑战者对局记录（发帖语义）。"""
    with TestClient(app) as client:
        h_a, h_b = _mk_two_users(client, "tbdp")
        name_b = client.get("/api/auth/me", headers=h_b).json()["username"]
        _give_ability(client, h_a, "影刃", "以暗影凝聚利刃斩杀敌人")
        _give_ability(client, h_b, "天雷", "引九天之雷轰击敌人")
        ld_a = _arm(client, h_a)
        ld_b = _arm(client, h_b)
        eid = _board_entry(client, h_a, ld_a["id"])

        _challenge(client, eid, h_b, ld_b["id"], f"{GOD} 胜者：{name_b}")

        d = client.get(f"/api/board/{eid}", headers=h_a).json()
        assert d["mine"] is True
        assert d["challenge_count"] == 1
        assert all(c["cracked"] for c in d["progress"])  # 榜主看全貌
        assert d["progress"][0]["name"] == "影刃"
        assert d["battles"] == []  # 无挑战者行迹


def test_board_detail_404():
    """不存在的条目 → 404。"""
    with TestClient(app) as client:
        h_a, _ = _mk_two_users(client, "tbd404")
        assert client.get("/api/board/999999", headers=h_a).status_code == 404
