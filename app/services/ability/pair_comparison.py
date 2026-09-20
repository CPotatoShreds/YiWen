"""奇术逐对比对：Redis 缓存（奇术粒度、顺序无关、LRU 淘汰）优先，未命中回退比对节点。

缓存 key = ``cmp:{节点指纹}:{h1}:{h2}``：

- ``h`` = 单门奇术内容（name/effect/detail）的 sha256；
- 两个 h 排序拼接，故装配顺序无关，同一对奇术共享一条缓存，提示词也按同一顺序渲染；
- 节点指纹（``catalog.node_fingerprint``）含提示词文本与模型标识，任一改动即换 key，旧缓存自然失效；
- 值 = ``PairVerdict`` 的紧凑 JSON。

键的增长由 Redis ``allkeys-lru`` 淘汰策略约束（见 docker-compose.yml 的 redis 配置），不设 TTL。
Redis 不可用或读写异常时静默回退直连比对节点，绝不影响比对主流程。
"""

import asyncio
import hashlib
import json
from uuid import UUID

from langchain_core.runnables import Runnable

from app.core.logger import get_logger
from app.core.redis import get_redis
from app.services.llm.reliability import ainvoke_with_reliability
from app.services.nodes.ability.pair_judge import PairVerdict
from app.services.nodes.catalog import node_fingerprint

logger = get_logger("ability_pair_cache")

NODE_ID = "scenario_ability_pair"
_CACHE_PREFIX = "cmp"
_FIELDS = ("name", "effect", "detail")

# 进程内固定：提示词/模型不变则为常量，故不必每次比对重算
_CACHE_VERSION = node_fingerprint(NODE_ID)


def ability_hash(ability: dict) -> str:
    """单门奇术内容哈希（覆盖比对实际渲染的字段）。"""
    payload = {field: str(ability.get(field, "")) for field in _FIELDS}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def render_ability(ability: dict) -> str:
    """单门奇术渲染为比对输入文本（有值才附详细解释）。"""
    lines = [f"- {ability.get('name', '')}：{ability.get('effect', '')}"]
    if ability.get("detail"):
        lines.append(f"  详细解释：{ability['detail']}")
    return "\n".join(lines)


def _cache_key(hash_a: str, hash_b: str) -> str:
    low, high = (hash_a, hash_b) if hash_a <= hash_b else (hash_b, hash_a)
    return f"{_CACHE_PREFIX}:{_CACHE_VERSION}:{low}:{high}"


async def _cache_get(key: str) -> PairVerdict | None:
    try:
        raw = await get_redis().get(key)
    except Exception:  # noqa: BLE001 - 缓存不可用即视为未命中
        return None
    if not raw:
        return None
    try:
        return PairVerdict.model_validate_json(raw)
    except Exception:  # noqa: BLE001 - 脏数据当作未命中
        return None


async def _cache_set(key: str, verdict: PairVerdict) -> None:
    try:
        await get_redis().set(key, verdict.model_dump_json())
    except Exception:  # noqa: BLE001 - 写缓存失败不影响主流程
        return


async def compare_pair(
    *,
    left: dict,
    right: dict,
    judge: Runnable,
    semaphore: asyncio.Semaphore,
    challenge_id: UUID,
) -> PairVerdict:
    """逐对奇术对比：缓存命中直接返回，未命中在并发闸内调比对节点并回写缓存。"""
    hash_left = ability_hash(left)
    hash_right = ability_hash(right)
    key = _cache_key(hash_left, hash_right)

    cached = await _cache_get(key)
    if cached is not None:
        logger.debug("ability_pair_cache_hit key=%s", key)
        return cached

    first, second = (left, right) if hash_left <= hash_right else (right, left)
    async with semaphore:
        verdict: PairVerdict = await ainvoke_with_reliability(
            judge,
            {"ability_a": render_ability(first), "ability_b": render_ability(second)},
            operation=NODE_ID,
            trace_context={"kind": "scenario", "trace_id": str(challenge_id)},
        )
    await _cache_set(key, verdict)
    return verdict
