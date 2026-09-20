"""双实例 SSE 事件总线验收脚本。

挑战在实例 A 创建（后台比对任务立即发布 stage:compare，LLM 是否可用不影响
本验收），观众以 SSE 连到实例 B，应能经 Redis 总线 + 回放流收到 A 发布的事件。

用法：
  1) docker compose up -d
  2) uv run uvicorn app.main:app --port 8102   # 实例 A
  3) uv run uvicorn app.main:app --port 8103   # 实例 B
  4) uv run python scripts/dual_instance_check.py

说明：脚本会用 docker exec 把本脚本注册的管理员账号提为 is_admin（仅本地开发库）。
"""

import json
import random
import string
import subprocess
import sys
import time

import httpx

A = "http://localhost:8102/api"
B = "http://localhost:8103/api"
PG_CONTAINER = "ynfight-postgres"


def _suffix() -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=6))


def _register_and_login(client: httpx.Client, username: str) -> None:
    r = client.post(f"{A}/auth/register", json={"username": username, "email": f"{username}@test.dev", "password": "check123"})
    if r.status_code not in (201, 400):  # 400=已存在（重跑）
        raise AssertionError(f"注册失败 {r.status_code} {r.text}")
    r = client.post(f"{A}/auth/login", json={"username": username, "email": f"{username}@test.dev", "password": "check123"})
    assert r.status_code == 200, f"登录失败 {r.status_code} {r.text}"


def _promote_admin(username: str) -> None:
    subprocess.run(
        ["docker", "exec", PG_CONTAINER, "psql", "-U", "ynfight", "-d", "ynfight",
         "-tAc", f"UPDATE users SET role = 'admin' WHERE username = '{username}'"],
        check=True, capture_output=True,
    )


def _must(r: httpx.Response, what: str) -> dict:
    assert r.status_code < 300, f"{what} 失败 {r.status_code} {r.text[:300]}"
    return r.json() if r.content else {}


def main() -> int:
    suffix = _suffix()
    admin_name, challenger_name = f"buschk_a_{suffix}", f"buschk_b_{suffix}"

    with httpx.Client(base_url=A, timeout=15) as admin, httpx.Client(base_url=A, timeout=15) as challenger:
        _register_and_login(admin, admin_name)
        _promote_admin(admin_name)
        ability = _must(admin.post("/creator/abilities", json={
            "name": "验界", "effect": "划定验收边界", "detail": "总线验收用奇术"}), "创建奇术")
        character = _must(admin.post("/creator/characters", json={
            "name": "验收官", "bio": "总线验收用奇人", "ability_ids": [ability["id"]]}), "创建奇人")
        scenario = _must(admin.post("/admin/scenarios", json={
            "name": f"总线验收卷{suffix[0:4]}", "subtitle": "跨实例", "introduction": "验收",
            "background": "验证事件总线跨实例投递。",
            "rules": ["收到事件即通过"], "victory_condition": "实例 B 收到实例 A 的事件",
            "judgement_rules": ["以脚本断言为准"]}), "创建卷")
        _must(admin.post(f"/admin/scenarios/{scenario['id']}/publish"), "发布卷")
        roster = _must(admin.post(f"/creator/scenarios/{scenario['id']}/rosters", json={
            "character_id": character["id"], "guidance": "守住总线"}), "创建阵容")

        _register_and_login(challenger, challenger_name)
        c_ability = _must(challenger.post("/creator/abilities", json={
            "name": "穿界", "effect": "跨越实例边界", "detail": ""}), "创建挑战者奇术")
        c_character = _must(challenger.post("/creator/characters", json={
            "name": "穿界人", "bio": "", "ability_ids": [c_ability["id"]]}), "创建挑战者奇人")

        challenge = _must(challenger.post(f"/scenario-rosters/{roster['id']}/challenges", json={
            "character_id": c_character["id"]}), "创建挑战")
        print(f"挑战已创建于实例 A：{challenge['id']}")

        # 观众侧：连实例 B 的 SSE（晚于创建也行——stage:compare 在回放流里）
        cookies = challenger.cookies
        got: list[dict] = []
        deadline = time.time() + 30
        with (
            httpx.Client(base_url=B, cookies=cookies, timeout=httpx.Timeout(35, read=35)) as viewer,
            viewer.stream("GET", f"/scenario-challenges/{challenge['id']}/stream") as resp,
        ):
            assert resp.status_code == 200, f"SSE 连接失败 {resp.status_code}"
            event_type = ""
            for line in resp.iter_lines():
                if time.time() > deadline:
                    break
                if line.startswith("event:"):
                    event_type = line[6:].strip()
                elif line.startswith("data:") and event_type not in ("", "message"):
                    data = json.loads(line[5:].strip())
                    got.append({"type": event_type, **data})
                    if data.get("type") in ("done", "error"):
                        break
                elif line == "" and got:
                    break

    types = [e["type"] for e in got]
    if not types:
        print("FAIL：实例 B 未收到任何事件")
        return 1
    print(f"PASS：实例 B 收到实例 A 的事件序列 {types}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
