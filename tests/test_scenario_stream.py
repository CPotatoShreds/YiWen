"""SSE 事件总线（Redis 跨实例拓扑 + 侧别过滤）测试。

真实 Redis（settings.REDIS_URL）可达才跑，否则整文件跳过——pub/sub 的订阅
语义无法用内存替身保真。跨"实例"用 monkeypatch 模块级 INSTANCE_ID 模拟：
发布方打 A 标，中转协程以 B 身份运行。
"""

import asyncio
import socket
import uuid
from unittest.mock import patch
from urllib.parse import urlparse

import pytest

from app.core.config import get_settings
from app.services.scenario import stream as stream_module
from app.services.scenario.stream import ScenarioChallengeStream

_url = urlparse(get_settings().REDIS_URL)


def _redis_reachable() -> bool:
    try:
        with socket.create_connection((_url.hostname or "localhost", _url.port or 6379), timeout=0.5):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not _redis_reachable(), reason="需要真实 Redis")


@pytest.fixture(autouse=True)
async def _fresh_redis_client():
    """redis 客户端按事件循环缓存，测完关闭本轮连接，防孤儿连接与跨用例污染。"""
    from app.core import redis as redis_module

    yield
    for key, (_, client) in list(redis_module._clients.items()):
        try:
            await client.aclose()
        except Exception:  # noqa: BLE001, S110 - 清理失败不影响断言
            pass
        redis_module._clients.pop(key, None)


async def _start_relay() -> asyncio.Task:
    """启动 relay 并等它自己的订阅就绪信号（numsub 会被僵尸订阅连接污染，不可作依据）。"""
    import time as _time

    task = asyncio.create_task(stream_module.start_scenario_event_relay())
    deadline = _time.monotonic() + 5.0
    while _time.monotonic() < deadline:
        ready = stream_module._relay_ready
        if ready is not None and ready.is_set():
            return task
        await asyncio.sleep(0.02)
    return task


async def test_view_chunk_live_only():
    """view_chunk 即发即弃：同通道同侧实时可达。"""
    cid = uuid.uuid4()
    channel = ScenarioChallengeStream(cid)
    queue, _ = await channel.subscribe(side="challenger")
    await channel.publish({"type": "view_chunk", "side": "challenger", "text": "一"}, replay=False)
    assert (await asyncio.wait_for(queue.get(), 1.0))["text"] == "一"


async def test_side_filtering_only_delivers_matching_side():
    """带 side 的事件只投同侧订阅者：挑战者连接收不到守方转写，反之亦然。"""
    cid = uuid.uuid4()
    channel = ScenarioChallengeStream(cid)
    challenger_queue, _ = await channel.subscribe(side="challenger")
    guardian_queue, _ = await channel.subscribe(side="guardian")

    await channel.publish({"type": "view_chunk", "side": "challenger", "text": "挑战者正文"}, replay=False)
    await channel.publish({"type": "view_chunk", "side": "guardian", "text": "守方正文"}, replay=False)

    assert (await asyncio.wait_for(challenger_queue.get(), 1.0))["text"] == "挑战者正文"
    assert (await asyncio.wait_for(guardian_queue.get(), 1.0))["text"] == "守方正文"
    assert challenger_queue.empty()  # 未投递守方正文
    assert guardian_queue.empty()  # 未投递挑战者正文


async def test_no_side_events_broadcast_to_all_sides():
    """无 side 事件（god_progress/done/error）对全部订阅者广播。"""
    cid = uuid.uuid4()
    channel = ScenarioChallengeStream(cid)
    challenger_queue, _ = await channel.subscribe(side="challenger")
    guardian_queue, _ = await channel.subscribe(side="guardian")

    await channel.publish({"type": "god_progress", "chars": 42}, replay=False)

    assert (await asyncio.wait_for(challenger_queue.get(), 1.0))["chars"] == 42
    assert (await asyncio.wait_for(guardian_queue.get(), 1.0))["chars"] == 42


async def test_cross_instance_live_delivery_via_relay():
    """A 发布的实时事件经 relay 中转投给 B 的同侧订阅者。"""
    cid = uuid.uuid4()
    try:
        with patch.object(stream_module, "INSTANCE_ID", "inst-b"):
            mine = stream_module.get_scenario_stream(cid)  # 本"实例"（B）注册的通道
            other_queue, _ = await mine.subscribe(side="challenger")
            relay = await _start_relay()
            try:
                publisher = ScenarioChallengeStream(cid)  # 模拟 A 实例（不在本进程注册表）
                payload = {"type": "view_chunk", "side": "challenger", "text": "跨实例"}
                # pub/sub 是 at-most-once：极端时序下可能错过单次发布，重试投递
                with patch.object(stream_module, "INSTANCE_ID", "inst-a"):
                    await publisher.publish(payload, replay=False)
                event = None
                for _ in range(5):
                    try:
                        event = await asyncio.wait_for(other_queue.get(), 1.5)
                        break
                    except TimeoutError:
                        with patch.object(stream_module, "INSTANCE_ID", "inst-a"):
                            await publisher.publish(payload, replay=False)
                assert event == {"type": "view_chunk", "side": "challenger", "text": "跨实例"}
            finally:
                relay.cancel()
                await asyncio.gather(relay, return_exceptions=True)
    finally:
        stream_module._registry.pop(cid, None)


async def test_own_origin_not_double_delivered():
    """自身实例的事件只经本地直投一份，relay 不回环补投。"""
    cid = uuid.uuid4()
    try:
        with patch.object(stream_module, "INSTANCE_ID", "inst-a"):
            channel = stream_module.get_scenario_stream(cid)
            queue, _ = await channel.subscribe(side="challenger")
            relay = await _start_relay()
            try:
                await channel.publish({"type": "turn", "side": "challenger", "turn": {"role": "views"}}, replay=False)
                assert (await asyncio.wait_for(queue.get(), 2.0))["type"] == "turn"
                await asyncio.sleep(0.5)  # 留出 relay 收到自己信封并跳过的时间窗
                assert queue.empty()
            finally:
                relay.cancel()
                await asyncio.gather(relay, return_exceptions=True)
    finally:
        stream_module._registry.pop(cid, None)


async def test_done_event_cleans_registry_and_snapshot():
    cid = uuid.uuid4()
    channel = stream_module.get_scenario_stream(cid)
    await channel.publish({"type": "done", "status": "won"})
    assert stream_module._registry.get(cid) is None
    # 本地快照保留无侧别终局事件，供同实例晚到订阅者补发
    _, snapshot = await channel.subscribe(side="challenger")
    assert {"type": "done", "status": "won"} in snapshot