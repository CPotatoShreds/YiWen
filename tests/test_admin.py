"""后台管理路由测试：权限、用户/异能 CRUD、级联删除、仪表盘、流量。

直接改库用 psycopg（同步驱动）直连测试库，避免跨事件循环操作全局 async engine
的连接池（app 用 asyncpg，psycopg 是独立连接，无 loop 冲突）。
"""

import os
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient

from app.main import app


def _sqlite() -> psycopg.Connection:
    """直连 pytest 临时测试库（PG）。"""
    return psycopg.connect(os.environ["DATABASE_URL"].replace("+asyncpg", ""))


def _new_user(client, prefix="testadm") -> tuple[str, str, dict]:
    """注册 + 登录，返回 (用户名, token, 带认证头)。"""
    uname = f"{prefix}_" + uuid4().hex[:8]
    r = client.post("/api/auth/register", json={"username": uname, "password": "secret123"})
    assert r.status_code == 201, r.text
    tok = client.post("/api/auth/login", json={"username": uname, "password": "secret123"}).json()[
        "access_token"
    ]
    return uname, tok, {"Authorization": f"Bearer {tok}"}


def _user_id(client, headers) -> int:
    return client.get("/api/auth/me", headers=headers).json()["id"]


def _promote(username: str) -> None:
    """直接改库把用户提为管理员。"""
    con = _sqlite()
    cur = con.execute("UPDATE users SET is_admin=TRUE WHERE username=%s", (username,))
    assert cur.rowcount == 1, f"promote failed for {username}"
    con.commit()
    con.close()


def _insert_battle(user_a_id: int, user_b_id: int, status: str = "done") -> int:
    # 测试库由 create_all 建表：下划线列均为客户端默认（无 server_default），raw insert 必须
    # 显式提供，否则 NOT NULL 违反（live 库经迁移带 server_default，行为不同，故以 create_all 为准）。
    con = _sqlite()
    cur = con.execute(
        "INSERT INTO battles (user_a_id, user_b_id, story, status, rank_delta_a, rank_delta_b,"
        " friendly, guess_text, guess_state, revealed, revealed_a, revealed_b)"
        " VALUES (%s, %s, '', %s, 0, 0, FALSE, '', 'none', FALSE, FALSE, FALSE)"
        " RETURNING id",
        (user_a_id, user_b_id, status),
    )
    new_id = cur.fetchone()[0]
    con.commit()
    con.close()
    return new_id


def _insert_battle_guess(battle_id: int, guesser_id: int) -> None:
    con = _sqlite()
    con.execute(
        "INSERT INTO battle_guesses (battle_id, guesser_id, used_abilities, cards, guess_history,"
        " attempts_used, attempts_max, flipped, done)"
        " VALUES (%s, %s, '[]', '[]', '[]', 0, 5, FALSE, TRUE)",
        (battle_id, guesser_id),
    )
    con.commit()
    con.close()


def _insert_request_log(user_id: int | None, path: str = "/api/auth/me") -> None:
    con = _sqlite()
    con.execute(
        "INSERT INTO request_logs (method, path, status_code, duration_ms, user_id) VALUES (%s, %s, %s, %s, %s)",
        ("GET", path, 200, 4, user_id),
    )
    con.commit()
    con.close()


def test_non_admin_forbidden():
    with TestClient(app) as client:
        _, _, h = _new_user(client)
        for path in ("/api/admin/users", "/api/admin/stats", "/api/admin/traffic"):
            assert client.get(path, headers=h).status_code == 403
        assert client.post("/api/admin/users", json={"username": "x", "password": "xxxxxx"}, headers=h).status_code == 403
        # 普通用户前台照常
        assert client.get("/api/auth/me", headers=h).status_code == 200


def test_unauthenticated_401():
    with TestClient(app) as client:
        assert client.get("/api/admin/users").status_code == 401


