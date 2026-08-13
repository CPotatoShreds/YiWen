"""对战系统测试：自定义异能 → 异步推演管道（一次性上帝视角→固定结尾判胜负→并发双视角转写）→ 猜底牌 / 保密揭示。"""

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.nodes.guess_matcher import PairMatch, Verification
from app.services.nodes.usage_judge import UsedAbilities

GOD = "上帝视角：甲以影刃潜行逼近，先手斩落乙。"
NAR_A = "A 视角叙述：甲循着阴影逼近，一刀斩落乙。"
NAR_B = "B 视角叙述：乙措手不及，被一击击倒。"


def _deduce(text):
    """mock _build_deduce_llm：返回一段上帝视角叙述（纯文本）。

    文本末尾需含结果行「…胜者：{用户名}」或「…平局」，供 _parse_winner 正则路径解析胜负。
    """
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=text)
    return llm


def _transcribe(nar_a: str, nar_b: str, delay: float = 0):
    """mock _build_transcribe_chain：返回 A/B 两视角叙述（角色第一人称讲述，无系统固定首尾）。

    delay>0 时转写前 sleep（模拟转写慢于推演）。
    """
    chain = MagicMock()

    async def _ainvoke(kwargs):
        if delay:
            await asyncio.sleep(delay)
        return {"narration_a": nar_a, "narration_b": nar_b}

    chain.ainvoke = AsyncMock(side_effect=_ainvoke)
    return chain


def _guess_pipeline(pair_fn, verify_guessed):
    """mock 猜词配对/检定两环节：返回 (pair_chain, verify_chain)。

    pair 收到的是 format_messages 生成的 messages 列表，side_effect 拼接全部消息文本后交给
    pair_fn 分派（含奇术真名，用于按目标卡判定）；verify 固定返回给定检定结果。
    拆分环节为纯函数 split_atomic_guesses，无需打桩。
    """
    pair_chain = MagicMock()

    async def _pair_ainvoke(kwargs):
        text = "\n".join(m.content for m in kwargs)
        return pair_fn(text)

    pair_chain.ainvoke = AsyncMock(side_effect=_pair_ainvoke)
    verify_chain = MagicMock()
    verify_chain.ainvoke = AsyncMock(return_value=Verification(guessed=verify_guessed, reason="检定"))
    return pair_chain, verify_chain


def _usage_chain(indices: list[int]):
    """mock _build_usage_llm 的返回链：ainvoke 返回指定使用子集编号。"""
    chain = MagicMock()
    chain.ainvoke = AsyncMock(return_value=UsedAbilities(indices=indices))
    return chain


def _mk_user(client, prefix="testbat") -> str:
    uname = f"{prefix}_" + uuid4().hex[:8]
    client.post("/api/auth/register", json={"username": uname, "password": "secret123"})
    return client.post("/api/auth/login", json={"username": uname, "password": "secret123"}).json()["access_token"]


