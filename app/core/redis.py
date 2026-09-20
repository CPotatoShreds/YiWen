"""Redis 异步客户端（按事件循环缓存；asyncpg/redis 连接均绑定 loop，跨 loop 复用会撞已关闭循环）。

仅用于**可降级**的场景（奇术比对缓存、事件总线、登录锁定）：连接/读写失败一律由
调用方静默处理，绝不影响主流程。短超时避免 Redis 不可用时拖慢请求。
"""

import asyncio

import redis.asyncio as aioredis

from app.core.config import get_settings

_clients: dict[int, tuple[asyncio.AbstractEventLoop, aioredis.Redis]] = {}


def get_redis() -> aioredis.Redis:
    """当前事件循环内缓存的 Redis 客户端；循环关闭后自动换新。"""
    loop = asyncio.get_running_loop()
    cached = _clients.get(id(loop))
    if cached is not None and cached[0] is loop and not loop.is_closed():
        return cached[1]
    # 清掉已关闭循环的孤儿连接，防连接池堆积
    for key, (owner, _) in list(_clients.items()):
        if owner.is_closed():
            _clients.pop(key, None)
    client = aioredis.from_url(
        get_settings().REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    _clients[id(loop)] = (loop, client)
    return client
