"""pytest 全局夹具：隔离后台 LLM 任务（异能理解生成），防止测试触发真实 API 调用。"""
import os
import shutil
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# 测试库隔离：每次 pytest 进程用独立的临时 SQLite 文件，避免共享 ./ynfight.db 被
# 后台对战任务在事件循环关闭时取消而留下的脏连接锁库（跨运行互相污染）。
# 必须在导入 app（app.db.base 建全局 engine）之前设置环境变量。
_tmp_db_dir = tempfile.mkdtemp(prefix="ynfight_pytest_")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{os.path.join(_tmp_db_dir, 'test.db').replace(os.sep, '/')}"


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
    with patch("app.services.battle._build_usage_llm", return_value=chain):
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
    """会话结束清理临时测试库目录；文件被后台连接占用时静默跳过。"""
    yield
    shutil.rmtree(_tmp_db_dir, ignore_errors=True)
