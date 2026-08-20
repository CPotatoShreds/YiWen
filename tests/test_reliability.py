"""可靠性层测试：硬超时 + 指数退避重试 + 重试耗尽抛 ChainFailure；推演链路一次性调用编排 + 转写校验定稿。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.nodes.ability.pair_judge import PairVerdict
from app.services.nodes.battle.transcribe_validator import TranscribeVerdict
from app.services.llm.reliability import ChainFailure, ainvoke_with_reliability


def _pass_validate_builder():
    """转写校验打桩：恒返回合格判定（原样保留叙述）。每次调用返回全新 chain，无共享状态。"""

    def build(llm_config=None):
        chain = MagicMock()
        chain.ainvoke = AsyncMock(return_value=TranscribeVerdict(passes=True))
        return chain

    return build


def _repair_builder(text: str):
    """转写修复打桩：返回固定重写文本。"""

    def build(llm_config=None):
        chain = MagicMock()
        chain.ainvoke = AsyncMock(return_value=text)
        return chain

    return build


def _pair_judge_builder(verdict: PairVerdict):
    """能力对比节点打桩：返回固定判定。每次调用返回全新 chain，无共享状态。"""

    def build(llm_config=None):
        chain = MagicMock()
        chain.ainvoke = AsyncMock(return_value=verdict)
        return chain

    return build


def _empty_transcribe_builder():
    """转写打桩：返回空字符串 → 两侧回退上帝正文（校验短路原样保留），只测推演链路。"""

    def build(llm_config=None):
        chain = MagicMock()
        chain.ainvoke = AsyncMock(return_value="")
        return chain

    return build


def test_retry_then_success():
    """失败一次后成功：重试生效（退避 sleep 被调用），最终返回成功结果。"""
    chain = MagicMock()
    chain.ainvoke = AsyncMock(side_effect=[TimeoutError("stalled"), "ok"])
    with patch("app.services.llm.reliability.asyncio.sleep", new=AsyncMock()) as sleep:
        result = asyncio.run(ainvoke_with_reliability(chain, {"k": 1}, operation="test"))
    assert result == "ok"
    assert chain.ainvoke.await_count == 2
    sleep.assert_awaited_once()  # 仅首次失败后退避一次，第二次直接成功


def test_exhausted_raises_chain_failure():
    """恒失败：按指数退避重试到耗尽，抛 ChainFailure，携带操作名与尝试次数。"""
    chain = MagicMock()
    chain.ainvoke = AsyncMock(side_effect=TimeoutError("stalled"))
    with patch("app.services.llm.reliability.asyncio.sleep", new=AsyncMock()), pytest.raises(ChainFailure) as exc:
        asyncio.run(ainvoke_with_reliability(chain, {"k": 1}, operation="deduce"))
    assert exc.value.operation == "deduce"
    assert exc.value.attempts == 3  # 首次调用 + 2 次重试
    assert chain.ainvoke.await_count == 3


def test_run_deduction_one_shot():
    """一次性推演：deduce 输出含结尾句「胜者：血影」→ winner B；推演信息只含奇人名字（异闻师名字不进 LLM 上下文）；
    视角身份注入奇人名字；能力对比节点先于推演产出报告；校验通过保留原文；SSE 沿链路推进度
    （compare → dueling → god_chunk → recounting → narration_chunk×2 → segment(round 0)）。"""
    from app.services.battle.deduction import run_deduction

    user_a = SimpleNamespace(id=1, username="异闻师甲")
    user_b = SimpleNamespace(id=2, username="异闻师乙")

    def _ability(name, effect):
        return SimpleNamespace(name=name, effect=effect, detail="", understanding="", tactic="")

    class FakeStream:
        def __init__(self):
            self.events = []

        async def publish(self, ev, replay: bool = True):
            self.events.append(ev)

    captured = {}

    def _deduce_llm(llm_config=None):
        llm = MagicMock()

        async def _ainvoke(kwargs):
            captured["info"] = kwargs["info"]
            captured["discuss_report"] = kwargs["discuss_report"]
            return "血影以血咒反噬，青锋倒下。胜者：血影"

        llm.ainvoke = AsyncMock(side_effect=_ainvoke)
        return llm

    def _transcribe_side(llm_config=None):
        chain = MagicMock()

        async def _ainvoke(kwargs):
            captured["god"] = kwargs["god"]
            captured.setdefault("viewers", []).append(kwargs["viewer_name"])
            captured["keys"] = set(kwargs)
            return "新A" if kwargs["viewer_name"] == "青锋" else "新B"

        chain.ainvoke = AsyncMock(side_effect=_ainvoke)
        return chain

    stream = FakeStream()
    res = asyncio.run(
        run_deduction(
            stream=stream,
            user_a=user_a,
            user_b=user_b,
            fighter_a="青锋",
            fighter_b="血影",
            abilities_a=[_ability("影刃", "斩杀")],
            abilities_b=[_ability("血咒", "诅咒")],
            tactic_a="",
            tactic_b="",
            style_a="暗杀流",
            style_b="潜行流",
            build_deduce=_deduce_llm,
            build_pair_judge=_pair_judge_builder(
                PairVerdict(
                    conflict=True,
                    conflict_reason="攻击与防御直接碰撞。",
                    stronger_ability="血咒",
                    stronger_reason="以自身鲜血为代价，果相之力更大。",
                )
            ),
            build_transcribe_side=_transcribe_side,
            build_validate=_pass_validate_builder(),  # 校验恒通过 → 原样保留转写叙述
            build_repair=_repair_builder("（不应被调用）"),
        )
    )

    # 胜负从结尾句解析（regex 路径）：胜者：血影（奇人名字）→ B 胜，winner_id 为异闻师 id
    assert res.winner_side == "B"
    assert res.winner_id == 2
    assert res.result == "血影"
    # 推演信息只含奇人名字与双方风格，异闻师名字不进 LLM 上下文
    assert "青锋" in captured["info"] and "血影" in captured["info"]
    assert "战斗风格：暗杀流" in captured["info"] and "战斗风格：潜行流" in captured["info"]
    assert "异闻师甲" not in captured["info"] and "异闻师乙" not in captured["info"]
    # 能力对比报告在推演前生成，作为推演输入传入 deduce
    assert "血咒占优" in captured["discuss_report"]
    assert "冲突" in captured["discuss_report"]
    # 转写恰两侧各 1 次，拿到完整上帝全文，视角身份注入奇人名字；不再注入系统固定首尾
    assert captured["god"] == res.god
    # 上帝视角 = 模型完整输出：不再服务端前置开场白（信任模型按模板已输出开场白）
    assert res.god == "血影以血咒反噬，青锋倒下。胜者：血影"
    assert set(captured["viewers"]) == {"青锋", "血影"}
    assert "pov_opening" not in captured["keys"] and "pov_closing" not in captured["keys"]
    assert res.narration_a == "新A"
    assert res.narration_b == "新B"
    # SSE 沿链路推进度：奇术对比 → 对决中（看破者收上帝逐字流）→ 胜负已分/奇人回归 → 双视角
    # 逐字流 → 单条转写正文（round 0，双视角成对发布）
    stages = [e for e in stream.events if e["type"] != "narration_chunk"]
    assert stages == [
        {"type": "stage", "stage": "compare"},
        {"type": "stage", "stage": "dueling"},
        {"type": "god_chunk", "text": res.god},
        {"type": "stage", "stage": "recounting", "fighter_a": "青锋", "fighter_b": "血影"},
        {"type": "segment", "round": 0, "narration_a": res.narration_a, "narration_b": res.narration_b},
    ]
    chunks = [e for e in stream.events if e["type"] == "narration_chunk"]
    assert sorted(c["side"] for c in chunks) == ["a", "b"]


def test_run_deduction_transcribe_failure_degrades():
    """转写 LLM 重试耗尽（抛异常）→ 两侧降级为上帝正文兜底，战斗仍产出结果。"""
    from app.services.battle.deduction import run_deduction

    user_a = SimpleNamespace(id=1, username="异闻师甲")
    user_b = SimpleNamespace(id=2, username="异闻师乙")

    def _ability(name, effect):
        return SimpleNamespace(name=name, effect=effect, detail="", understanding="", tactic="")

    class FakeStream:
        def __init__(self):
            self.events = []

        async def publish(self, ev, replay: bool = True):
            self.events.append(ev)

    def _deduce_llm(llm_config=None):
        llm = MagicMock()
        llm.ainvoke = AsyncMock(return_value="血影以血咒反噬，青锋倒下。胜者：血影")
        return llm

    def _transcribe_side(llm_config=None):
        chain = MagicMock()
        chain.ainvoke = AsyncMock(side_effect=TimeoutError("转写僵死"))
        return chain

    with patch("app.services.llm.reliability.asyncio.sleep", new=AsyncMock()):  # 免退避等待
        res = asyncio.run(
            run_deduction(
                stream=FakeStream(),
                user_a=user_a,
                user_b=user_b,
                fighter_a="青锋",
                fighter_b="血影",
                abilities_a=[_ability("影刃", "斩杀")],
                abilities_b=[_ability("血咒", "诅咒")],
                tactic_a="",
                tactic_b="",
                build_deduce=_deduce_llm,
                build_pair_judge=_pair_judge_builder(
                    PairVerdict(
                        conflict=False,
                        conflict_reason="无直接冲突。",
                        stronger_ability="影刃",
                        stronger_reason="契相与显相综合更强。",
                    )
                ),
                build_transcribe_side=_transcribe_side,
                build_validate=_pass_validate_builder(),
                build_repair=_repair_builder("（不应被调用）"),
            )
        )

    assert res.winner_side == "B"
    assert res.result == "血影"
    assert "血影以血咒反噬，青锋倒下。" in res.narration_a
    assert res.narration_a.endswith("胜者：血影")
    assert res.narration_b == res.narration_a


def test_run_deduction_repairs_leaked_ability():
    """380 场景：上帝视角全文从未出现「影刃」的表现，转写却脱口而出对家异能名「影刃」→
    校验判不合格 → 修复重写去掉违规 → 再校验通过定稿；另一侧合格叙述原样保留。"""
    from app.services.battle.deduction import run_deduction

    user_a = SimpleNamespace(id=1, username="异闻师甲")
    user_b = SimpleNamespace(id=2, username="异闻师乙")

    def _ability(name, effect):
        return SimpleNamespace(name=name, effect=effect, detail="", understanding="", tactic="")

    class FakeStream:
        async def publish(self, ev, replay: bool = True):
            pass

    def _deduce_llm(llm_config=None):
        llm = MagicMock()
        llm.ainvoke = AsyncMock(return_value="血影以血咒反噬，青锋倒下。胜者：血影")  # 上帝视角：无影刃表现
        return llm

    def _transcribe_side(llm_config=None):
        chain = MagicMock()

        async def _ainvoke(kwargs):
            if kwargs["viewer_name"] == "青锋":
                return "青锋的合格讲述"
            return "我见他掌中凝出影刃，寒光一闪。"  # 泄露对家异能名「影刃」

        chain.ainvoke = AsyncMock(side_effect=_ainvoke)
        return chain

    repair_calls = []

    def _content_validate_builder():
        def build(llm_config=None):
            chain = MagicMock()

            async def _ainvoke(kwargs):
                if "影刃" in kwargs["narration"]:
                    return TranscribeVerdict(
                        passes=False,
                        violations=["叙述出现对家异能名「影刃」，上帝视角全文未出现其表现"],
                    )
                return TranscribeVerdict(passes=True)

            chain.ainvoke = AsyncMock(side_effect=_ainvoke)
            return chain

        return build

    def _repair_builder():
        def build(llm_config=None):
            chain = MagicMock()

            async def _ainvoke(kwargs):
                repair_calls.append(kwargs["violations"])
                return "血影的合格讲述：我只见他身形一晃，似乎从影中借力。"

            chain.ainvoke = AsyncMock(side_effect=_ainvoke)
            return chain

        return build

    res = asyncio.run(
        run_deduction(
            stream=FakeStream(),
            user_a=user_a,
            user_b=user_b,
            fighter_a="青锋",
            fighter_b="血影",
            abilities_a=[_ability("影刃", "斩杀")],
            abilities_b=[_ability("血咒", "诅咒")],
            tactic_a="",
            tactic_b="",
            build_deduce=_deduce_llm,
            build_pair_judge=_pair_judge_builder(
                PairVerdict(
                    conflict=False,
                    conflict_reason="无直接冲突。",
                    stronger_ability="影刃",
                    stronger_reason="契相与显相综合更强。",
                )
            ),
            build_transcribe_side=_transcribe_side,
            build_validate=_content_validate_builder(),
            build_repair=_repair_builder(),
        )
    )

    assert res.narration_a == "青锋的合格讲述"  # 合格 → 原样保留
    assert res.narration_b == "血影的合格讲述：我只见他身形一晃，似乎从影中借力。"  # 泄露 → 修复重写
    assert len(repair_calls) == 1  # 仅泄露侧触发一次修复
    assert "影刃" in repair_calls[0]


def test_run_deduction_validation_fail_keeps_original():
    """校验两次都判不合格（含修复后再校验）→ 该侧叙述退回原文稿件（不用上帝视角兜底，上帝第三人称不展示）。"""
    from app.services.battle.deduction import run_deduction

    user_a = SimpleNamespace(id=1, username="异闻师甲")
    user_b = SimpleNamespace(id=2, username="异闻师乙")

    def _ability(name, effect):
        return SimpleNamespace(name=name, effect=effect, detail="", understanding="", tactic="")

    class FakeStream:
        async def publish(self, ev, replay: bool = True):
            pass

    def _deduce_llm(llm_config=None):
        llm = MagicMock()
        llm.ainvoke = AsyncMock(return_value="血影以血咒反噬，青锋倒下。胜者：血影")
        return llm

    def _transcribe_side(llm_config=None):
        chain = MagicMock()

        async def _ainvoke(kwargs):
            return "A叙述" if kwargs["viewer_name"] == "青锋" else "B叙述"

        chain.ainvoke = AsyncMock(side_effect=_ainvoke)
        return chain

    def _always_fail_builder():
        def build(llm_config=None):
            chain = MagicMock()
            chain.ainvoke = AsyncMock(return_value=TranscribeVerdict(passes=False, violations=["叙述不合规"]))
            return chain

        return build

    def _repair_builder():
        def build(llm_config=None):
            chain = MagicMock()
            chain.ainvoke = AsyncMock(return_value="重写后的叙述仍不含规")
            return chain

        return build

    res = asyncio.run(
        run_deduction(
            stream=FakeStream(),
            user_a=user_a,
            user_b=user_b,
            fighter_a="青锋",
            fighter_b="血影",
            abilities_a=[_ability("影刃", "斩杀")],
            abilities_b=[_ability("血咒", "诅咒")],
            tactic_a="",
            tactic_b="",
            build_deduce=_deduce_llm,
            build_pair_judge=_pair_judge_builder(
                PairVerdict(
                    conflict=False,
                    conflict_reason="无直接冲突。",
                    stronger_ability="影刃",
                    stronger_reason="契相与显相综合更强。",
                )
            ),
            build_transcribe_side=_transcribe_side,
            build_validate=_always_fail_builder(),
            build_repair=_repair_builder(),
        )
    )

    assert res.narration_a == "A叙述"  # 修复后再校验仍不合格 → 退回原文稿件
    assert res.narration_b == "B叙述"


def test_run_pair_analysis_before_deduce():
    """能力对比节点在推演前对双方各四门奇术全量跨边配对，只接收每对奇术的信息。"""
    from app.services.battle.deduction import run_deduction

    user_a = SimpleNamespace(id=1, username="异闻师甲")
    user_b = SimpleNamespace(id=2, username="异闻师乙")

    def _ability(name, effect):
        return SimpleNamespace(name=name, effect=effect, detail="", understanding="", tactic="")

    class FakeStream:
        async def publish(self, ev, replay: bool = True):
            pass

    pair_inputs = []

    def _pair_judge_llm(llm_config=None):
        chain = MagicMock()

        async def _ainvoke(kwargs):
            pair_inputs.append(kwargs)
            return PairVerdict(
                conflict=True,
                conflict_reason="攻击与防御直接碰撞。",
                stronger_ability=kwargs["ability_a"].split("：", 1)[0].removeprefix("- "),
                stronger_reason="契相受限且显相路径完整，三相总强度占优。",
            )

        chain.ainvoke = AsyncMock(side_effect=_ainvoke)
        return chain

    captured = {}

    def _deduce_llm(llm_config=None):
        llm = MagicMock()

        async def _ainvoke(kwargs):
            captured["discuss_report"] = kwargs["discuss_report"]
            return "血影以血咒反噬，青锋倒下。胜者：血影"

        llm.ainvoke = AsyncMock(side_effect=_ainvoke)
        return llm

    asyncio.run(
        run_deduction(
            stream=FakeStream(),
            user_a=user_a,
            user_b=user_b,
            fighter_a="青锋",
            fighter_b="血影",
            abilities_a=[_ability(f"甲术{i}", f"甲方效果{i}") for i in range(1, 5)],
            abilities_b=[_ability(f"乙术{i}", f"乙方效果{i}") for i in range(1, 5)],
            tactic_a="先手突袭",
            tactic_b="潜行伏击",
            style_a="暗杀流",
            style_b="潜行流",
            build_pair_judge=_pair_judge_llm,
            build_deduce=_deduce_llm,
            build_transcribe_side=_empty_transcribe_builder(),
            build_validate=_pass_validate_builder(),
            build_repair=_repair_builder(""),
        )
    )

    # 双方各四门奇术 → 全量跨边配对恰好 16 次；每次只传当前两门奇术。
    assert len(pair_inputs) == 16
    assert all(set(kwargs) == {"ability_a", "ability_b"} for kwargs in pair_inputs)
    assert {(kwargs["ability_a"].split("：", 1)[0], kwargs["ability_b"].split("：", 1)[0]) for kwargs in pair_inputs} == {
        (f"- 甲术{i}", f"- 乙术{j}") for i in range(1, 5) for j in range(1, 5)
    }
    assert all("青锋" not in str(kwargs) and "血影" not in str(kwargs) for kwargs in pair_inputs)
    assert all("先手突袭" not in str(kwargs) and "潜行伏击" not in str(kwargs) for kwargs in pair_inputs)
    # 对比输出作为 discuss_report 传给推演 LLM
    assert "甲术1占优" in captured["discuss_report"]
    assert "冲突" in captured["discuss_report"]


def test_pair_judge_uses_discuss_theory_and_four_field_verdict():
    """比对节点完整复用讨论节点三相理论，只接收两门奇术，并以四字段决出占优者。"""
    from app.services.nodes.ability.pair_judge import (
        PAIR_JUDGE_SYSTEM_PROMPT,
        PAIR_JUDGE_USER_MSG,
        PairVerdict,
    )
    from app.services.nodes.battle.discusser import DISCUSS_SYSTEM_PROMPT

    theory_start = DISCUSS_SYSTEM_PROMPT.index("## 核心世界观公理：三相共鸣理论")
    theory_end = DISCUSS_SYSTEM_PROMPT.index("\n其他规则：")
    assert DISCUSS_SYSTEM_PROMPT[theory_start:theory_end] in PAIR_JUDGE_SYSTEM_PROMPT
    assert "{info}" not in PAIR_JUDGE_USER_MSG
    assert "{ability_a}" in PAIR_JUDGE_USER_MSG and "{ability_b}" in PAIR_JUDGE_USER_MSG
    assert set(PairVerdict.model_fields) == {
        "conflict",
        "conflict_reason",
        "stronger_ability",
        "stronger_reason",
    }


def test_pair_report_filters_non_conflicts_and_deduce_treats_it_as_authoritative():
    """下游只接收直接冲突的比对文本，推演提示将三相结论视为决定性结论。"""
    from app.services.nodes.ability.pair_judge import PairVerdict, render_pair_report
    from app.services.nodes.battle.deducer import DEDUCE_SYSTEM_PROMPT, DEDUCE_TEMPLATE
    from app.services.nodes.battle.discusser import DISCUSS_SYSTEM_PROMPT

    report = render_pair_report(
        [
            PairVerdict(
                conflict=False,
                conflict_reason="两门奇术作用方向没有直接对抗。",
                stronger_ability="静观",
                stronger_reason="显相路径更完整。",
            ),
            PairVerdict(
                conflict=True,
                conflict_reason="攻击与防御直接碰撞。",
                stronger_ability="壁障",
                stronger_reason="契相与显相总强度更高。",
            ),
        ]
    )

    assert "权威奇术比对结论" in report
    assert "壁障占优" in report
    assert "静观" not in report
    message = DEDUCE_TEMPLATE.format_messages(
        info="双方信息",
        discuss_report=report,
        opening="开场",
        ending_a="甲胜",
        ending_b="乙胜",
        ending_draw="平局",
    )[1].content
    assert "【权威奇术比对结果】" in message
    assert "不能由双方信息中的奇术原始描述推翻" in message
    assert "三相判定是决定性结论" in DEDUCE_SYSTEM_PROMPT
    theory_start = DISCUSS_SYSTEM_PROMPT.index("## 核心世界观公理：三相共鸣理论")
    theory_end = DISCUSS_SYSTEM_PROMPT.index("\n其他规则：")
    assert DISCUSS_SYSTEM_PROMPT[theory_start:theory_end] in DEDUCE_SYSTEM_PROMPT


def test_pair_analysis_failure_degrades_to_direct_deduce():
    """能力对比节点抛异常（重试耗尽）→ 降级为仅用双方信息推演，战斗不废场、结果与无对比时一致。"""
    from app.services.battle.deduction import run_deduction

    user_a = SimpleNamespace(id=1, username="异闻师甲")
    user_b = SimpleNamespace(id=2, username="异闻师乙")

    def _ability(name, effect):
        return SimpleNamespace(name=name, effect=effect, detail="", understanding="", tactic="")

    class FakeStream:
        async def publish(self, ev, replay: bool = True):
            pass

    def _pair_judge_llm(llm_config=None):
        chain = MagicMock()
        chain.ainvoke = AsyncMock(side_effect=TimeoutError("对比僵死"))
        return chain

    captured = {}

    def _deduce_llm(llm_config=None):
        llm = MagicMock()

        async def _ainvoke(kwargs):
            captured["discuss_report"] = kwargs["discuss_report"]
            return "血影以血咒反噬，青锋倒下。胜者：血影"

        llm.ainvoke = AsyncMock(side_effect=_ainvoke)
        return llm

    with patch("app.services.llm.reliability.asyncio.sleep", new=AsyncMock()):  # 免退避等待
        res = asyncio.run(
            run_deduction(
                stream=FakeStream(),
                user_a=user_a,
                user_b=user_b,
                fighter_a="青锋",
                fighter_b="血影",
                abilities_a=[_ability("影刃", "斩杀")],
                abilities_b=[_ability("血咒", "诅咒")],
                tactic_a="",
                tactic_b="",
                build_pair_judge=_pair_judge_llm,
                build_deduce=_deduce_llm,
                build_transcribe_side=_empty_transcribe_builder(),
                build_validate=_pass_validate_builder(),
                build_repair=_repair_builder(""),
            )
        )

    # 对比失败被捕获，推演照常进行并产出结果；discuss_report 为空（未污染推演输入）
    assert res.winner_side == "B"
    assert res.result == "血影"
    assert captured["discuss_report"] == ""
