"""小天下集单次挑战的 SSE 发布/订阅通道（跨实例事件总线）。

设计边界（docs/plans/2026-09-13-sse-scope-refactor.md）：SSE 只服务"满足条件的
LLM 节点输出"——上帝视角以遮挡进度（god_progress，只发累计字数）呈现，双方视角
逐字转写（view_chunk，带 side）实时推送；阶段进度改由前端轮询驱动，stage 事件
已退场；回放流随之移除（终态由端点查库短路），快照仅保留进程内 _emitted。

拓扑：
- 实时：publish() 先投本地订阅者队列，再向 Redis 全局频道广播信封（origin=实例号）。
  各实例的 relay 协程收到他人实例的事件后转投本地订阅者；自身 origin 跳过，防回环双投。
- 侧别过滤：订阅者登记侧别（challenger/guardian），带 side 的事件只投递给同侧
  订阅者（防守方收到挑战者正文；无 side 事件如 done/error/god_progress 全体广播）。
- 降级：Redis 不可用时退化为单进程模式（本地投递照旧，跨实例能力暂失），
  仅在状态翻转时打一条 warning 防刷屏。
"""

import asyncio
import json
import uuid
from uuid import UUID

from redis.exceptions import RedisError

from app.core.logger import get_logger
from app.core.metrics import SSE_STREAMS_ACTIVE
from app.core.redis import get_redis

logger = get_logger("scenario_stream")

INSTANCE_ID = uuid.uuid4().hex

_EVENTS_CHANNEL = "scenario:challenge-events"

_redis_ok = True


def _note_redis_failure(exc: Exception) -> None:
    global _redis_ok
    if _redis_ok:
        _redis_ok = False
        logger.warning("事件总线 Redis 不可用，退化为单进程模式：%s", exc)


def _note_redis_recovered() -> None:
    global _redis_ok
    if not _redis_ok:
        _redis_ok = True
        logger.warning("事件总线 Redis 已恢复")


class ScenarioChallengeStream:
    """单条挑战的 SSE 发布/订阅通道（含侧别过滤）。"""

    def __init__(self, challenge_id: UUID) -> None:
        self.challenge_id = challenge_id
        self._subscribers: dict[asyncio.Queue, str | None] = {}  # 队列 → 订阅侧别（None=不过滤）
        self._emitted: list[dict] = []  # 本地快照：仅 done/error 等无侧别终局事件

    def _fanout(self, event: dict) -> None:
        side = event.get("side")
        for queue, subscriber_side in list(self._subscribers.items()):
            if side is not None and subscriber_side is not None and side != subscriber_side:
                continue  # 侧别不符：守方连接不投挑战者事件（含逐字正文）
            queue.put_nowait(event)

    async def subscribe(self, side: str | None = None) -> tuple[asyncio.Queue, list[dict]]:
        """登记本地订阅者（登记侧别用于过滤）并返回 (队列, 本地快照)。"""
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[queue] = side
        SSE_STREAMS_ACTIVE.inc()
        return queue, list(self._emitted)

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.pop(queue, None)
        SSE_STREAMS_ACTIVE.dec()

    async def publish(self, event: dict, *, replay: bool = True) -> None:
        if replay:
            self._emitted.append(event)
        self._fanout(event)
        await _broadcast_remote(self.challenge_id, event)
        if event.get("type") in {"done", "error"}:
            # 终态后端点靠查库短路，本地通道可退场
            _registry.pop(self.challenge_id, None)


async def _broadcast_remote(challenge_id: UUID, event: dict) -> None:
    """向其他实例广播事件；失败静默降级。"""
    try:
        envelope = json.dumps(
            {"origin": INSTANCE_ID, "challenge_id": str(challenge_id), "event": event},
            ensure_ascii=False,
        )
        await get_redis().publish(_EVENTS_CHANNEL, envelope)
        _note_redis_recovered()
    except (RedisError, OSError) as exc:
        _note_redis_failure(exc)


_relay_ready: asyncio.Event | None = None  # 当前 relay 完成订阅后置位（测试与巡检用）


async def start_scenario_event_relay() -> None:
    """跨实例事件中转：订阅全局频道，把他人实例的事件投给本地订阅者。

    常驻协程，随 FastAPI lifespan 启停；断线自动重连（5 秒退避）。
    """
    global _relay_ready
    _relay_ready = None  # 只认本轮自己的订阅信号，不继承上一轮/他实例的状态
    while True:
        try:
            pubsub = get_redis().pubsub()
            await pubsub.subscribe(_EVENTS_CHANNEL)
            subscribed = asyncio.Event()
            _relay_ready = subscribed
            subscribed.set()
            _note_redis_recovered()
            try:
                while True:
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    if not message or message.get("type") != "message":
                        continue
                    try:
                        envelope = json.loads(message["data"])
                        if envelope.get("origin") == INSTANCE_ID:
                            continue
                        stream = _registry.get(UUID(envelope["challenge_id"]))
                        if stream is not None:
                            stream._fanout(envelope["event"])
                    except (json.JSONDecodeError, KeyError, ValueError) as exc:
                        logger.warning("忽略无法解析的事件信封：%s", exc)
            except (RedisError, OSError) as exc:
                _note_redis_failure(exc)
            finally:
                try:
                    await pubsub.aclose()
                except (RedisError, OSError):
                    pass
        except asyncio.CancelledError:
            raise
        except (RedisError, OSError) as exc:
            _note_redis_failure(exc)
        await asyncio.sleep(5)


_registry: dict[UUID, ScenarioChallengeStream] = {}


def get_scenario_stream(challenge_id: UUID) -> ScenarioChallengeStream:
    stream = _registry.get(challenge_id)
    if stream is None:
        stream = ScenarioChallengeStream(challenge_id)
        _registry[challenge_id] = stream
    return stream