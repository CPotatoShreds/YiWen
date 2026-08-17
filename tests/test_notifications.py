"""通知系统测试：三类通知触发（点将挑战/新战报/猜词进展）+ 已读接口 + SSE 实时流。

打桩方式与 test_board_progress.py 一致：conftest 全局打桩 usage/validate/discuss/理解，
推演（_build_deduce_llm）与转写（_build_transcribe_chain）、猜词点评/检定
（_build_commentary/verify_llm）在此按测试作用域打桩。

覆盖语义：
- 点将挑战 → 榜主收 board_challenge（ref=board）；点将局榜主不收 battle_report/guess_progress。
- 完整对战落定 → 双方各收 battle_report（ref=battle）。
- 猜词每次点评 → 被猜方收 guess_progress（点评即窥探）；检定产生新看破 → 再追加一条；检定无新看破不刷屏。
- 已读/全部已读幂等递减 unread；非本人/未登录被拒。
- SSE 开流后新通知落库 → 流内收到 notification 事件（客户端据此重拉对账）。
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


def _mk_user(client, prefix="tnnot") -> str:
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


def _challenge(client, entry_id, h_challenger, loadout_id, god_text):
    """点将挑战（打桩推演/转写），等待落定后返回行迹 dict。"""
    with (
        patch("app.services.battle._build_deduce_llm", return_value=_deduce(god_text)),
        patch("app.services.battle._build_transcribe_chain", return_value=_transcribe(NAR_A, NAR_B)),
    ):
        rc = client.post(f"/api/board/{entry_id}/challenge", json={"loadout_id": loadout_id}, headers=h_challenger)
        assert rc.status_code == 200, rc.text
        return _wait_done(client, rc.json()["battle_id"], h_challenger)


def _mk_battle(client, h_a, h_b, name_a):
    """组装一局完整对战：默认 A 胜 → B 为败方/猜词者。返回等待落定后的行迹 dict。"""
    user_b_id = client.get("/api/auth/me", headers=h_b).json()["id"]
    with (
        patch("app.services.battle._build_deduce_llm", return_value=_deduce(f"{GOD} 胜者：{name_a}")),
        patch("app.services.battle._build_transcribe_chain", return_value=_transcribe(NAR_A, NAR_B)),
        patch("app.services.battle.pick_opponent", new=AsyncMock(return_value=user_b_id)),
    ):
        r = client.post("/api/battles", headers=h_a)
        assert r.status_code == 200
        return _wait_done(client, r.json()["id"], h_a)


def _notifs(client, headers):
    return client.get("/api/notifications", headers=headers).json()


def _wait_unread(client, headers, expected, timeout=5):
    """等通知落库：猜词先 commit 后发通知，读列表可能早于通知 commit（微秒级滞后），轮询对齐。"""
    lst = None
    for _ in range(int(timeout / 0.1)):
        lst = _notifs(client, headers)
        if lst["unread"] == expected:
            return lst
        time.sleep(0.1)
    return lst


# ---------------------------------------------------------------------------
# 点将挑战通知 + 点将局榜主排除
# ---------------------------------------------------------------------------


def test_board_challenge_notifies_owner_only():
    """点将挑战 → 榜主收 board_challenge（ref=board）；点将局榜主不 battle_report/guess_progress。

    榜主不可查看点将单场（get_battle 403），故只收「有人点将」通知跳奇人榜；
    猜词进展归并到榜单，不逐场打扰榜主。
    """
    with TestClient(app) as client:
        h_a, h_b = _mk_two_users(client, "tnbc")
        name_a = client.get("/api/auth/me", headers=h_a).json()["username"]
        name_b = client.get("/api/auth/me", headers=h_b).json()["username"]
        _give_ability(client, h_a, "影刃", "以暗影凝聚利刃斩杀敌人")
        _give_ability(client, h_b, "天雷", "引九天之雷轰击敌人")
        ld_a = _arm(client, h_a)
        ld_b = _arm(client, h_b)
        eid = _board_entry(client, h_a, ld_a["id"])

        # 挑战落定
        b = _challenge(client, eid, h_b, ld_b["id"], f"{GOD} 胜者：{name_b}")

        # 榜主：仅 1 条 board_challenge，指向奇人榜；无 battle_report
        lst_a = _notifs(client, h_a)
        assert lst_a["unread"] == 1
        (n,) = lst_a["items"]
        assert n["type"] == "board_challenge"
        assert n["title"] == "你的奇人被点将挑战"
        assert name_b in n["body"] and name_a in n["body"]  # 挑战者名 + 刻印奇人名（= 榜主名）
        assert n["ref_type"] == "board" and n["ref_id"] == eid
        assert n["read"] is False

        # 挑战者：收到 battle_report（点将局仅挑战者可见单场），且不因点将收 board_challenge
        lst_b = _notifs(client, h_b)
        (m,) = lst_b["items"]
        assert m["type"] == "battle_report"
        assert m["ref_type"] == "battle" and m["ref_id"] == b["id"]
        assert m["body"].find(name_a) != -1

        # 挑战者猜词（点评 + 检定看破）：榜主仍只有 board_challenge（无 guess_progress）
        commentary, verify = _guess_pipeline(lambda kw: Verification(cracked=True, missing=""))
        with (
            patch("app.services.battle._build_commentary_llm", return_value=commentary),
            patch("app.services.battle._build_verify_llm", return_value=verify),
        ):
            g = _post_guess(client, f"/api/battles/{b['id']}/guess", h_b, text="影刃化形，遁入暗影")
            assert g.status_code == 202
            _wait_guess(client, b["id"], h_b, attempts_before=0)
            gv = _post_guess(client, f"/api/battles/{b['id']}/guess/verify", h_b)
            assert gv.status_code == 202
            _wait_guess(client, b["id"], h_b, attempts_before=1)

        lst_a = _notifs(client, h_a)
        assert lst_a["unread"] == 1
        assert lst_a["items"][0]["type"] == "board_challenge"


# ---------------------------------------------------------------------------
# 完整对战：双方战报
# ---------------------------------------------------------------------------


def test_full_battle_notifies_both_participants():
    """完整对战落定 → 双方各收 1 条 battle_report（ref=battle）。"""
    with TestClient(app) as client:
        h_a, h_b = _mk_two_users(client, "tnbr")
        name_a = client.get("/api/auth/me", headers=h_a).json()["username"]
        name_b = client.get("/api/auth/me", headers=h_b).json()["username"]
        _give_ability(client, h_a, "影刃", "以暗影凝聚利刃斩杀敌人")
        _give_ability(client, h_b, "天雷", "引九天之雷轰击敌人")
        _arm(client, h_a)
        _arm(client, h_b)

        b = _mk_battle(client, h_a, h_b, name_a)
        assert b["winner"] == name_a

        for h, other in ((h_a, name_b), (h_b, name_a)):
            lst = _notifs(client, h)
            assert lst["unread"] == 1
            (n,) = lst["items"]
            assert n["type"] == "battle_report"
            assert n["ref_type"] == "battle" and n["ref_id"] == b["id"]
            assert n["body"].find(other) != -1


# ---------------------------------------------------------------------------
# 猜词进展：仅新进展通知
# ---------------------------------------------------------------------------


def test_guess_progress_notifies_commentary_and_new_cracks():
    """败方每次点评 → 胜方收 guess_progress；检定产生新看破 → 再收一条；检定无新看破不追加。

    点评即新的窥探行为，每次点评都通知被猜方；检定仅在产生新看破时打扰，避免纯重复检定刷屏。
    """
    with TestClient(app) as client:
        h_a, h_b = _mk_two_users(client, "tngp")
        name_a = client.get("/api/auth/me", headers=h_a).json()["username"]
        _give_ability(client, h_a, "雷暴召来", "召唤雷霆轰击对手")
        _give_ability(client, h_a, "影刃", "以暗影凝聚利刃斩杀敌人")
        _give_ability(client, h_b, "镜面反射", "将对手的攻击原样反射回去")
        _arm(client, h_a)
        _arm(client, h_b)

        b = _mk_battle(client, h_a, h_b, name_a)

        # 落定后：双方各 1 条战报
        lst_a = _notifs(client, h_a)
        assert lst_a["unread"] == 1 and lst_a["items"][0]["type"] == "battle_report"

        # 猜 1（点评）：不动看破，但点评本身即窥探 → 追加 guess_progress（已看破 0 门）
        commentary, verify = _guess_pipeline(
            lambda text: Verification(cracked=True, missing="") if "雷暴" in text else Verification(cracked=False, missing="")
        )
        with (
            patch("app.services.battle._build_commentary_llm", return_value=commentary),
            patch("app.services.battle._build_verify_llm", return_value=verify),
        ):
            g = _post_guess(client, f"/api/battles/{b['id']}/guess", h_b, text="掌控雷电轰击目标")
            assert g.status_code == 202
            gb1 = _wait_guess(client, b["id"], h_b, attempts_before=0)
        assert sorted(c["cracked"] for c in gb1["guess_cards"]) == [False, False]  # 点评不动看破
        lst_a = _wait_unread(client, h_a, 2)  # 等通知落库（guess commit 后微秒级滞后）
        assert lst_a["items"][0]["type"] == "guess_progress"
        assert lst_a["items"][0]["ref_type"] == "battle" and lst_a["items"][0]["ref_id"] == b["id"]
        assert "已看破 0 门" in lst_a["items"][0]["body"]

        # 检定 1：看破一门 → 追加 guess_progress（已看破 1 门）
        with (
            patch("app.services.battle._build_commentary_llm", return_value=commentary),
            patch("app.services.battle._build_verify_llm", return_value=verify),
        ):
            gv = _post_guess(client, f"/api/battles/{b['id']}/guess/verify", h_b)
            assert gv.status_code == 202
            _wait_guess(client, b["id"], h_b, attempts_before=1)
        lst_a = _wait_unread(client, h_a, 3)
        assert lst_a["items"][0]["type"] == "guess_progress"
        assert "已看破 1 门" in lst_a["items"][0]["body"]

        # 猜 2（点评）：重复猜测也通知（点评即窥探行为）
        commentary2, verify2 = _guess_pipeline()
        with (
            patch("app.services.battle._build_commentary_llm", return_value=commentary2),
            patch("app.services.battle._build_verify_llm", return_value=verify2),
        ):
            g = _post_guess(client, f"/api/battles/{b['id']}/guess", h_b, text="信口胡说")
            assert g.status_code == 202
            _wait_guess(client, b["id"], h_b, attempts_before=2)
        lst_a = _wait_unread(client, h_a, 4)
        assert lst_a["items"][0]["type"] == "guess_progress"

        # 检定 2：无新看破 → 不追加
        with (
            patch("app.services.battle._build_commentary_llm", return_value=commentary2),
            patch("app.services.battle._build_verify_llm", return_value=verify2),
        ):
            gv = _post_guess(client, f"/api/battles/{b['id']}/guess/verify", h_b)
            assert gv.status_code == 202
            _wait_guess(client, b["id"], h_b, attempts_before=3)
        lst_a = _wait_unread(client, h_a, 4)  # 未新增
        assert lst_a["items"][0]["type"] == "guess_progress"


# ---------------------------------------------------------------------------
# 已读接口
# ---------------------------------------------------------------------------


def test_mark_read_and_mark_all_read():
    """单条已读幂等、非本人 404；全部已读 → unread 归零。"""
    with TestClient(app) as client:
        h_a, h_b = _mk_two_users(client, "tnrd")
        name_b = client.get("/api/auth/me", headers=h_b).json()["username"]
        _give_ability(client, h_a, "影刃", "以暗影凝聚利刃斩杀敌人")
        _give_ability(client, h_b, "天雷", "引九天之雷轰击敌人")
        ld_a = _arm(client, h_a)
        ld_b = _arm(client, h_b)
        eid = _board_entry(client, h_a, ld_a["id"])

        # 两次点将 → 榜主 2 条未读
        _challenge(client, eid, h_b, ld_b["id"], f"{GOD} 胜者：{name_b}")
        _challenge(client, eid, h_b, ld_b["id"], f"{GOD} 胜者：{name_b}")
        lst = _notifs(client, h_a)
        assert lst["unread"] == 2

        # 单条已读（幂等）；非本人标记 → 404
        nid = lst["items"][0]["id"]
        assert client.post(f"/api/notifications/{nid}/read", headers=h_a).status_code == 204
        assert client.post(f"/api/notifications/{nid}/read", headers=h_a).status_code == 204
        assert client.post(f"/api/notifications/{nid}/read", headers=h_b).status_code == 404
        lst = _notifs(client, h_a)
        assert lst["unread"] == 1
        assert next(n for n in lst["items"] if n["id"] == nid)["read"] is True

        # 全部已读 → 归零
        assert client.post("/api/notifications/read-all", headers=h_a).status_code == 204
        lst = _notifs(client, h_a)
        assert lst["unread"] == 0
        assert all(n["read"] for n in lst["items"])


def test_notifications_require_auth():
    """未登录访问通知接口 → 401。"""
    with TestClient(app) as client:
        assert client.get("/api/notifications").status_code == 401
        assert client.post("/api/notifications/1/read").status_code == 401
        assert client.post("/api/notifications/read-all").status_code == 401
        with client.stream("GET", "/api/notifications/stream") as r:
            assert r.status_code == 401


# ---------------------------------------------------------------------------
# 实时总线（SSE 的投递机制）
# ---------------------------------------------------------------------------


async def test_notification_bus_pushes_event_to_subscriber():
    """实时总线：订阅者在新通知落库时即时收到 {type, id}；无订阅者静默跳过（行已在库）。

    通知流是长连接 SSE（永不自行终止），而 TestClient 传输层会阻塞到应用协程完成，
    无法经 HTTP 层读永续流——故直接测服务层总线（subscribe → create_notification → publish），
    SSE 端点本身的认证路径由 test_notifications_require_auth 覆盖。
    """
    from sqlalchemy import func, select

    from app.db.base import async_session_factory
    from app.models.notification import Notification
    from app.models.user import User
    from app.services.notifications import create_notification, subscribe, unsubscribe

    # 直插接收者用户（避免在 async 测试里跑 TestClient）
    async with async_session_factory() as db:
        u = User(username=f"bus_{uuid4().hex[:8]}", password_hash="x")
        db.add(u)
        await db.commit()
        await db.refresh(u)
        uid = u.id

    q = subscribe(uid)
    try:
        async with async_session_factory() as db:
            n = await create_notification(
                db,
                user_id=uid,
                type="battle_report",
                title="新的战报已送达",
                body="测试",
                ref_type="battle",
                ref_id=1,
            )
        assert q.get_nowait() == {"type": "notification", "id": n.id}
        assert q.empty()  # 每条只投递一次
    finally:
        unsubscribe(uid, q)

    # 无订阅者：create_notification 不报错、正常落库（客户端下次拉取对账即可见）
    async with async_session_factory() as db:
        await create_notification(db, user_id=uid, type="board_challenge", title="t", body="")
    async with async_session_factory() as db:
        cnt = (
            await db.execute(select(func.count()).select_from(Notification).where(Notification.user_id == uid))
        ).scalar_one()
        assert cnt == 2