def test_admin_user_crud():
    with TestClient(app) as client:
        uname, _, h = _new_user(client)
        _promote(uname)

        # 列表包含自己
        users = client.get("/api/admin/users", headers=h).json()
        assert any(u["username"] == uname and u["is_admin"] for u in users)

        # 新建
        r = client.post(
            "/api/admin/users",
            json={"username": "created_x", "password": "secret123", "exp": 50, "rank_points": 900, "is_admin": True},
            headers=h,
        )
        assert r.status_code == 201, r.text
        new_id = r.json()["id"]
        assert r.json()["exp"] == 50 and r.json()["rank_points"] == 900 and r.json()["is_admin"]

        # 改名重复 → 400
        assert client.put(f"/api/admin/users/{new_id}", json={"username": uname}, headers=h).status_code == 400

        # 修改
        r = client.put(
            f"/api/admin/users/{new_id}",
            json={"exp": 120, "rank_points": 950, "reveal_on_miss": False, "is_admin": False},
            headers=h,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["exp"] == 120 and body["rank_points"] == 950 and not body["is_admin"]

        # 搜索命中
        hits = client.get("/api/admin/users?search=created_x", headers=h).json()
        assert [u["id"] for u in hits] == [new_id]

        # 删除
        assert client.delete(f"/api/admin/users/{new_id}", headers=h).status_code == 204
        con = _sqlite()
        assert con.execute("SELECT 1 FROM users WHERE id=%s", (new_id,)).fetchone() is None
        con.close()


def test_guards_self_delete_and_self_demote():
    with TestClient(app) as client:
        uname, _, h = _new_user(client)
        my_id = _user_id(client, h)
        _promote(uname)
        # 不能删自己
        assert client.delete(f"/api/admin/users/{my_id}", headers=h).status_code == 400
        # 不能取消自己的管理员权限
        assert client.put(f"/api/admin/users/{my_id}", json={"is_admin": False}, headers=h).status_code == 400


def test_user_delete_cascade():
    with TestClient(app) as client:
        # A 管理员；B、C 普通用户
        _, _, h_a = _new_user(client)
        _promote(_me_name(client, h_a))

        _, _, h_b = _new_user(client, "testc_b")
        _, _, h_c = _new_user(client, "testc_c")
        b_id = _user_id(client, h_b)
        c_id = _user_id(client, h_c)

        # C 造数据：一个异能 + 一位装了该异能的奇人
        r = client.post("/api/abilities", json={"name": "燃烬", "effect": "点燃一切"}, headers=h_c)
        assert r.status_code == 201
        ld = client.post("/api/loadouts", json={"name": "赤焰君临"}, headers=h_c).json()
        for a in client.get("/api/abilities/mine", headers=h_c).json():
            assert client.post(f"/api/loadouts/{ld['id']}/abilities/{a['id']}", headers=h_c).status_code == 200
        lid = ld["id"]

        # B↔C 故人关系
        assert client.post("/api/friends/request", json={"friend_id": c_id}, headers=h_b).status_code == 200
        assert client.post(f"/api/friends/{b_id}/accept", headers=h_c).status_code == 200

        # C 参与一场 done 对战 + 猜词状态
        bid = _insert_battle(c_id, b_id, "done")
        _insert_battle_guess(bid, c_id)

        # C 有几条请求日志（软引用）
        _insert_request_log(c_id)
        # 删除 C
        assert client.delete(f"/api/admin/users/{c_id}", headers=h_a).status_code == 204

        con = _sqlite()
        assert con.execute("SELECT 1 FROM users WHERE id=%s", (c_id,)).fetchone() is None
        assert con.execute("SELECT 1 FROM user_abilities WHERE user_id=%s", (c_id,)).fetchone() is None
        assert con.execute("SELECT 1 FROM loadouts WHERE user_id=%s", (c_id,)).fetchone() is None
        assert con.execute("SELECT 1 FROM loadout_abilities WHERE loadout_id=%s", (lid,)).fetchone() is None
        assert (
            con.execute("SELECT 1 FROM battles WHERE user_a_id=%s OR user_b_id=%s", (c_id, c_id)).fetchone() is None
        )
        assert con.execute("SELECT 1 FROM battle_guesses WHERE battle_id=%s", (bid,)).fetchone() is None
        assert (
            con.execute("SELECT 1 FROM friendships WHERE user_id=%s OR friend_id=%s", (c_id, c_id)).fetchone() is None
        )
        # 请求日志软引用置空：不再有 user_id=c_id 的行
        assert con.execute("SELECT 1 FROM request_logs WHERE user_id=%s", (c_id,)).fetchone() is None
        con.close()


def _me_name(client, headers) -> str:
    return client.get("/api/auth/me", headers=headers).json()["username"]


def test_ability_admin_crud_and_force_delete():
    with TestClient(app) as client:
        _, _, h = _new_user(client)
        _promote(_me_name(client, h))

        # 后台新建（挂到某用户）
        r = client.post(
            "/api/admin/abilities",
            json={"name": "天罡", "effect": "召唤天雷", "owner_id": _user_id(client, h)},
            headers=h,
        )
        assert r.status_code == 201, r.text
        aid = r.json()["id"]

        # 修改（理解清空、不调度 LLM）
        r = client.put(f"/api/admin/abilities/{aid}", json={"name": "天罡改", "effect": "召唤暴雨"}, headers=h)
        assert r.status_code == 200
        assert r.json()["name"] == "天罡改"

        # 强制删除：user_abilities 引用一并清
        assert client.delete(f"/api/admin/abilities/{aid}", headers=h).status_code == 204
        con = _sqlite()
        assert con.execute("SELECT 1 FROM abilities WHERE id=%s", (aid,)).fetchone() is None
        assert con.execute("SELECT 1 FROM user_abilities WHERE ability_id=%s", (aid,)).fetchone() is None
        con.close()


def test_battle_read_and_delete():
    with TestClient(app) as client:
        _, _, h_a = _new_user(client)
        a_name = _me_name(client, h_a)
        _, _, h_b = _new_user(client, "testbt_b")
        b_id = _user_id(client, h_b)
        _promote(a_name)

        done_id = _insert_battle(_user_id(client, h_a), b_id, "done")
        _insert_battle_guess(done_id, b_id)
        pending_id = _insert_battle(_user_id(client, h_a), b_id, "pending")

        # 列表
        battles = client.get("/api/admin/battles", headers=h_a).json()
        assert any(b["id"] == done_id and b["status"] == "done" for b in battles)

        # 详情（上帝视角 story 原样返回）
        detail = client.get(f"/api/admin/battles/{done_id}", headers=h_a).json()
        assert detail["id"] == done_id and detail["status"] == "done"

        # pending 不可删
        assert client.delete(f"/api/admin/battles/{pending_id}", headers=h_a).status_code == 409
        # done 可删（连同猜词状态）
        assert client.delete(f"/api/admin/battles/{done_id}", headers=h_a).status_code == 204
        con = _sqlite()
        assert con.execute("SELECT 1 FROM battles WHERE id=%s", (done_id,)).fetchone() is None
        assert con.execute("SELECT 1 FROM battle_guesses WHERE battle_id=%s", (done_id,)).fetchone() is None
        assert con.execute("SELECT 1 FROM battles WHERE id=%s", (pending_id,)).fetchone() is not None
        con.close()
        # 顺带清掉 pending（后台禁止删 pending，直接改库清理本测试的 raw 数据）
        con = _sqlite()
        con.execute("DELETE FROM battles WHERE id=%s", (pending_id,))
        con.commit()
        con.close()


def test_loadout_and_friendship_delete():
    with TestClient(app) as client:
        _, _, h_a = _new_user(client)
        a_name = _me_name(client, h_a)
        _, _, h_b = _new_user(client, "testlf_b")
        b_id = _user_id(client, h_b)
        a_id = _user_id(client, h_a)
        _promote(a_name)

        # 建奇人 + 故人
        ld = client.post("/api/loadouts", json={"name": "奇人·壹"}, headers=h_b).json()
        client.post("/api/friends/request", json={"friend_id": _user_id(client, h_a)}, headers=h_b)

        # 奇人删除
        assert client.delete(f"/api/admin/loadouts/{ld['id']}", headers=h_a).status_code == 204
        con = _sqlite()
        assert con.execute("SELECT 1 FROM loadouts WHERE id=%s", (ld["id"],)).fetchone() is None
        con.close()

        # 故人列表 → 删除
        friends = [f for f in client.get("/api/admin/friendships", headers=h_a).json() if {f["user_id"], f["friend_id"]} == {a_id, b_id}]
        assert len(friends) == 1
        row = friends[0]
        assert client.delete(f"/api/admin/friendships/{row['user_id']}/{row['friend_id']}", headers=h_a).status_code == 204
        con = _sqlite()
        assert con.execute(
            "SELECT 1 FROM friendships WHERE user_id=%s AND friend_id=%s",
            (row["user_id"], row["friend_id"]),
        ).fetchone() is None
        con.close()


def test_stats_counts():
    with TestClient(app) as client:
        _, _, h_a = _new_user(client)
        a_name = _me_name(client, h_a)
        a_id = _user_id(client, h_a)
        _, _, h_b = _new_user(client, "testst_b")
        b_id = _user_id(client, h_b)
        _promote(a_name)

        # 造点数据：B 一个异能 + 奇人；一场 done 对战
        client.post("/api/abilities", json={"name": "冰封", "effect": "冻结一切"}, headers=h_b)
        client.post("/api/loadouts", json={"name": "霜语者"}, headers=h_b)
        _insert_battle(a_id, b_id, "done")
        _insert_battle(a_id, b_id, "failed")

        stats = client.get("/api/admin/stats", headers=h_a).json()
        assert stats["total_users"] >= 2
        assert stats["total_abilities"] >= 1
        assert stats["total_loadouts"] >= 1
        assert stats["total_battles"] >= 2
        assert stats["battles_done"] >= 1
        assert stats["battles_failed"] >= 1
        assert len(stats["recent_battles"]) >= 1


def test_traffic_aggregation():
    with TestClient(app) as client:
        _, _, h_a = _new_user(client)
        a_name = _me_name(client, h_a)
        _promote(a_name)
        # 流量中间件已停用，显式造三条请求日志
        for _ in range(3):
            _insert_request_log(_user_id(client, h_a))

        t = client.get("/api/admin/traffic", headers=h_a).json()
        assert t["total_requests"] >= 3
        assert t["last_24h"] >= 3
        assert t["avg_ms"] >= 0
        assert len(t["daily"]) == 7
        assert t["daily"][-1]["count"] >= 1  # 今天有请求
        assert any(ep["path"].endswith("/auth/me") for ep in t["endpoints"])
        assert len(t["recent"]) >= 1


# ---------- 对战试验场 ----------


def _test_ability(client, headers, name, effect):
    """后台建一个奇术，返回 id。"""
    r = client.post("/api/admin/abilities", json={"name": name, "effect": effect}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_test_arena_skip_battle_and_guess():
    """试验场：建测试账号 → 组装临时奇人 → 指定胜负 → 猜词（验证玩家表零污染）。"""
    with TestClient(app) as client:
        _, _, h = _new_user(client)
        _promote(_me_name(client, h))

        # 建两个测试账号
        a = client.post("/api/admin/test/users", json={"username": None, "exp": 10, "rank_points": 1000}, headers=h)
        assert a.status_code == 201, a.text
        b = client.post("/api/admin/test/users", json={"username": "b_bot", "rank_points": 1000}, headers=h)
        assert b.status_code == 201, b.text

        # 生成持久测试奇人（勾选奇术，名字随机、账号自动绑定）
        aid = _test_ability(client, h, "燃烬之握", "点燃一切")
        bid = _test_ability(client, h, "霜语者", "冻结一切")
        l_a = client.post("/api/admin/test/loadouts", json={"abilities": [aid]}, headers=h)
        assert l_a.status_code == 201, l_a.text
        l_a_id = l_a.json()["id"]
        assert l_a_id >= 1  # 持久化：真实 id，不再是 -1
        assert l_a.json()["username"]  # 自动绑定账号
        l_b = client.post("/api/admin/test/loadouts", json={"abilities": [bid]}, headers=h)
        assert l_b.status_code == 201, l_b.text
        l_b_id = l_b.json()["id"]

        # 指定胜负（skip）前记录玩家表基线（共享测试库可能已有他测造的 battles 行）
        con = _sqlite()
        battles_before = con.execute("SELECT COUNT(*) FROM battles").fetchone()[0]
        guesses_before = con.execute("SELECT COUNT(*) FROM battle_guesses").fetchone()[0]
        con.close()

        # 指定胜负（skip）→ 直接进猜词阶段
        r = client.post(
            "/api/admin/test/battles/skip",
            json={
                "fighter_a": {"name": "赤焰君临", "abilities": [aid], "owner": a.json()["username"]},
                "fighter_b": {"name": "霜语者", "abilities": [bid], "owner": b.json()["username"]},
                "winner": "A",
            },
            headers=h,
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == "done"
        assert body["winner"] == a.json()["username"]
        assert body["guess_state"] in ("none", "guessing")
        assert body["guess_total"] == 1  # 无叙述 → 默认全部奇术被使用
        tb_id = body["id"]

        # 猜词（三环节打桩默认不命中 → 无看破，次数耗尽揭示）
        g = client.post(
            f"/api/admin/test/battles/{tb_id}/guess",
            json={"text": "能点燃一切"},
            headers=h,
        )
        assert g.status_code == 200, g.text
        assert g.json()["guess_state"] == "guessing"

        # 玩家侧零污染：battles / battle_guesses 未新增（仅测试域落 test_* 表）
        con = _sqlite()
        assert con.execute("SELECT COUNT(*) FROM battles").fetchone()[0] == battles_before
        assert con.execute("SELECT COUNT(*) FROM battle_guesses").fetchone()[0] == guesses_before
        assert con.execute("SELECT COUNT(*) FROM users WHERE username IN ('赤焰君临','霜语者')").fetchone()[0] == 0
        con.close()

        # 测试行迹列表可见
        lst = client.get("/api/admin/test/battles", headers=h).json()
        assert any(b["id"] == tb_id for b in lst)

        # 删除测试行迹 + 测试账号 + 持久测试奇人
        assert client.delete(f"/api/admin/test/battles/{tb_id}", headers=h).status_code == 204
        assert client.delete(f"/api/admin/test/users/{b.json()['id']}", headers=h).status_code == 204
        assert client.delete(f"/api/admin/test/loadouts/{l_a_id}", headers=h).status_code == 204
        assert client.delete(f"/api/admin/test/loadouts/{l_b_id}", headers=h).status_code == 204


def test_test_arena_lists_persistent_loadouts():
    """试验场读持久测试奇人：含绑定账号名与装配奇术。"""
    with TestClient(app) as client:
        _, _, h = _new_user(client)
        _promote(_me_name(client, h))
        aid = _test_ability(client, h, "焚天", "烈焰焚城")
        created = client.post("/api/admin/test/loadouts", json={"abilities": [aid]}, headers=h)
        assert created.status_code == 201, created.text
        c = created.json()

        rows = client.get("/api/admin/test/loadouts", headers=h).json()
        assert any(
            l["id"] == c["id"] and l["name"] == c["name"] and l["user_id"] == c["user_id"]
            and l["username"] and len(l["abilities"]) >= 1
            for l in rows
        )


def test_test_arena_generate_loadout_persists_and_auto_account():
    """生成持久奇人：自动绑定账号、刷新仍存在、删奇人连带清空无对局引用账号；有对局则保留账号。"""
    with TestClient(app) as client:
        _, _, h = _new_user(client)
        _promote(_me_name(client, h))
        aid = _test_ability(client, h, "燃烬之握", "点燃一切")

        con = _sqlite()
        base_tl = con.execute("SELECT COUNT(*) FROM test_loadouts").fetchone()[0]
        base_tu = con.execute("SELECT COUNT(*) FROM test_users").fetchone()[0]

        created = client.post("/api/admin/test/loadouts", json={"abilities": [aid]}, headers=h)
        assert created.status_code == 201, created.text
        c = created.json()
        assert c["id"] > 0
        assert c["name"]
        assert c["style"] == ""  # 风格恒空
        assert c["username"]  # 自动绑定账号
        assert c["user_id"] > 0

        # 自动账号 + 持久奇人落库
        assert con.execute("SELECT COUNT(*) FROM test_loadouts").fetchone()[0] == base_tl + 1
        assert con.execute("SELECT COUNT(*) FROM test_users").fetchone()[0] == base_tu + 1
        join_row = con.execute(
            "SELECT 1 FROM test_loadout_abilities WHERE loadout_id=%s AND ability_id=%s",
            (c["id"], aid),
        ).fetchone()
        assert join_row is not None
        con.close()

        # 再 GET（模拟刷新/切页）→ 持久存在
        again = client.get("/api/admin/test/loadouts", headers=h).json()
        assert any(l["id"] == c["id"] for l in again)

        # 无对局引用 → 删奇人连带删绑定账号
        assert client.delete(f"/api/admin/test/loadouts/{c['id']}", headers=h).status_code == 204
        con = _sqlite()
        assert con.execute("SELECT COUNT(*) FROM test_loadouts WHERE id=%s", (c["id"],)).fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM test_users WHERE id=%s", (c["user_id"],)).fetchone()[0] == 0
        con.close()

    with TestClient(app) as client:
        _, _, h = _new_user(client)
        _promote(_me_name(client, h))
        aid = _test_ability(client, h, "燃烬之握", "点燃一切")
        bid = _test_ability(client, h, "霜语者", "冻结一切")
        l = client.post("/api/admin/test/loadouts", json={"abilities": [aid]}, headers=h).json()
        r = client.post(
            "/api/admin/test/battles/skip",
            json={
                "fighter_a": {"test_loadout_id": l["id"]},
                "fighter_b": {"name": "对家", "abilities": [bid], "owner": None},
                "winner": "A",
            },
            headers=h,
        )
        assert r.status_code == 201, r.text
        tb_id = r.json()["id"]
        # 有对局引用 → 删奇人后账号保留（行迹用户名仍可解析）
        assert client.delete(f"/api/admin/test/loadouts/{l['id']}", headers=h).status_code == 204
        con = _sqlite()
        assert con.execute("SELECT COUNT(*) FROM test_users WHERE id=%s", (l["user_id"],)).fetchone()[0] == 1
        con.close()
        detail = client.get(f"/api/admin/test/battles/{tb_id}", headers=h).json()
        assert detail["user_a"] == l["username"]
        assert client.delete(f"/api/admin/test/battles/{tb_id}", headers=h).status_code == 204


# ---------- LLM 链路追踪 ----------


def _wait_for_trace_count(con, n, *, kind=None, trace_id=None, timeout=3.0):
    """追踪落库是异步 fire-and-forget 任务：轮询 sqlite 直连直到达到期望条数。

    缺省统计全部记录；传 kind/trace_id 时只统计命中的记录——避免此前测试遗留的追踪记录
    让等待提前返回，与本次追踪异步落库竞态。
    """
    import time

    where = ""
    params = []
    if kind is not None:
        where += " AND kind=%s"
        params.append(kind)
    if trace_id is not None:
        where += " AND trace_id=%s"
        params.append(trace_id)
    sql = f"SELECT COUNT(*) FROM llm_traces WHERE 1=1{where}"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        cnt = con.execute(sql, params).fetchone()[0]
        if cnt >= n:
            return cnt
        time.sleep(0.05)
    return cnt


def test_llm_trace_recorded_for_guess_flow():
    """试验场猜词（打桩 LLM）应落 llm_traces 追踪记录：含环节、请求、输出，且管理端可查。"""
    with TestClient(app) as client:
        _, _, h = _new_user(client)
        _promote(_me_name(client, h))

        aid = _test_ability(client, h, "燃烬之握", "点燃一切")
        r = client.post(
            "/api/admin/test/battles/skip",
            json={
                "fighter_a": {"name": "赤焰君临", "abilities": [aid], "owner": None},
                "fighter_b": {"name": "霜语者", "abilities": [aid], "owner": None},
                "winner": "A",
            },
            headers=h,
        )
        assert r.status_code == 201, r.text
        tb_id = r.json()["id"]

        # 提交猜词（拆分是纯函数无 LLM；配对打桩返回空，但仍会触发 LLM 调用并落追踪）
        g = client.post(
            f"/api/admin/test/battles/{tb_id}/guess",
            json={"text": "能点燃一切"},
            headers=h,
        )
        assert g.status_code == 200, g.text

        # 追踪落库是异步任务，轮询等待本场 guess_pair 记录出现
        con = _sqlite()
        n = _wait_for_trace_count(con, 1, kind="test_guess", trace_id=str(tb_id))
        con.close()
        assert n >= 1, "应至少有一条 llm_traces 记录"

        # 管理端列表可见（带环节/场景过滤）
        lst = client.get(f"/api/admin/llm-traces?kind=test_guess&trace_id={tb_id}", headers=h).json()
        ops = {t["operation"] for t in lst}
        assert "guess_pair" in ops, f"应含 guess_pair，实际 {ops}"
        assert all(t["kind"] == "test_guess" and t["trace_id"] == str(tb_id) for t in lst)

        # 详情含请求输入
        detail = client.get(f"/api/admin/llm-traces/{lst[0]['id']}", headers=h).json()
        assert detail["request_json"] is not None
        assert detail["status"] in ("ok", "fail")

        # 统计聚合可用
        stats = client.get("/api/admin/llm-traces/stats", headers=h).json()
        assert stats["total"] >= 1
        assert any(op["operation"] == "guess_pair" for op in stats["by_operation"])

        # 清掉测试行迹（trace 保留，不清理测试方便复盘）
        client.delete(f"/api/admin/test/battles/{tb_id}", headers=h)


def test_llm_trace_forbidden_for_non_admin():
    """追踪仅管理员可见。"""
    with TestClient(app) as client:
        _, _, h = _new_user(client)
        assert client.get("/api/admin/llm-traces", headers=h).status_code == 403
        assert client.get("/api/admin/llm-traces/stats", headers=h).status_code == 403
