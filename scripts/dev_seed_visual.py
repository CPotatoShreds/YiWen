"""开发环境视觉核验种子（一次性开发工具）：创建可登录的一套数据。

产出：一个玩家账号（可登录）+ 一套「卷/阵容/进行中挑战」+ 两条已终局的挑战记录（胜/负），
用于在对战页与记录阅读页做视觉核验。仅用于本地开发库，勿在生产执行。

用法：
  1) 后端跑在 8102（uv run uvicorn app.main:app --port 8102）
  2) uv run python scripts/dev_seed_visual.py
  3) 按输出的账号密码登录 http://localhost:5174，访问输出的 battle/records 链接
"""

import asyncio
import json
import random
import string
import subprocess
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx

A = "http://localhost:8102/api"
PG_CONTAINER = "ynfight-postgres"
PASSWORD = "visual123"


def _suffix() -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=5))


def _must(r: httpx.Response, what: str) -> dict:
    assert r.status_code < 300, f"{what} 失败 {r.status_code} {r.text[:300]}"
    return r.json() if r.content else {}


def _register(client: httpx.Client, username: str) -> dict:
    r = client.post(f"{A}/auth/register", json={"username": username, "email": f"{username}@test.dev", "password": PASSWORD})
    assert r.status_code == 201, r.text
    return r.json()


def _promote(username: str) -> None:
    subprocess.run(
        ["docker", "exec", PG_CONTAINER, "psql", "-U", "ynfight", "-d", "ynfight", "-tAc",
         f"UPDATE users SET role = 'admin' WHERE username = '{username}'"],
        check=True, capture_output=True,
    )


def _character(client: httpx.Client, name: str) -> str:
    ability = _must(client.post(f"{A}/creator/abilities", json={"name": f"术{name}", "effect": "留下可观察的痕迹", "detail": ""}), "创建奇术")
    character = _must(client.post(f"{A}/creator/characters", json={"name": name, "bio": "沉静寡言", "ability_ids": [ability["id"]]}), "创建奇人")
    return character["id"]


async def _seed_finished_runs(roster_id: UUID, challenger_id: int) -> None:
    """插入两条终局回合（胜/负），供记录阅读页展示。"""
    from sqlalchemy import select

    from app.db.base import async_session_factory
    from app.models.scenario_domain import ScenarioChallengeRun, ScenarioRosterProgress

    now = datetime.now(UTC).replace(tzinfo=None)
    async with async_session_factory() as db:
        progress = await db.get(ScenarioRosterProgress, {"roster_id": roster_id, "challenger_id": challenger_id})
        won_turn = {
            "role": "views",
            "challenger_text": "她压低身形沿墙根绕行，在铜铃将响未响的一线之间穿过回廊，指尖先一步触到封印正中的符眼。守方察觉时，符纸已揭。",
            "guardian_text": "守方先以铃声诱敌，再收拢绳索，却没料到对手根本不曾踏进正廊——只留下一枚移位的蒲团与半开的窗。",
            "omniscient": "挑战者看穿了'铃阵即防线'的预设：铃声只覆盖正廊，西侧回廊因盲区而无警戒。她在三息之间完成绕行与揭符；守方的追击路线被自己布下的铃声信息拖慢半拍，胜负在这一拍之间落定。",
            "achieved": True,
            "reason": "挑战者达成公开目标；全程未违反卷内最高优先级规则。",
            "created_at": (now - timedelta(hours=3)).isoformat(),
        }
        lost_turn = {
            "role": "views",
            "challenger_text": "他选择正面夺门。第一道门闩比预想的沉，第二道门闩上缠了细线。他扯断细线的瞬间，堂内灯火齐灭。",
            "guardian_text": "守方不急于出手，只让灯焰在对方掌风里退到廊柱之后，然后收网。",
            "omniscient": "挑战者的强攻路线把主动权交给了守方预设的机关：门闩与细线本为一体，扯线即触发熄灯与落锁。挑战者在最需要视野的一瞬失去视野，未能抵达目标。",
            "achieved": False,
            "reason": "挑战者未达成公开目标；其行动触发守方预设机关后未再组织有效逼近。",
            "created_at": (now - timedelta(hours=1)).isoformat(),
        }
        rows = (await db.execute(
            select(ScenarioChallengeRun).where(ScenarioChallengeRun.roster_id == roster_id).order_by(ScenarioChallengeRun.created_at)
        )).scalars().all()
        template = rows[-1]
        roster_snapshot = template.roster_snapshot
        scenario_snapshot = template.scenario_snapshot
        challenger_snapshot = template.challenger_snapshot
        for number, (turn, won) in enumerate([(won_turn, True), (lost_turn, False)], start=2):
            db.add(ScenarioChallengeRun(
                roster_id=roster_id, challenger_id=challenger_id, status="won" if won else "lost",
                challenge_number=number, won=won,
                scenario_snapshot=scenario_snapshot, roster_snapshot=roster_snapshot, challenger_snapshot=challenger_snapshot,
                messages=[
                    {"role": "challenger", "text": "从侧翼潜行接近" if won else "正面夺门", "created_at": (now - timedelta(hours=4)).isoformat()},
                    turn,
                ],
                derived={"achieved": won, "reason": turn["reason"]},
                finished_at=now, created_at=now - timedelta(hours=4 if won else 2),
            ))
        if progress is not None:
            progress.attempts = max(progress.attempts, 3)
        await db.commit()


def main() -> int:
    suffix = _suffix()
    owner_name = f"visowner_{suffix}"
    player_name = f"visplayer_{suffix}"

    with httpx.Client(base_url=A, timeout=20) as owner, httpx.Client(base_url=A, timeout=20) as player:
        owner_row = _register(owner, owner_name)
        _promote(owner_name)
        _must(owner.post(f"{A}/auth/login", json={"username": owner_name, "password": PASSWORD}), "管理员登录")
        scenario = _must(owner.post(f"{A}/admin/scenarios", json={
            "name": f"封喉卷{suffix[:3]}", "subtitle": "见招拆招，一剑封喉", "introduction": "回廊与铃阵",
            "background": "子夜的旧驿馆，檐下铜铃成阵，封印在堂心。",
            "rules": ["不得离开驿馆范围"], "victory_condition": "让对方死亡或失去战斗能力",
            "judgement_rules": ["同时失去能力判负"],
        }), "创建卷")
        _must(owner.post(f"{A}/admin/scenarios/{scenario['id']}/publish"), "发布卷")
        owner_character = _character(owner, f"守铃{suffix[:3]}")
        roster = _must(owner.post(f"{A}/creator/scenarios/{scenario['id']}/rosters", json={
            "character_id": owner_character, "guidance": "以铃声控场，收拢退路",
        }), "创建阵容")

        player_row = _register(player, player_name)
        _must(player.post(f"{A}/auth/login", json={"username": player_name, "password": PASSWORD}), "玩家登录")
        player_character = _character(player, f"夜行{suffix[:3]}")
        challenge = _must(player.post(f"{A}/scenario-rosters/{roster['id']}/challenges", json={
            "character_id": player_character,
        }), "创建挑战")

        asyncio.run(_seed_finished_runs(UUID(roster["id"]), player_row["id"]))

    base = f"http://localhost:5174/scenarios/{scenario['slug']}/rosters/{roster['id']}"
    print(json.dumps({
        "login_user": player_name,
        "login_password": PASSWORD,
        "owner_user": owner_name,
        "battle_url": f"{base}/battle",
        "records_url": f"{base}/records",
        "challenge_id": challenge["id"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())