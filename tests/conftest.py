"""pytest 全局夹具：隔离后台 LLM 任务（异能理解生成），防止测试触发真实 API 调用。"""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import psycopg
import pytest

# 测试库隔离：使用独立 PG 测试库（同一 postgres 实例上的 ynfight_test）。
# 每个 pytest 会话重建一次，避免共享开发库数据互相污染。必须在导入 app
# （app.db.base 建全局 engine）之前设置环境变量。
os.environ["DATABASE_URL"] = "postgresql+asyncpg://ynfight:ynfight@localhost:5432/ynfight_test"

# 重建测试库（DROP + CREATE）：psycopg 直连维护库，autocommit 下执行 DDL。
try:
    _admin = psycopg.connect("postgresql://ynfight:ynfight@localhost:5432/postgres", autocommit=True)
    _admin.execute("DROP DATABASE IF EXISTS ynfight_test WITH (FORCE)")
    _admin.execute("CREATE DATABASE ynfight_test")
    _admin.close()
except psycopg.Error as exc:
    raise RuntimeError(
        "测试需要本地 Docker PostgreSQL：先运行 `docker compose up -d` 再跑 pytest。"
    ) from exc


@pytest.fixture(autouse=True)
def _no_real_understanding_llm():
    """异能理解后台任务打桩：返回固定理解文本（瞬时完成），全测试生效。"""
    chain = MagicMock()

    async def fake_ainvoke(inputs):
        name = inputs.get("name", "")
        return f"AI 理解：对「{name}」的客观分析，涵盖核心机制、触发条件与限制。"

    chain.ainvoke = AsyncMock(side_effect=fake_ainvoke)
    with patch("app.services.ability_understanding.build_understanding_chain", return_value=chain):
        yield


@pytest.fixture(autouse=True)
def _no_real_loadout_interpretation_llm():
    """奇人风格/战术解读后台任务打桩：返回空清洗文本（解读为空 → 推演回退原文），全测试生效。

    路由在风格/战术/装配变更时调度该任务；不打桩会触发真实 LLM。空文本对既有测试零影响。
    """
    from app.services.loadout_interpretation import LoadoutInterpretation

    chain = MagicMock()
    chain.ainvoke = AsyncMock(return_value=LoadoutInterpretation(style="", tactic=""))
    with patch("app.services.loadout_interpretation.build_interpretation_chain", return_value=chain):
        yield


@pytest.fixture(autouse=True)
def _no_real_usage_llm():
    """奇术使用子集节点打桩：返回空子集（触发 _prepare_guess 的「全部装配」降级，等价于全用），瞬时完成，全测试生效。

    结算时每个有败方的对决都会调用该节点；不打桩会触发真实 LLM。具体子集行为由测试自行 override。
    """
    from app.services.nodes.usage_judge import UsedAbilities

    chain = MagicMock()
    chain.ainvoke = AsyncMock(return_value=UsedAbilities(indices=[]))
    with (
        patch("app.services.battle._build_usage_llm", return_value=chain),
        patch("app.services.test_battle.build_usage_llm", return_value=chain),
    ):
        yield


@pytest.fixture(autouse=True)
def _no_real_discuss_llm():
    """讨论节点打桩：返回空报告（推演退化为仅用双方信息），全测试生效，避免触发真实 LLM。

    run_deduction 默认 build_discuss=build_discuss_llm 在 def 时绑定，测试 arena（test_battle
    直接调 run_deduction）需单独打桩 test_battle.build_discuss_llm。具体报告行为由测试 override。
    """
    chain = MagicMock()
    chain.ainvoke = AsyncMock(return_value="")
    with (
        patch("app.services.battle._build_discuss_llm", return_value=chain),
        patch("app.services.test_battle.build_discuss_llm", return_value=chain),
    ):
        yield


@pytest.fixture(autouse=True)
def _no_real_test_arena_guess_nodes():
    """试验场猜词配对/检定打桩：返回空匹配，瞬时完成。

    test_battle.submit_test_guess 直接 import 节点构造器（不走 battle 层别名），需单独打桩。
    拆分环节为纯函数 split_atomic_guesses（无 LLM）。具体行为由测试自行 override。
    """
    from app.services.nodes.guess_matcher import PairMatch, Verification

    pair_chain = MagicMock()
    pair_chain.ainvoke = AsyncMock(return_value=PairMatch(snippet=""))
    verify_chain = MagicMock()
    verify_chain.ainvoke = AsyncMock(return_value=Verification(guessed=False, reason=""))
    with (
        patch("app.services.test_battle.build_guess_pair_llm", return_value=pair_chain),
        patch("app.services.test_battle.build_guess_verify_llm", return_value=verify_chain),
    ):
        yield


@pytest.fixture(autouse=True)
def _no_real_transcribe_validation():
    """转写校验/修复节点打桩：校验恒通过（合格叙述原样保留），全测试生效，避免触发真实 LLM。

    结算链路转写后必走校验节点；不打桩会触发真实 LLM。具体违规判定/修复行为由测试自行 override。
    """
    from app.services.nodes.transcribe_validator import TranscribeVerdict

    validate_chain = MagicMock()
    validate_chain.ainvoke = AsyncMock(return_value=TranscribeVerdict(passes=True))
    repair_chain = MagicMock()
    repair_chain.ainvoke = AsyncMock(return_value="")
    with (
        patch("app.services.battle._build_validate_chain", return_value=validate_chain),
        patch("app.services.battle._build_repair_chain", return_value=repair_chain),
    ):
        yield


@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_db():
    """会话结束清理测试库连接（PG 测试库保留即可，下次会话会自动重建）。"""
    yield