def _give_ability(client, tok, name, effect):
    r = client.post("/api/abilities", json={"name": name, "effect": effect}, headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 201


def _arm_named(client, tok, name):
    """新建一位带名奇人 + 装全部异能 + 解封（参与匹配需已解封且装奇术）。"""
    h = {"Authorization": f"Bearer {tok}"}
    ld = client.post("/api/loadouts", json={"name": name}, headers=h).json()
    for a in client.get("/api/abilities/mine", headers=h).json():
        client.post(f"/api/loadouts/{ld['id']}/abilities/{a['id']}", headers=h)
    assert client.put(f"/api/loadouts/{ld['id']}", json={"enabled": True}, headers=h).status_code == 200
    return ld


def _arm(client, tok):
    """立起一位出战奇人（名 = 异闻师用户名）+ 装全部异能 + 解封。

    注册不赠送默认奇人，新建须命名；奇人名 = 用户名，deduce 文本以「胜者：{用户名}」收尾即可
    解析（双方用户名唯一，不触发同名区分）。
    """
    h = {"Authorization": f"Bearer {tok}"}
    uname = client.get("/api/auth/me", headers=h).json()["username"]
    return _arm_named(client, tok, uname)


def _wait_understanding(client, headers, timeout=5):
    """等待异能理解后台生成落库（conftest 已打桩，瞬时完成）。"""
    for _ in range(int(timeout / 0.1)):
        mine = client.get("/api/abilities/mine", headers=headers).json()
        if mine and all(a["understanding"] for a in mine):
            return
        time.sleep(0.1)


def _wait_done(client, battle_id, headers, timeout=12):
    """轮询战报直到非 pending。"""
    b = None
    for _ in range(int(timeout / 0.2)):
        b = client.get(f"/api/battles/{battle_id}", headers=headers).json()
        if b["status"] != "pending":
            return b
        time.sleep(0.2)
    return b


def _wait_guess(client, battle_id, headers, attempts_before, timeout=12):
    """轮询战报直到后台猜词任务落库（猜测次数推进）。

    猜词 POST 只同步受理（202），LLM 判定在后台任务跑——须在此轮询等待（在 pair/verify
    打桩作用域内），任务落库后读到的才是完整结算结果。
    """
    b = None
    for _ in range(int(timeout / 0.2)):
        b = client.get(f"/api/battles/{battle_id}", headers=headers).json()
        if b["guess_attempts_used"] > attempts_before:
            return b
        time.sleep(0.2)
    return b


def _read_sse(client, url, headers, timeout=12):
    """读取 SSE 流直到 done/error 或超时，返回事件列表（字节级按 \\n\\n 切帧，兼容任意分块边界）。"""
    events = []
    with client.stream("GET", url, headers=headers) as r:
        assert r.status_code == 200
        buf = b""
        deadline = time.time() + timeout
        for chunk in r.iter_bytes():
            buf += chunk
            while b"\n\n" in buf:
                frame, buf = buf.split(b"\n\n", 1)
                event = "message"
                data = ""
                for fl in frame.decode("utf-8").split("\n"):
                    if fl.startswith("event:"):
                        event = fl[6:].strip()
                    elif fl.startswith("data:"):
                        data += fl[5:].strip()
                if data:
                    events.append({"type": event, **json.loads(data)})
            if any(e["type"] in ("done", "error") for e in events) or time.time() > deadline:
                break
    return events


def test_battle_flow_and_guess_miss():
    with TestClient(app) as client:
        tok_a = _mk_user(client)
        tok_b = _mk_user(client)
        h_a = {"Authorization": f"Bearer {tok_a}"}
        h_b = {"Authorization": f"Bearer {tok_b}"}
        name_b = client.get("/api/auth/me", headers=h_b).json()["username"]
        _give_ability(client, tok_a, "影刃", "以暗影凝聚利刃斩杀敌人")
        _give_ability(client, tok_b, "血咒", "以自身鲜血为引发动诅咒，反噬攻击者")
        _arm(client, tok_a)
        _arm(client, tok_b)
        _wait_understanding(client, h_a)

        user_b_id = client.get("/api/auth/me", headers=h_b).json()["id"]
        with (
            patch("app.services.battle._build_deduce_llm", return_value=_deduce(f"{GOD} 胜者：{name_b}")),
            patch("app.services.battle._build_transcribe_chain", return_value=_transcribe(NAR_A, NAR_B)),
            patch("app.services.battle.pick_opponent", new=AsyncMock(return_value=user_b_id)),
            patch("app.services.battle.GUESS_ATTEMPTS_MAX", 1),  # 单次机会：一次未看破即耗尽
        ):
            r = client.post("/api/battles", headers=h_a)
            assert r.status_code == 200
            assert r.json()["status"] == "pending"  # 立即返回，异步推演
            b = _wait_done(client, r.json()["id"], h_a)

        assert b["status"] == "done"
        assert b["winner"] == name_b  # B 胜，A 败
        assert b["can_guess"] is True  # A 是输家，可猜奇术
        # 叙述各看各的 + 上帝视角恒不展示：A 只见自己的视角叙述（转写正文，无系统固定首尾）
        assert b["story"]["narration_a"] == NAR_A
        assert "narration_b" not in b["story"]
        assert "narration" not in b["story"]  # 上帝视角存储但不展示
        # 揭示前：对手（B）异能表与解读隐藏，自己（A）的可见
        assert b["story"]["abilities_a"]
        assert b["story"]["insight_a"]  # 解读来自已存的 AI 异能理解
        assert "abilities_b" not in b["story"]
        assert "insight_b" not in b["story"]
        # 空白卡片：使用子集=全部装配（conftest 桩空子集 → 降级全用），B 一门 → 1 张未看破卡
        assert b["guess_total"] == 1
        assert b["guess_cards"] and b["guess_cards"][0]["cracked"] is False
        assert b["guess_cards"][0]["name"] is None  # 未看破不揭示真实奇术

        # 结算：见闻 签到10 + 对战5 + 首次5 = 20
        me_a = client.get("/api/auth/me", headers=h_a).json()
        me_b = client.get("/api/auth/me", headers=h_b).json()
        assert me_a["exp"] == 20 and me_b["exp"] == 20
        assert me_a["rank_points"] == 984 and me_b["rank_points"] == 1016

        # A 猜一次（配对判定无价值、检定未猜出）→ 机会耗尽，B 显式开启 reveal_on_miss，结束后揭示
        assert client.put("/api/auth/settings", json={"reveal_on_miss": True}, headers=h_b).status_code == 200
        pair, verify = _guess_pipeline(lambda kw: PairMatch(snippet=""), False)
        with (
            patch("app.services.battle._build_pair_llm", return_value=pair),
            patch("app.services.battle._build_verify_llm", return_value=verify),
        ):
            g = client.post(f"/api/battles/{b['id']}/guess", json={"text": "控制重力"}, headers=h_a)
            assert g.status_code == 202  # 只受理：LLM 判定在后台任务，轮询等落库
            gb = _wait_guess(client, b["id"], h_a, attempts_before=0)
        assert gb["guessed"] is True and gb["guess_hit"] is False
        assert gb["guess_score"] == 0.0
        assert gb["revealed"] is True  # 默认揭示
        assert gb["can_guess"] is False
        assert gb["story"]["abilities_b"]  # 已揭示
        assert gb["winner"] == name_b  # 未翻转

        # 猜词已结束 → 400
        g2 = client.post(f"/api/battles/{b['id']}/guess", json={"text": "再猜一次"}, headers=h_a)
        assert g2.status_code == 400


def test_guess_hit_flips_winner_and_rank():
    with TestClient(app) as client:
        tok_a = _mk_user(client, "testflip")
        tok_b = _mk_user(client, "testflip")
        h_a = {"Authorization": f"Bearer {tok_a}"}
        h_b = {"Authorization": f"Bearer {tok_b}"}
        name_a = client.get("/api/auth/me", headers=h_a).json()["username"]
        name_b = client.get("/api/auth/me", headers=h_b).json()["username"]
        _give_ability(client, tok_a, "雷暴召来", "召唤雷霆轰击对手")
        _give_ability(client, tok_b, "镜面反射", "将对手的攻击原样反射回去")
        _arm(client, tok_a)
        _arm(client, tok_b)
        _wait_understanding(client, h_a)

        user_b_id = client.get("/api/auth/me", headers=h_b).json()["id"]
        with (
            patch("app.services.battle._build_deduce_llm", return_value=_deduce(f"{GOD} 胜者：{name_a}")),
            patch("app.services.battle._build_transcribe_chain", return_value=_transcribe(NAR_A, NAR_B)),
            patch("app.services.battle.pick_opponent", new=AsyncMock(return_value=user_b_id)),
        ):
            r = client.post("/api/battles", headers=h_a)
            b = _wait_done(client, r.json()["id"], h_b)  # 以 B（输家）视角轮询

        assert b["winner"] == name_a  # 初始 A 胜
        assert b["can_guess"] is True  # B 是输家
        assert NAR_B in b["story"]["narration_b"]  # B 只见自己的视角
        assert "narration_a" not in b["story"]

        # B 一次道出命中全部奇术（配对有价值 + 检定猜出）→ 全破逆转，名望回滚重算
        pair, verify = _guess_pipeline(lambda kw: PairMatch(snippet="召唤雷霆轰击对手"), True)
        with (
            patch("app.services.battle._build_pair_llm", return_value=pair),
            patch("app.services.battle._build_verify_llm", return_value=verify),
        ):
            g = client.post(f"/api/battles/{b['id']}/guess", json={"text": "掌控雷电轰击目标"}, headers=h_b)
            assert g.status_code == 202
            gb = _wait_guess(client, b["id"], h_b, attempts_before=0)
        assert gb["guess_hit"] is True
        assert gb["guess_score"] == 1.0
        assert gb["guessed"] is True
        assert gb["revealed"] is True
        assert gb["winner"] == name_b  # 翻转
        assert gb["guess_cards"][0]["cracked"] is True
        assert gb["guess_cards"][0]["name"] == "雷暴召来"  # 看破揭示真实奇术
        # 名望：分段结算——对战 A +16/B -16，全破后回滚重算为 A -16 / B +16
        assert gb["rank_delta_a"] == -16 and gb["rank_delta_b"] == 16
        me_a = client.get("/api/auth/me", headers=h_a).json()
        me_b = client.get("/api/auth/me", headers=h_b).json()
        assert me_a["rank_points"] == 984 and me_b["rank_points"] == 1016


def test_reveal_on_miss_toggle_hides_ability():
    """胜者关闭 reveal_on_miss：败方猜词结束未全破后，对手异能继续保密。"""
    with TestClient(app) as client:
        tok_a = _mk_user(client, "testhide")
        tok_b = _mk_user(client, "testhide")
        h_a = {"Authorization": f"Bearer {tok_a}"}
        h_b = {"Authorization": f"Bearer {tok_b}"}
        _give_ability(client, tok_a, "燃烬之握", "点燃接触物")
        _give_ability(client, tok_b, "霜语", "冻结空气中的水分")
        _arm(client, tok_a)
        _arm(client, tok_b)
        # B（胜者）关闭揭示
        assert client.put("/api/auth/settings", json={"reveal_on_miss": False}, headers=h_b).status_code == 200

        user_b = client.get("/api/auth/me", headers=h_b).json()
        user_b_id, name_b = user_b["id"], user_b["username"]
        with (
            patch("app.services.battle._build_deduce_llm", return_value=_deduce(f"{GOD} 胜者：{name_b}")),
            patch("app.services.battle._build_transcribe_chain", return_value=_transcribe(NAR_A, NAR_B)),
            patch("app.services.battle.pick_opponent", new=AsyncMock(return_value=user_b_id)),
            patch("app.services.battle.GUESS_ATTEMPTS_MAX", 1),  # 单次机会：一次未看破即耗尽
        ):
            r = client.post("/api/battles", headers=h_a)
            b = _wait_done(client, r.json()["id"], h_a)

        pair, verify = _guess_pipeline(lambda kw: PairMatch(snippet=""), False)
        with (
            patch("app.services.battle._build_pair_llm", return_value=pair),
            patch("app.services.battle._build_verify_llm", return_value=verify),
        ):
            g = client.post(f"/api/battles/{b['id']}/guess", json={"text": "不猜了"}, headers=h_a)
            assert g.status_code == 202
            gb = _wait_guess(client, b["id"], h_a, attempts_before=0)
        assert gb["guess_hit"] is False
        assert gb["guess_score"] == 0.0
        assert gb["revealed"] is False  # 保密未揭示
        assert "abilities_b" not in gb["story"]  # 对手异能仍隐藏


def test_battle_draw_from_ending():
    """推演结尾句为「平局」→ 和局：无输家、双方皆可猜奇术、名望不变、推演只调 1 次。"""
    with TestClient(app) as client:
        tok_a = _mk_user(client, "testdraw")
        tok_b = _mk_user(client, "testdraw")
        h_a = {"Authorization": f"Bearer {tok_a}"}
        h_b = {"Authorization": f"Bearer {tok_b}"}
        _give_ability(client, tok_a, "影刃", "以暗影凝聚利刃斩杀敌人")
        _give_ability(client, tok_b, "血咒", "以自身鲜血为引发动诅咒")
        _arm(client, tok_a)
        _arm(client, tok_b)

        user_b_id = client.get("/api/auth/me", headers=h_b).json()["id"]
        deduce = _deduce("双方僵持周旋，谁也没有彻底失去作战能力。平局")
        with (
            patch("app.services.battle._build_deduce_llm", return_value=deduce),
            patch("app.services.battle._build_transcribe_chain", return_value=_transcribe(NAR_A, NAR_B)),
            patch("app.services.battle.pick_opponent", new=AsyncMock(return_value=user_b_id)),
        ):
            r = client.post("/api/battles", headers=h_a)
            b = _wait_done(client, r.json()["id"], h_a)

        assert b["status"] == "done"
        assert b["winner"] is None
        assert b["story"]["result"] == "和局"
        assert b["guess_by"] is None  # 和局无输家：双方皆可猜
        assert b["can_guess"] is True  # 和局双方解锁猜奇术
        assert b["my_guess"] is not None and b["my_guess"]["total"] == 1  # 我方猜对方实际用过的 1 门奇术
        assert b["rank_delta_a"] == 0 and b["rank_delta_b"] == 0  # 和局 a_score=0.5 → Elo 不变
        assert deduce.ainvoke.call_count == 1  # 一次性推演：结尾句即定胜负


def test_winner_from_ending():
    """推演结尾句声明 B 胜 → winner 为 B，推演只调 1 次（无轮数概念）。"""
    with TestClient(app) as client:
        tok_a = _mk_user(client, "test3rd")
        tok_b = _mk_user(client, "test3rd")
        h_a = {"Authorization": f"Bearer {tok_a}"}
        h_b = {"Authorization": f"Bearer {tok_b}"}
        name_b = client.get("/api/auth/me", headers=h_b).json()["username"]
        _give_ability(client, tok_a, "影刃", "以暗影凝聚利刃斩杀敌人")
        _give_ability(client, tok_b, "血咒", "以自身鲜血为引发动诅咒")
        _arm(client, tok_a)
        _arm(client, tok_b)

        user_b_id = client.get("/api/auth/me", headers=h_b).json()["id"]
        deduce = _deduce(f"战局推进……乙彻底击倒甲。胜者：{name_b}")
        with (
            patch("app.services.battle._build_deduce_llm", return_value=deduce),
            patch("app.services.battle._build_transcribe_chain", return_value=_transcribe(NAR_A, NAR_B)),
            patch("app.services.battle.pick_opponent", new=AsyncMock(return_value=user_b_id)),
        ):
            r = client.post("/api/battles", headers=h_a)
            b = _wait_done(client, r.json()["id"], h_a)

        assert b["winner"] == name_b
        assert deduce.ainvoke.call_count == 1  # 一次性推演，结尾句即定胜负


def test_share_shows_share_side_perspective():
    """分享按侧：A 的分享链接是 A 视角，B 的分享链接是 B 视角；上帝视角恒不在分享响应。"""
    with TestClient(app) as client:
        tok_a = _mk_user(client, "testshr")
        tok_b = _mk_user(client, "testshr")
        h_a = {"Authorization": f"Bearer {tok_a}"}
        h_b = {"Authorization": f"Bearer {tok_b}"}
        _give_ability(client, tok_a, "影刃", "以暗影凝聚利刃斩杀敌人")
        _give_ability(client, tok_b, "镜面反射", "将对手的攻击原样反射回去")
        _arm(client, tok_a)
        _arm(client, tok_b)

        user_a = client.get("/api/auth/me", headers=h_a).json()
        user_b = client.get("/api/auth/me", headers=h_b).json()
        user_b_id, name_a = user_b["id"], user_a["username"]
        with (
            patch("app.services.battle._build_deduce_llm", return_value=_deduce(f"{GOD} 胜者：{name_a}")),
            patch("app.services.battle._build_transcribe_chain", return_value=_transcribe(NAR_A, NAR_B)),
            patch("app.services.battle.pick_opponent", new=AsyncMock(return_value=user_b_id)),
        ):
            r = client.post("/api/battles", headers=h_a)
            b = _wait_done(client, r.json()["id"], h_a)
        assert b["share_token"] and b["share_token_b"]

        # A 的分享 → A 视角
        sa = client.get(f"/api/battles/share/{b['share_token']}")
        assert sa.status_code == 200
        sja = sa.json()["story"]
        assert NAR_A in sja["narration_a"]
        assert "narration_b" not in sja
        assert "narration" not in sja  # 上帝视角不展示
        assert sja["abilities_a"] and "abilities_b" not in sja  # 揭示前 B 异能保密

        # B 的分享 → B 视角
        sb = client.get(f"/api/battles/share/{b['share_token_b']}")
        assert sb.status_code == 200
        sjb = sb.json()["story"]
        assert NAR_B in sjb["narration_b"]
        assert "narration_a" not in sjb
        assert "narration" not in sjb
        assert sjb["abilities_b"] and "abilities_a" not in sjb


def test_battle_without_ability():
    with TestClient(app) as client:
        tok = _mk_user(client)
        # 无异能者无法参战 → 400
        r = client.post("/api/battles", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 400


def _mk_battle(client, tok_a, tok_b, h_a, h_b, deduce=None):
    """组装一局对战所需的异能/装配/等待理解。

    deduce 文本需以「胜者：X / 平局」结尾供结果解析；缺省为「GOD 胜者：{name_a}」（默认 A 胜）。
    返回 (deduce_mock, user_b_id)。
    """
    _give_ability(client, tok_a, "影刃", "以暗影凝聚利刃斩杀敌人")
    _give_ability(client, tok_b, "血咒", "以自身鲜血为引发动诅咒")
    _arm(client, tok_a)
    _arm(client, tok_b)
    _wait_understanding(client, h_a)
    name_a = client.get("/api/auth/me", headers=h_a).json()["username"]
    user_b_id = client.get("/api/auth/me", headers=h_b).json()["id"]
    deduce_llm = _deduce(deduce if deduce is not None else f"{GOD} 胜者：{name_a}")
    return deduce_llm, user_b_id


def test_battle_stream_emits_ordered_segments():
    """推演中订阅 SSE：收到自己视角的单段叙述（A 见 narration_a）→ done；B 订阅见 narration_b；上帝叙述永不上流。"""
    with TestClient(app) as client:
        tok_a = _mk_user(client, "testse1")
        tok_b = _mk_user(client, "testse1")
        h_a = {"Authorization": f"Bearer {tok_a}"}
        h_b = {"Authorization": f"Bearer {tok_b}"}
        deduce_llm, user_b_id = _mk_battle(client, tok_a, tok_b, h_a, h_b)
        transcribe_llm = _transcribe(NAR_A, NAR_B, delay=0.3)  # 转写慢于推演，留出订阅窗口
        with (
            patch("app.services.battle._build_deduce_llm", return_value=deduce_llm),
            patch("app.services.battle._build_transcribe_chain", return_value=transcribe_llm),
            patch("app.services.battle.pick_opponent", new=AsyncMock(return_value=user_b_id)),
        ):
            r = client.post("/api/battles", headers=h_a)
            battle_id = r.json()["id"]

            ev_a = _read_sse(client, f"/api/battles/{battle_id}/stream", headers=h_a)

        # A 流：1 个 segment（round 0，自己视角，直接是转写正文无系统固定首尾）+ done；narration 为改写后的单侧字段，不残留原始键
        segs_a = [e for e in ev_a if e["type"] == "segment"]
        assert [s["round"] for s in segs_a] == [0]
        assert segs_a[0]["narration"] == NAR_A  # 含 A 视角正文而非 GOD，上帝叙述不泄露
        assert any(e["type"] == "done" for e in ev_a)
        assert not any("narration_a" in e or "narration_b" in e for e in ev_a)  # 对面视角/原始双键不出流


def test_battle_stream_filter_for_viewer_side():
    """_filter_for_viewer：segment 按观看者身份改写为单侧 narration（A 见 A 文，B 见 B 文），其余事件透传。"""
    from app.api.routes.battles import _filter_for_viewer

    ev = {"type": "segment", "round": 1, "narration_a": NAR_A, "narration_b": NAR_B}
    assert _filter_for_viewer(ev, viewer_id=1, a_id=1, b_id=2) == {"type": "segment", "round": 1, "narration": NAR_A}
    assert _filter_for_viewer(ev, viewer_id=2, a_id=1, b_id=2) == {"type": "segment", "round": 1, "narration": NAR_B}
    # 非 segment 事件原样透传；segment 但本侧无叙述时丢弃
    assert _filter_for_viewer({"type": "done", "status": "done"}, viewer_id=1, a_id=1, b_id=2) == {
        "type": "done",
        "status": "done",
    }
    assert _filter_for_viewer({"type": "segment", "round": 0}, viewer_id=2, a_id=1, b_id=2) is None


def test_battle_stream_done_battle_short_circuits():
    """已完成对战开流：立即收到单个 done 事件（不挂起）。

    和局双方各收手后猜词全结束（guess_state "done"）→ 总线已关闭，开流立即短接；
    （和局且仍可猜时流保持开放，由 test_battle_stream_delivers_guess_done 覆盖。）
    """
    with TestClient(app) as client:
        tok_a = _mk_user(client, "testsd")
        tok_b = _mk_user(client, "testsd")
        h_a = {"Authorization": f"Bearer {tok_a}"}
        h_b = {"Authorization": f"Bearer {tok_b}"}
        deduce_llm, user_b_id = _mk_battle(
            client, tok_a, tok_b, h_a, h_b, deduce="双方僵持周旋，谁也没有彻底失去作战能力。平局"
        )
        transcribe_llm = _transcribe(NAR_A, NAR_B)
        with (
            patch("app.services.battle._build_deduce_llm", return_value=deduce_llm),
            patch("app.services.battle._build_transcribe_chain", return_value=transcribe_llm),
            patch("app.services.battle.pick_opponent", new=AsyncMock(return_value=user_b_id)),
        ):
            r = client.post("/api/battles", headers=h_a)
            battle_id = r.json()["id"]
            _wait_done(client, battle_id, h_a)

            # 和局双方各收手 → 猜词全结束（guess_state "done"）
            assert client.post(f"/api/battles/{battle_id}/give-up", headers=h_a).status_code == 200
            assert client.post(f"/api/battles/{battle_id}/give-up", headers=h_b).status_code == 200

            ev = _read_sse(client, f"/api/battles/{battle_id}/stream", headers=h_a)
        assert ev == [{"type": "done", "status": "done"}]


def test_battle_stream_delivers_guess_done():
    """猜词阶段开流：后台判定完成经总线推 guess_done；机会用尽后总线关闭，流随之收尾。

    POST 只受理（202），SSE 流保持开放订阅总线；判定落库后收到 guess_done，总线关闭哨兵结束流。
    pair mock 刻意慢于流订阅，保证流先订阅上总线（否则 done 短接路径不涉及总线）。
    """
    with TestClient(app) as client:
        tok_a = _mk_user(client, "testgd")
        tok_b = _mk_user(client, "testgd")
        h_a = {"Authorization": f"Bearer {tok_a}"}
        h_b = {"Authorization": f"Bearer {tok_b}"}
        deduce_llm, user_b_id = _mk_battle(client, tok_a, tok_b, h_a, h_b)  # 默认 A 胜 → B 可猜
        transcribe_llm = _transcribe(NAR_A, NAR_B)
        with (
            patch("app.services.battle._build_deduce_llm", return_value=deduce_llm),
            patch("app.services.battle._build_transcribe_chain", return_value=transcribe_llm),
            patch("app.services.battle.pick_opponent", new=AsyncMock(return_value=user_b_id)),
            patch("app.services.battle.GUESS_ATTEMPTS_MAX", 1),  # 一次未看破即结束 → 总线关闭
        ):
            r = client.post("/api/battles", headers=h_a)
            battle_id = r.json()["id"]
            _wait_done(client, battle_id, h_a)

        pair_chain = MagicMock()

        async def _pair_ainvoke(kwargs):
            await asyncio.sleep(0.3)  # 慢于流订阅：留出 SSE 打开并订阅总线的窗口
            return PairMatch(snippet="")

        pair_chain.ainvoke = AsyncMock(side_effect=_pair_ainvoke)
        verify_chain = MagicMock()
        verify_chain.ainvoke = AsyncMock(return_value=Verification(guessed=False, reason="检定"))
        with (
            patch("app.services.battle._build_pair_llm", return_value=pair_chain),
            patch("app.services.battle._build_verify_llm", return_value=verify_chain),
        ):
            g = client.post(f"/api/battles/{battle_id}/guess", json={"text": "控制重力"}, headers=h_b)
            assert g.status_code == 202
            ev = _read_sse(client, f"/api/battles/{battle_id}/stream", headers=h_b)
        assert any(e["type"] == "guess_done" for e in ev)


def test_battle_stream_requires_participant():
    """非参战方订阅流 → 404。"""
    with TestClient(app) as client:
        tok_a = _mk_user(client, "testsp")
        tok_b = _mk_user(client, "testsp")
        tok_c = _mk_user(client, "testsp")
        h_a = {"Authorization": f"Bearer {tok_a}"}
        h_b = {"Authorization": f"Bearer {tok_b}"}
        deduce_llm, user_b_id = _mk_battle(client, tok_a, tok_b, h_a, h_b)
        transcribe_llm = _transcribe(NAR_A, NAR_B)
        with (
            patch("app.services.battle._build_deduce_llm", return_value=deduce_llm),
            patch("app.services.battle._build_transcribe_chain", return_value=transcribe_llm),
            patch("app.services.battle.pick_opponent", new=AsyncMock(return_value=user_b_id)),
        ):
            r = client.post("/api/battles", headers=h_a)
            battle_id = r.json()["id"]
            _wait_done(client, battle_id, h_a)  # 等后台任务收尾，避免遗留未提交写入

            h_c = {"Authorization": f"Bearer {tok_c}"}
            with client.stream("GET", f"/api/battles/{battle_id}/stream", headers=h_c) as resp:
                assert resp.status_code == 404


def test_battle_deduce_failure_marks_failed_with_message():
    """推演 LLM 重试耗尽（挂死/超时）→ 战斗标记 failed，story 写入面向用户的解释文本；SSE 透传同文案。"""
    with TestClient(app) as client:
        tok_a = _mk_user(client, "testfail")
        tok_b = _mk_user(client, "testfail")
        h_a = {"Authorization": f"Bearer {tok_a}"}
        h_b = {"Authorization": f"Bearer {tok_b}"}
        _give_ability(client, tok_a, "影刃", "以暗影凝聚利刃斩杀敌人")
        _give_ability(client, tok_b, "血咒", "以自身鲜血为引发动诅咒")
        _arm(client, tok_a)
        _arm(client, tok_b)
        _wait_understanding(client, h_a)

        user_b_id = client.get("/api/auth/me", headers=h_b).json()["id"]
        deduce = MagicMock()
        deduce.ainvoke = AsyncMock(side_effect=TimeoutError("LLM 请求僵死"))  # 恒失败 → 可靠性重试耗尽
        with (
            patch("app.services.battle._build_deduce_llm", return_value=deduce),
            patch("app.services.battle._build_transcribe_chain", return_value=_transcribe(NAR_A, NAR_B)),
            patch("app.services.battle.pick_opponent", new=AsyncMock(return_value=user_b_id)),
        ):
            r = client.post("/api/battles", headers=h_a)
            assert r.status_code == 200
            assert r.json()["status"] == "pending"
            # 可靠性重试 3 次（1s + 2s 指数退避）后失败，留足等待时间
            b = _wait_done(client, r.json()["id"], h_a, timeout=15)
            battle_id = r.json()["id"]

        assert b["status"] == "failed"
        assert b["story"]["error_message"] == "铺陈中途失联，行迹未能成卷，请稍后再启程。"
        assert b["can_guess"] is False

        # 已失败战斗开流 → error 事件透传同一解释文案
        ev = _read_sse(client, f"/api/battles/{battle_id}/stream", headers=h_a)
        assert ev == [{"type": "error", "message": "铺陈中途失联，行迹未能成卷，请稍后再启程。"}]


def test_guess_failure_returns_retryable_400():
    """猜词无法拆出有效原子条目 → 400 解释文本；不消耗次数、状态不变，可重试（不破坏已落定的对战）。

    拆分已改为按换行切分（纯函数）：输入只有分隔符/空白时切不出条目，走可重试文案。
    """
    with TestClient(app) as client:
        tok_a = _mk_user(client, "testgfail")
        tok_b = _mk_user(client, "testgfail")
        h_a = {"Authorization": f"Bearer {tok_a}"}
        h_b = {"Authorization": f"Bearer {tok_b}"}
        deduce_llm, user_b_id = _mk_battle(client, tok_a, tok_b, h_a, h_b)  # 默认 A 胜
        transcribe_llm = _transcribe(NAR_A, NAR_B)
        with (
            patch("app.services.battle._build_deduce_llm", return_value=deduce_llm),
            patch("app.services.battle._build_transcribe_chain", return_value=transcribe_llm),
            patch("app.services.battle.pick_opponent", new=AsyncMock(return_value=user_b_id)),
        ):
            r = client.post("/api/battles", headers=h_a)
            b = _wait_done(client, r.json()["id"], h_b)  # B 败方可猜

        # 只输入分隔符/空白 → 拆不出原子条目，400 可重试文案，且不消耗次数可重试
        g = client.post(f"/api/battles/{b['id']}/guess", json={"text": "，，，\n\n，，，"}, headers=h_b)
        assert g.status_code == 400
        assert g.json()["detail"] == "奇术判定失联，请稍后重试猜奇术。"
        # 判定失败不消耗次数、不落 done：仍可重试
        fresh = client.get(f"/api/battles/{b['id']}", headers=h_b).json()
        assert fresh["can_guess"] is True
        assert fresh["guessed"] is False
        assert fresh["guess_attempts_used"] == 0
        # 对战结果未被破坏
        assert fresh["status"] == "done"


def test_usage_subset_limits_cards():
    """使用子集节点只判一门使用 → 空白卡片只有 1 张（装配了 2 门，另一门未用不算）。"""
    with TestClient(app) as client:
        tok_a = _mk_user(client, "testsub")
        tok_b = _mk_user(client, "testsub")
        h_a = {"Authorization": f"Bearer {tok_a}"}
        h_b = {"Authorization": f"Bearer {tok_b}"}
        _give_ability(client, tok_a, "雷暴召来", "召唤雷霆轰击对手")
        _give_ability(client, tok_a, "影刃", "以暗影凝聚利刃斩杀敌人")
        _give_ability(client, tok_b, "镜面反射", "将对手的攻击原样反射回去")
        _arm(client, tok_a)
        _arm(client, tok_b)
        _wait_understanding(client, h_a)

        name_a = client.get("/api/auth/me", headers=h_a).json()["username"]
        user_b_id = client.get("/api/auth/me", headers=h_b).json()["id"]
        with (
            patch("app.services.battle._build_deduce_llm", return_value=_deduce(f"{GOD} 胜者：{name_a}")),
            patch("app.services.battle._build_transcribe_chain", return_value=_transcribe(NAR_A, NAR_B)),
            patch("app.services.battle.pick_opponent", new=AsyncMock(return_value=user_b_id)),
            patch("app.services.battle._build_usage_llm", return_value=_usage_chain([1])),  # 只用第 1 门（雷暴召来）
        ):
            r = client.post("/api/battles", headers=h_a)
            b = _wait_done(client, r.json()["id"], h_b)  # B 输家视角

        assert b["guess_total"] == 1  # 装配 2 门，只用 1 门
        assert len(b["guess_cards"]) == 1
        assert b["guess_cards"][0]["cracked"] is False

        # 看破该卡 → 揭示的正是「使用过」的那门（装配清单之一；装配顺序在 SQLite 秒级时间戳
        # 下不稳定，故只断言名字落在装配的两门之内）
        pair, verify = _guess_pipeline(lambda kw: PairMatch(snippet="召唤雷霆轰击对手"), True)
        with (
            patch("app.services.battle._build_pair_llm", return_value=pair),
            patch("app.services.battle._build_verify_llm", return_value=verify),
        ):
            g = client.post(f"/api/battles/{b['id']}/guess", json={"text": "掌控雷电轰击目标"}, headers=h_b)
            assert g.status_code == 202
            gb = _wait_guess(client, b["id"], h_b, attempts_before=0)
        assert gb["guess_cards"][0]["cracked"] is True
        assert gb["guess_cards"][0]["name"] in {"雷暴召来", "影刃"}


def test_guess_cracks_card_reveals_ability():
    """多张卡：猜中一门 → 该卡看破并揭示真实奇术，其余卡不动，猜词继续（未全破不结束）。"""
    with TestClient(app) as client:
        tok_a = _mk_user(client, "testcrack")
        tok_b = _mk_user(client, "testcrack")
        h_a = {"Authorization": f"Bearer {tok_a}"}
        h_b = {"Authorization": f"Bearer {tok_b}"}
        _give_ability(client, tok_a, "雷暴召来", "召唤雷霆轰击对手")
        _give_ability(client, tok_a, "影刃", "以暗影凝聚利刃斩杀敌人")
        _give_ability(client, tok_b, "镜面反射", "将对手的攻击原样反射回去")
        _arm(client, tok_a)
        _arm(client, tok_b)
        _wait_understanding(client, h_a)

        name_a = client.get("/api/auth/me", headers=h_a).json()["username"]
        user_b_id = client.get("/api/auth/me", headers=h_b).json()["id"]
        with (
            patch("app.services.battle._build_deduce_llm", return_value=_deduce(f"{GOD} 胜者：{name_a}")),
            patch("app.services.battle._build_transcribe_chain", return_value=_transcribe(NAR_A, NAR_B)),
            patch("app.services.battle.pick_opponent", new=AsyncMock(return_value=user_b_id)),
        ):
            r = client.post("/api/battles", headers=h_a)
            b = _wait_done(client, r.json()["id"], h_b)  # 使用子集=全部装配（conftest 桩），2 张卡

        assert b["guess_total"] == 2
        assert b["can_guess"] is True

        # 只命中「雷暴召来」→ 该卡看破揭示，另一门（影刃）不动，未全破仍在猜词中
        def pair_fn(text):
            return PairMatch(
                snippet="召唤雷霆轰击对手" if "雷暴" in text else "",
            )

        pair, verify = _guess_pipeline(pair_fn, True)
        with (
            patch("app.services.battle._build_pair_llm", return_value=pair),
            patch("app.services.battle._build_verify_llm", return_value=verify),
        ):
            g = client.post(f"/api/battles/{b['id']}/guess", json={"text": "掌控雷电轰击目标"}, headers=h_b)
            assert g.status_code == 202
            gb = _wait_guess(client, b["id"], h_b, attempts_before=0)
        assert gb["guessed"] is False  # 未全破，猜词继续
        assert gb["guess_hit"] is None
        assert gb["can_guess"] is True
        assert gb["guess_score"] == 0.5  # 1/2
        assert gb["guess_attempts_used"] == 1
        # 装配顺序在 SQLite 秒级时间戳下不稳定，故不断言具体哪门；只断言：
        # 恰好一张卡被命中看破（片段上卡 + 揭示装配清单内真实奇术），另一张原样不动
        assert sorted(c["cracked"] for c in gb["guess_cards"]) == [False, True]
        assert sorted(c["matched"] for c in gb["guess_cards"]) == [[], ["召唤雷霆轰击对手"]]
        assert {c["name"] for c in gb["guess_cards"]} == {"雷暴召来", None}


def test_winner_sees_guesser_progress():
    """赢家可同时看到败方猜词进度：卡片进度/片段/看破 + 每次猜测原文（guess_history）。

    猜词数据对双方可见（此前仅败方）；赢家借 guess_by 判断自己不是败方，拿到相同的卡片数据与
    败方逐次提交的猜测原文。
    """
    with TestClient(app) as client:
        tok_a = _mk_user(client, "testwin")
        tok_b = _mk_user(client, "testwin")
        h_a = {"Authorization": f"Bearer {tok_a}"}
        h_b = {"Authorization": f"Bearer {tok_b}"}
        name_a = client.get("/api/auth/me", headers=h_a).json()["username"]
        name_b = client.get("/api/auth/me", headers=h_b).json()["username"]
        _give_ability(client, tok_a, "雷暴召来", "召唤雷霆轰击对手")
        _give_ability(client, tok_a, "影刃", "以暗影凝聚利刃斩杀敌人")
        _give_ability(client, tok_b, "镜面反射", "将对手的攻击原样反射回去")
        _arm(client, tok_a)
        _arm(client, tok_b)
        _wait_understanding(client, h_a)

        user_b_id = client.get("/api/auth/me", headers=h_b).json()["id"]
        with (
            patch("app.services.battle._build_deduce_llm", return_value=_deduce(f"{GOD} 胜者：{name_a}")),  # A 胜 → B 是败方/猜词者
            patch("app.services.battle._build_transcribe_chain", return_value=_transcribe(NAR_A, NAR_B)),
            patch("app.services.battle.pick_opponent", new=AsyncMock(return_value=user_b_id)),
        ):
            r = client.post("/api/battles", headers=h_a)
            b = _wait_done(client, r.json()["id"], h_a)  # A（赢家）视角

        # 赢家视角：猜词数据双方可见，guess_by 指向败方
        assert b["status"] == "done"
        assert b["winner"] == name_a
        assert b["guess_by"] == name_b
        assert b["can_guess"] is False  # 赢家不能猜
        assert b["guess_total"] == 2
        assert b["guess_attempts_used"] == 0
        assert b["guess_history"] == []
        assert b["guess_cards"] and len(b["guess_cards"]) == 2
        assert all(not c["cracked"] and c["matched"] == [] for c in b["guess_cards"])
        assert b["guessed"] is False  # 尚未开始猜词，赢家面板显示「正在猜」

        # 败方猜一次（命中第 1 门，未全破）→ 赢家视角实时看到进度推进与猜测原文
        def pair_fn(text):
            return PairMatch(
                snippet="召唤雷霆轰击对手" if "雷暴" in text else "",
            )

        pair, verify = _guess_pipeline(pair_fn, True)
        with (
            patch("app.services.battle._build_pair_llm", return_value=pair),
            patch("app.services.battle._build_verify_llm", return_value=verify),
        ):
            g = client.post(f"/api/battles/{b['id']}/guess", json={"text": "掌控雷电轰击目标"}, headers=h_b)
            assert g.status_code == 202
            b2 = _wait_guess(client, b["id"], h_a, attempts_before=0)  # 赢家视角轮询到进度落库
        assert b2["guess_attempts_used"] == 1
        assert b2["guess_history"] == ["掌控雷电轰击目标"]  # 正是败方提交的原文
        assert b2["guess_score"] == 0.5  # 1/2
        assert b2["guessed"] is False  # 未全破，仍在猜词中
        # 装配顺序不稳定：恰好一张卡看破并揭示真实奇术（片段赢家也可见），另一张未破
        assert sorted(c["cracked"] for c in b2["guess_cards"]) == [False, True]
        assert sorted(c["matched"] for c in b2["guess_cards"]) == [[], ["召唤雷霆轰击对手"]]
        assert {c["name"] for c in b2["guess_cards"]} == {"雷暴召来", None}


def test_same_name_fighters_disambiguated():
    """双方奇人同名 → 推演与结算显示为「奇人名（异闻师名）」以区分。"""
    with TestClient(app) as client:
        tok_a = _mk_user(client)
        tok_b = _mk_user(client)
        h_a = {"Authorization": f"Bearer {tok_a}"}
        h_b = {"Authorization": f"Bearer {tok_b}"}
        _give_ability(client, tok_a, "影刃", "以暗影凝聚利刃斩杀敌人")
        _give_ability(client, tok_b, "血咒", "以自身鲜血为引发动诅咒")
        uname_a = client.get("/api/auth/me", headers=h_a).json()["username"]
        uname_b = client.get("/api/auth/me", headers=h_b).json()["username"]
        user_b_id = client.get("/api/auth/me", headers=h_b).json()["id"]
        # 双方奇人同名「林峰」；推演桩以复合名收尾（与 _resolve_battle 的区分规则一致）
        _arm_named(client, tok_a, "林峰")
        _arm_named(client, tok_b, "林峰")

        with (
            patch("app.services.battle._build_deduce_llm", return_value=_deduce(f"{GOD} 胜者：林峰（{uname_a}）")),
            patch("app.services.battle._build_transcribe_chain", return_value=_transcribe(NAR_A, NAR_B)),
            patch("app.services.battle.pick_opponent", new=AsyncMock(return_value=user_b_id)),
        ):
            r = client.post("/api/battles", headers=h_a)
            b = _wait_done(client, r.json()["id"], h_a)

        assert b["status"] == "done"
        assert b["fighter_a"] == f"林峰（{uname_a}）"
        assert b["fighter_b"] == f"林峰（{uname_b}）"
        assert b["winner_fighter"] == f"林峰（{uname_a}）"


async def test_unique_pending_index_rejects_duplicate():
    """并发防重（启程竞态）：同一用户第二场 pending 被部分唯一索引挡下，抛 IntegrityError。

    复现场景：start_battle 先查后插有竞态——两个并发启程请求都查不到 pending 都走到插入；
    唯一索引兜底，第二场插入被拒。此处直接验证 DB 层约束（无论应用层时序如何都不产生双 pending）。
    """
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError

    from app.db.base import async_session_factory
    from app.models.battle import Battle
    from app.models.user import User

    async with async_session_factory() as db:
        db.add(User(username="race_dup", password_hash="x"))
        await db.commit()
    async with async_session_factory() as db:
        uid = (await db.execute(select(User).where(User.username == "race_dup"))).scalar_one().id
        db.add(Battle(user_a_id=uid, user_b_id=uid, status="pending", story=""))
        await db.commit()
    with pytest.raises(IntegrityError):
        async with async_session_factory() as db:
            db.add(Battle(user_a_id=uid, user_b_id=uid, status="pending", story=""))
            await db.commit()
