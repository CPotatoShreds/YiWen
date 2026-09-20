"""奇术逐对比对缓存：命中免调 LLM、顺序无关、Redis 故障降级。

全部用内存假 Redis 与打桩的 LLM 调用，不依赖真实 Redis / 模型。
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.services.ability import pair_comparison
from app.services.nodes.ability.pair_judge import PairVerdict

ABILITY_A = {"name": "火", "effect": "燃烧", "detail": ""}
ABILITY_B = {"name": "水", "effect": "浇灭", "detail": ""}
ABILITY_C = {"name": "风", "effect": "吹散", "detail": ""}


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str) -> None:
        self.store[key] = value


def _verdict() -> PairVerdict:
    return PairVerdict(
        conflict=True, conflict_reason="水火相克", stronger_ability="水", stronger_reason="三相更盛"
    )


@pytest.fixture
def fake_redis(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(pair_comparison, "get_redis", lambda: fake)
    return fake


@pytest.fixture
def llm(monkeypatch):
    """打桩比对节点调用，返回 (mock, 计数访问器)。"""
    mock = AsyncMock(return_value=_verdict())
    monkeypatch.setattr(pair_comparison, "ainvoke_with_reliability", mock)
    return mock


async def _compare(left, right) -> PairVerdict:
    return await pair_comparison.compare_pair(
        left=left, right=right, judge=object(), semaphore=asyncio.Semaphore(4), challenge_id="c-1"
    )


async def test_cache_hit_skips_llm(fake_redis, llm):
    first = await _compare(ABILITY_A, ABILITY_B)
    second = await _compare(ABILITY_A, ABILITY_B)
    assert llm.await_count == 1
    assert first.stronger_ability == second.stronger_ability == "水"
    assert len(fake_redis.store) == 1


async def test_order_independent_shares_cache(fake_redis, llm):
    await _compare(ABILITY_A, ABILITY_B)
    await _compare(ABILITY_B, ABILITY_A)
    assert llm.await_count == 1
    assert len(fake_redis.store) == 1


async def test_distinct_pairs_miss_separately(fake_redis, llm):
    await _compare(ABILITY_A, ABILITY_B)
    await _compare(ABILITY_A, ABILITY_C)
    assert llm.await_count == 2
    assert len(fake_redis.store) == 2


async def test_redis_unavailable_degrades(monkeypatch, llm):
    def boom():
        raise RuntimeError("redis down")

    monkeypatch.setattr(pair_comparison, "get_redis", boom)
    verdict = await _compare(ABILITY_A, ABILITY_B)
    assert verdict.stronger_ability == "水"
    assert llm.await_count == 1


async def test_corrupt_cache_value_degrades(fake_redis, llm):
    key = pair_comparison._cache_key(
        pair_comparison.ability_hash(ABILITY_A), pair_comparison.ability_hash(ABILITY_B)
    )
    fake_redis.store[key] = "{ 不是合法 PairVerdict"
    verdict = await _compare(ABILITY_A, ABILITY_B)
    assert verdict.stronger_ability == "水"
    assert llm.await_count == 1
