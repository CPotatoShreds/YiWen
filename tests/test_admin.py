"""后台管理路由测试：权限、用户/异能 CRUD、级联删除、仪表盘、流量。

直接改库用原生 sqlite3 直连测试库（conftest 已把 DATABASE_URL 指到临时库），
避免跨事件循环操作全局 async engine 的连接池（aiosqlite 连接与创建它的 loop 关联）。
"""

import os
import sqlite3
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def _sqlite() -> sqlite3.Connection:
    """直连 pytest 临时测试库。"""
    url = os.environ["DATABASE_URL"]
    return sqlite3.connect(url.split("///", 1)[1])


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
    cur = con.execute("UPDATE users SET is_admin=1 WHERE username=?", (username,))
    assert cur.rowcount == 1, f"promote failed for {username}"
    con.commit()
    con.close()


def _insert_battle(user_a_id: int, user_b_id: int, status: str = "done") -> int:
    # 测试库由 create_all 建表：下划线列均为客户端默认（无 server_default），raw insert 必须
    # 显式提供，否则 NOT NULL 违反（live 库经迁移带 server_default，行为不同，故以 create_all 为准）。
    con = _sqlite()
    cur = con.execute(
        "INSERT INTO battles (user_a_id, user_b_id, story, status, rank_delta_a, rank_delta_b,"
        " friendly, guess_text, guess_state, revealed)"
        " VALUES (?, ?, '', ?, 0, 0, 0, '', 'none', 0)",
        (user_a_id, user_b_id, status),
    )
    con.commit()
    con.close()
    return cur.lastrowid


def _insert_battle_guess(battle_id: int) -> None:
    con = _sqlite()
    con.execute(
        "INSERT INTO battle_guesses (battle_id, used_abilities, cards, guess_history, attempts_used, attempts_max, flipped)"
        " VALUES (?, '[]', '[]', '[]', 0, 5, 0)",
        (battle_id,),
    )
    con.commit()
    con.close()


def _insert_request_log(user_id: int | None, path: str = "/api/auth/me") -> None:
    con = _sqlite()
    con.execute(
        "INSERT INTO request_logs (method, path, status_code, duration_ms, user_id) VALUES (?, ?, ?, ?, ?)",
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
        assert con.execute("SELECT 1 FROM users WHERE id=?", (new_id,)).fetchone() is None
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
        _insert_battle_guess(bid)

        # C 有几条请求日志（软引用）
        _insert_request_log(c_id)
        # 删除 C
        assert client.delete(f"/api/admin/users/{c_id}", headers=h_a).status_code == 204

        con = _sqlite()
        assert con.execute("SELECT 1 FROM users WHERE id=?", (c_id,)).fetchone() is None
        assert con.execute("SELECT 1 FROM user_abilities WHERE user_id=?", (c_id,)).fetchone() is None
        assert con.execute("SELECT 1 FROM loadouts WHERE user_id=?", (c_id,)).fetchone() is None
        assert con.execute("SELECT 1 FROM loadout_abilities WHERE loadout_id=?", (lid,)).fetchone() is None
        assert (
            con.execute("SELECT 1 FROM battles WHERE user_a_id=? OR user_b_id=?", (c_id, c_id)).fetchone() is None
        )
        assert con.execute("SELECT 1 FROM battle_guesses WHERE battle_id=?", (bid,)).fetchone() is None
        assert (
            con.execute("SELECT 1 FROM friendships WHERE user_id=? OR friend_id=?", (c_id, c_id)).fetchone() is None
        )
        # 请求日志软引用置空：不再有 user_id=c_id 的行
        assert con.execute("SELECT 1 FROM request_logs WHERE user_id=?", (c_id,)).fetchone() is None
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
        assert con.execute("SELECT 1 FROM abilities WHERE id=?", (aid,)).fetchone() is None
        assert con.execute("SELECT 1 FROM user_abilities WHERE ability_id=?", (aid,)).fetchone() is None
        con.close()


def test_battle_read_and_delete():
    with TestClient(app) as client:
        _, _, h_a = _new_user(client)
        a_name = _me_name(client, h_a)
        _, _, h_b = _new_user(client, "testbt_b")
        b_id = _user_id(client, h_b)
        _promote(a_name)

        done_id = _insert_battle(_user_id(client, h_a), b_id, "done")
        _insert_battle_guess(done_id)
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
        assert con.execute("SELECT 1 FROM battles WHERE id=?", (done_id,)).fetchone() is None
        assert con.execute("SELECT 1 FROM battle_guesses WHERE battle_id=?", (done_id,)).fetchone() is None
        assert con.execute("SELECT 1 FROM battles WHERE id=?", (pending_id,)).fetchone() is not None
        con.close()
        # 顺带清掉 pending（后台禁止删 pending，直接改库清理本测试的 raw 数据）
        con = _sqlite()
        con.execute("DELETE FROM battles WHERE id=?", (pending_id,))
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
        assert con.execute("SELECT 1 FROM loadouts WHERE id=?", (ld["id"],)).fetchone() is None
        con.close()

        # 故人列表 → 删除
        friends = [f for f in client.get("/api/admin/friendships", headers=h_a).json() if {f["user_id"], f["friend_id"]} == {a_id, b_id}]
        assert len(friends) == 1
        row = friends[0]
        assert client.delete(f"/api/admin/friendships/{row['user_id']}/{row['friend_id']}", headers=h_a).status_code == 204
        con = _sqlite()
        assert con.execute(
            "SELECT 1 FROM friendships WHERE user_id=? AND friend_id=?",
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
