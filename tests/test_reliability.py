"""可靠性层测试：硬超时 + 指数退避重试 + 重试耗尽抛 ChainFailure；推演链路一次性调用编排 + 转写校验定稿。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.nodes.transcribe_validator import TranscribeVerdict
from app.services.reliability import ChainFailure, ainvoke_with_reliability


def _pass_validate_builder():
    """转写校验打桩：恒返回合格判定（原样保留叙述）。每次调用返回全新 chain，无共享状态。"""

    def build():
        chain = MagicMock()
        chain.ainvoke = AsyncMock(return_value=TranscribeVerdict(passes=True))
        return chain

    return build


def _repair_builder(text: str):
    """转写修复打桩：返回固定重写文本。"""

    def build():
        chain = MagicMock()
        chain.ainvoke = AsyncMock(return_value=text)
        return chain

    return build


def _discuss_builder(report: str):
    """讨论节点打桩：返回固定讨论报告文本。"""

    def build():
        chain = MagicMock()
        chain.ainvoke = AsyncMock(return_value=report)
        return chain

    return build


def _empty_transcribe_builder():
    """转写打桩：返回空 dict → 两侧回退上帝正文（校验短路原样保留），只测推演链路。"""

    def build():
        chain = MagicMock()
        chain.ainvoke = AsyncMock(return_value={})
        return chain

    return build


def test_retry_then_success():
    """失败一次后成功：重试生效（退避 sleep 被调用），最终返回成功结果。"""
    chain = MagicMock()
    chain.ainvoke = AsyncMock(side_effect=[TimeoutError("stalled"), "ok"])
    with patch("app.services.reliability.asyncio.sleep", new=AsyncMock()) as sleep:
        result = asyncio.run(ainvoke_with_reliability(chain, {"k": 1}, operation="test"))
    assert result == "ok"
    assert chain.ainvoke.await_count == 2
    sleep.assert_awaited_once()  # 仅首次失败后退避一次，第二次直接成功


def test_exhausted_raises_chain_failure():
    """恒失败：按指数退避重试到耗尽，抛 ChainFailure，携带操作名与尝试次数。"""
    chain = MagicMock()
    chain.ainvoke = AsyncMock(side_effect=TimeoutError("stalled"))
    with patch("app.services.reliability.asyncio.sleep", new=AsyncMock()), pytest.raises(ChainFailure) as exc:
        asyncio.run(ainvoke_with_reliability(chain, {"k": 1}, operation="deduce"))
    assert exc.value.operation == "deduce"
    assert exc.value.attempts == 3  # 首次调用 + 2 次重试
    assert chain.ainvoke.await_count == 3


def test_run_deduction_one_shot():
    """一次性推演：deduce 输出含结尾句「胜者：血影」→ winner B；推演信息只含奇人名字（异闻师名字不进 LLM 上下文）；
    视角身份注入奇人名字；校验通过保留原文；SSE 沿链路推进度（dueling → recounting → segment(round 0)）。"""
    from app.services.deduction import run_deduction

    user_a = SimpleNamespace(id=1, username="异闻师甲")
    user_b = SimpleNamespace(id=2, username="异闻师乙")

    def _ability(name, effect):
        return SimpleNamespace(name=name, effect=effect, detail="", understanding="", tactic="")

    class FakeStream:
        def __init__(self):
            self.events = []

        async def publish(self, ev):
            self.events.append(ev)

    captured = {}

    def _deduce_llm():
        llm = MagicMock()

        async def _ainvoke(kwargs):
            captured["info"] = kwargs["info"]
            captured["opening"] = kwargs["opening"]
            captured["discuss_report"] = kwargs["discuss_report"]
            return "血影以血咒反噬，青锋倒下。胜者：血影"

        llm.ainvoke = AsyncMock(side_effect=_ainvoke)
        return llm

    def _transcribe_chain():
        chain = MagicMock()

        async def _ainvoke(kwargs):
            captured["god"] = kwargs["god"]
            captured["viewer_a"] = kwargs["viewer_name_a"]
            captured["viewer_b"] = kwargs["viewer_name_b"]
            captured["keys"] = set(kwargs)
            return {"narration_a": "新A", "narration_b": "新B"}

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
            build_discuss=_discuss_builder("金身可挡精神冲击，但若先被信息定位再偷袭则破。"),
            build_transcribe=_transcribe_chain,
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
    # 讨论报告在推演前生成，作为推演输入传入 deduce
    assert captured["discuss_report"] == "金身可挡精神冲击，但若先被信息定位再偷袭则破。"
    # 转写恰 1 次，拿到完整上帝全文（开场白 + 推演段），视角身份注入奇人名字；不再注入系统固定首尾
    assert captured["god"] == res.god
    assert res.god.startswith(captured["opening"])
    assert captured["viewer_a"] == "青锋" and captured["viewer_b"] == "血影"
    assert "pov_opening" not in captured["keys"] and "pov_closing" not in captured["keys"]
    assert res.narration_a == "新A"
    assert res.narration_b == "新B"
    # SSE 沿链路推进度：对决中 → 胜负已分/奇人回归 → 单条转写正文（round 0，双视角成对发布）
    assert stream.events == [
        {"type": "stage", "stage": "dueling"},
        {"type": "stage", "stage": "recounting", "fighter_a": "青锋", "fighter_b": "血影"},
        {"type": "segment", "round": 0, "narration_a": res.narration_a, "narration_b": res.narration_b},
    ]


def test_run_deduction_transcribe_failure_degrades():
    """转写 LLM 重试耗尽（抛异常）→ 两侧降级为上帝正文兜底，战斗仍产出结果。"""
    from app.services.deduction import run_deduction

    user_a = SimpleNamespace(id=1, username="异闻师甲")
    user_b = SimpleNamespace(id=2, username="异闻师乙")

    def _ability(name, effect):
        return SimpleNamespace(name=name, effect=effect, detail="", understanding="", tactic="")

    class FakeStream:
        def __init__(self):
            self.events = []

        async def publish(self, ev):
            self.events.append(ev)

    def _deduce_llm():
        llm = MagicMock()
        llm.ainvoke = AsyncMock(return_value="血影以血咒反噬，青锋倒下。胜者：血影")
        return llm

    def _transcribe_chain():
        chain = MagicMock()
        chain.ainvoke = AsyncMock(side_effect=TimeoutError("转写僵死"))
        return chain

    with patch("app.services.reliability.asyncio.sleep", new=AsyncMock()):  # 免退避等待
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
                build_discuss=_discuss_builder("报告"),
                build_transcribe=_transcribe_chain,
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
    from app.services.deduction import run_deduction

    user_a = SimpleNamespace(id=1, username="异闻师甲")
    user_b = SimpleNamespace(id=2, username="异闻师乙")

    def _ability(name, effect):
        return SimpleNamespace(name=name, effect=effect, detail="", understanding="", tactic="")

    class FakeStream:
        async def publish(self, ev):
            pass

    def _deduce_llm():
        llm = MagicMock()
        llm.ainvoke = AsyncMock(return_value="血影以血咒反噬，青锋倒下。胜者：血影")  # 上帝视角：无影刃表现
        return llm

    def _transcribe_chain():
        chain = MagicMock()

        async def _ainvoke(kwargs):
            return {
                "narration_a": "青锋的合格讲述",
                "narration_b": "我见他掌中凝出影刃，寒光一闪。",  # 泄露对家异能名「影刃」
            }

        chain.ainvoke = AsyncMock(side_effect=_ainvoke)
        return chain

    repair_calls = []

    def _content_validate_builder():
        def build():
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
        def build():
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
            build_discuss=_discuss_builder("报告"),
            build_transcribe=_transcribe_chain,
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
    from app.services.deduction import run_deduction

    user_a = SimpleNamespace(id=1, username="异闻师甲")
    user_b = SimpleNamespace(id=2, username="异闻师乙")

    def _ability(name, effect):
        return SimpleNamespace(name=name, effect=effect, detail="", understanding="", tactic="")

    class FakeStream:
        async def publish(self, ev):
            pass

    def _deduce_llm():
        llm = MagicMock()
        llm.ainvoke = AsyncMock(return_value="血影以血咒反噬，青锋倒下。胜者：血影")
        return llm

    def _transcribe_chain():
        chain = MagicMock()
        chain.ainvoke = AsyncMock(return_value={"narration_a": "A叙述", "narration_b": "B叙述"})
        return chain

    def _always_fail_builder():
        def build():
            chain = MagicMock()
            chain.ainvoke = AsyncMock(return_value=TranscribeVerdict(passes=False, violations=["叙述不合规"]))
            return chain

        return build

    def _repair_builder():
        def build():
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
            build_discuss=_discuss_builder("报告"),
            build_transcribe=_transcribe_chain,
            build_validate=_always_fail_builder(),
            build_repair=_repair_builder(),
        )
    )

    assert res.narration_a == "A叙述"  # 修复后再校验仍不合格 → 退回原文稿件
    assert res.narration_b == "B叙述"


def test_run_discussion_node_before_deduce():
    """讨论节点先于推演：拿到双方信息（含异能/战术）生成报告，输出作为 discuss_report 传入推演 LLM。"""
    from app.services.deduction import run_deduction

    user_a = SimpleNamespace(id=1, username="异闻师甲")
    user_b = SimpleNamespace(id=2, username="异闻师乙")

    def _ability(name, effect):
        return SimpleNamespace(name=name, effect=effect, detail="", understanding="", tactic="")

    class FakeStream:
        async def publish(self, ev):
            pass

    discuss_inputs = []

    def _discuss_llm():
        chain = MagicMock()

        async def _ainvoke(kwargs):
            discuss_inputs.append(kwargs["info"])
            return "【结论】金身可挡精神冲击，但先被信息定位再偷袭则破。"

        chain.ainvoke = AsyncMock(side_effect=_ainvoke)
        return chain

    captured = {}

    def _deduce_llm():
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
            abilities_a=[_ability("影刃", "斩杀")],
            abilities_b=[_ability("血咒", "诅咒")],
            tactic_a="先手突袭",
            tactic_b="潜行伏击",
            style_a="暗杀流",
            style_b="潜行流",
            build_discuss=_discuss_llm,
            build_deduce=_deduce_llm,
            build_transcribe=_empty_transcribe_builder(),
            build_validate=_pass_validate_builder(),
            build_repair=_repair_builder(""),
        )
    )

    # 讨论节点恰好 1 次、先于推演拿到双方信息（异能 + 战术 + 风格）
    assert len(discuss_inputs) == 1
    assert "青锋" in discuss_inputs[0] and "血影" in discuss_inputs[0]
    assert "影刃" in discuss_inputs[0] and "血咒" in discuss_inputs[0]
    assert "先手突袭" in discuss_inputs[0] and "潜行伏击" in discuss_inputs[0]
    # 讨论输出作为 discuss_report 传给推演 LLM
    assert captured["discuss_report"] == "【结论】金身可挡精神冲击，但先被信息定位再偷袭则破。"


def test_discuss_failure_degrades_to_direct_deduce():
    """讨论节点抛异常（重试耗尽）→ 降级为仅用双方信息推演，战斗不废场、结果与无讨论时一致。"""
    from app.services.deduction import run_deduction

    user_a = SimpleNamespace(id=1, username="异闻师甲")
    user_b = SimpleNamespace(id=2, username="异闻师乙")

    def _ability(name, effect):
        return SimpleNamespace(name=name, effect=effect, detail="", understanding="", tactic="")

    class FakeStream:
        async def publish(self, ev):
            pass

    def _discuss_llm():
        chain = MagicMock()
        chain.ainvoke = AsyncMock(side_effect=TimeoutError("讨论僵死"))
        return chain

    captured = {}

    def _deduce_llm():
        llm = MagicMock()

        async def _ainvoke(kwargs):
            captured["discuss_report"] = kwargs["discuss_report"]
            return "血影以血咒反噬，青锋倒下。胜者：血影"

        llm.ainvoke = AsyncMock(side_effect=_ainvoke)
        return llm

    with patch("app.services.reliability.asyncio.sleep", new=AsyncMock()):  # 免退避等待
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
                build_discuss=_discuss_llm,
                build_deduce=_deduce_llm,
                build_transcribe=_empty_transcribe_builder(),
                build_validate=_pass_validate_builder(),
                build_repair=_repair_builder(""),
            )
        )

    # 讨论失败被捕获，推演照常进行并产出结果；discuss_report 为空（未污染推演输入）
    assert res.winner_side == "B"
    assert res.result == "血影"
    assert captured["discuss_report"] == ""
