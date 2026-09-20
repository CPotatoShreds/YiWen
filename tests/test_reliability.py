import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm.reliability import ChainFailure, ainvoke_with_reliability


def test_retry_then_success():
    chain = MagicMock()
    chain.ainvoke = AsyncMock(side_effect=[TimeoutError("stalled"), "ok"])
    with patch("app.services.llm.reliability.asyncio.sleep", new=AsyncMock()) as sleep:
        assert asyncio.run(ainvoke_with_reliability(chain, {"k": 1}, operation="test")) == "ok"
    assert chain.ainvoke.await_count == 2
    sleep.assert_awaited_once()


def test_exhausted_raises_chain_failure():
    chain = MagicMock()
    chain.ainvoke = AsyncMock(side_effect=TimeoutError("stalled"))
    with patch("app.services.llm.reliability.asyncio.sleep", new=AsyncMock()), pytest.raises(ChainFailure) as exc:
        asyncio.run(ainvoke_with_reliability(chain, {"k": 1}, operation="scenario"))
    assert exc.value.operation == "scenario"
    assert exc.value.attempts == 3
