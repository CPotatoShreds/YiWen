"""pytest 全局夹具：隔离后台 LLM 任务（风格/战术解读等），防止测试触发真实 API 调用。"""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import psycopg
import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# 测试库隔离：使用独立 PG 测试库（同一 postgres 实例上的 ynfight_test）。
# 每个 pytest 会话重建一次，避免共享开发库数据互相污染。必须在导入 app
# （app.db.base 建全局 engine）之前设置环境变量。
os.environ["DATABASE_URL"] = "postgresql+asyncpg://ynfight:ynfight@localhost:5432/ynfight_test"
# 测试禁用连接池：TestClient 每个测试函数独立事件循环，池化连接会孤儿化（Event loop is closed）。
# 回退每会话新建连接（NullPool），生产默认开启池不受影响。
os.environ["DB_POOL_ENABLED"] = "false"

# LLM 方案密钥：测试进程内生成一组全新密钥，避免写 data/ 目录或用真实部署密钥。
# profile_crypto 惰性读 env 并缓存于进程 _state，故同样须在导入 app 之前设置。
_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
os.environ["LLM_PROFILE_PRIVATE_KEY"] = _private.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode()
os.environ["LLM_PROFILE_STORAGE_KEY"] = Fernet.generate_key().decode()

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
def _no_real_ability_understanding_llm():
    """奇术因果槽位后台任务打桩：返回默认空槽位（三相空、零相为 False），全测试生效。

    创建/更新奇术时路由调度该任务；不打桩会触发真实 LLM。空槽位对既有测试零影响
    （_render_ability 仅在 understanding 非空时才输出「因果槽位」行）。具体行为由测试 override。
    """
    from app.services.ability_understanding import AbilitySlot, Phase, SlotVerdict

    chain = MagicMock()
    chain.ainvoke = AsyncMock(
        return_value=AbilitySlot(
            verdict=SlotVerdict(zero_phase=False, source_phases=[], summary=""),
            pre=Phase(present=False),
            mid=Phase(present=False),
            post=Phase(present=False),
        )
    )
    with patch("app.services.ability_understanding.build_understanding_chain", return_value=chain):
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
def _no_real_pair_judge_llm():
    """能力对比节点打桩：返回无冲突判定（推演退化为仅用双方信息），全测试生效，避免触发真实 LLM。

    battle.py 的 _build_pair_judge_chain 别名与 test_battle 直接 import 的构建器都要打桩
    （对比节点在 run_deduction 编排内，两入口都会触达）。具体冲突判定行为由测试 override。
    """
    from app.services.nodes.ability_pairs import PairVerdict

    chain = MagicMock()
    chain.ainvoke = AsyncMock(return_value=PairVerdict(ability_a="", ability_b="", conflict=False))
    with (
        patch("app.services.battle._build_pair_judge_chain", return_value=chain),
        patch("app.services.test_battle.build_pair_judge_chain", return_value=chain),
    ):
        yield


@pytest.fixture(autouse=True)
def _no_real_discuss_llm():
    """讨论节点打桩：返回空报告，全测试生效，避免触发真实 LLM。

    讨论节点已脱离推演编排（能力对比节点暂时替代），battle.py 不再引用；仅 admin 试验场
    generate_test_discuss_report 仍直接 import，故保留 test_battle 侧打桩。具体报告行为由测试 override。
    """
    chain = MagicMock()
    chain.ainvoke = AsyncMock(return_value="")
    with (
        patch("app.services.test_battle.build_discuss_llm", return_value=chain),
    ):
        yield


@pytest.fixture(autouse=True)
def _no_real_test_arena_guess_nodes():
    """试验场猜词点评/检定打桩：返回空点评 + 未看破，瞬时完成。

    test_battle.submit_test_guess 直接 import 节点构造器（不走 battle 层别名），需单独打桩。
    具体行为由测试自行 override。
    """
    from app.services.nodes.guess_matcher import CommentaryRound, Verification

    commentary_chain = MagicMock()
    commentary_chain.ainvoke = AsyncMock(return_value=CommentaryRound(items=[]))
    verify_chain = MagicMock()
    verify_chain.ainvoke = AsyncMock(return_value=Verification(cracked=False, missing=""))
    with (
        patch("app.services.test_battle.build_guess_commentary_llm", return_value=commentary_chain),
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
