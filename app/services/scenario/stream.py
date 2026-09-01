"""小天下集单次挑战的实时事件总线。"""

import asyncio
from uuid import UUID


class ScenarioChallengeStream:
    """单条挑战的 SSE 发布/订阅通道。

    结构性阶段事件会保留，浏览器中途连入时可立刻恢复当前进度；逐字转写
    不重播，权威全文由挑战详情接口中的已落库回合补齐。
    """

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._emitted: list[dict] = []

    def subscribe(self) -> tuple[asyncio.Queue, list[dict]]:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(queue)
        return queue, list(self._emitted)

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    async def publish(self, event: dict, *, replay: bool = True) -> None:
        if replay:
            self._emitted.append(event)
        for queue in list(self._subscribers):
            queue.put_nowait(event)


_registry: dict[UUID, ScenarioChallengeStream] = {}


def get_scenario_stream(challenge_id: UUID) -> ScenarioChallengeStream:
    stream = _registry.get(challenge_id)
    if stream is None:
        stream = ScenarioChallengeStream()
        _registry[challenge_id] = stream
    return stream
