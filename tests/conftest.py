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
