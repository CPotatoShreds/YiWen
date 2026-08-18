"""对决实时流（SSE）事件总线：推演过程中的分段转写与结果事件中继。

`_resolve_battle` 在每轮转写完成后把视角分段 publish 到该战场的事件总线；
SSE 端点订阅总线，按观看者身份只透传自己一侧的叙述，最后收到 done/error 事件后关闭。

订阅者用一个 asyncio.Queue（无界）接事件；`subscribe()` 会先返回一份已发出事件的
快照，让「中途才连上」的观看者也能补发此前各段，不会漏段。
"""

import asyncio

# 关闭哨兵：close() 时投递给每个订阅者队列，消费端收到即退出
_SENTINEL = None


class BattleStream:
    """单个战场的发布/订阅总线。"""

    def __init__(self, battle_id: int) -> None:
        self.battle_id = battle_id
        self._subscribers: set[asyncio.Queue] = set()
        self._emitted: list[dict] = []  # 已按序发出的事件，供迟到订阅者补发
        self._closed = False

    def subscribe(self) -> tuple[asyncio.Queue, list[dict]]:
        """注册一个订阅者，返回 (事件队列, 已发出事件快照)。

        快照与入队之间无 await，单事件循环内与 publish 的「先追加 _emitted 再入队」
        原子衔接：同一事件要么在快照里（补发），要么在队列里（实时），不会重复或遗漏。
        战斗已关闭时不再注册，直接补发快照 + 投递哨兵：迟到订阅者读完历史即退出，
        不会挂在空队列上（覆盖 SSE 端点「读到 pending 后战斗恰好结束」的竞态——若
        close 时弹出注册表，端点会拿到一个重建的空总线永久阻塞）。
        """
        q: asyncio.Queue = asyncio.Queue()
        snapshot = list(self._emitted)
        if self._closed:
            q.put_nowait(_SENTINEL)
        else:
            self._subscribers.add(q)
        return q, snapshot

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """注销订阅者；战斗已关闭且无剩余订阅者时，从注册表清掉本总线（防对象泄漏）。"""
        self._subscribers.discard(q)
        if self._closed and not self._subscribers:
            _registry.pop(self.battle_id, None)

    async def publish(self, event: dict, replay: bool = True) -> None:
        """发布一个事件；replay=False 时只实时入队、不进 `_emitted` 快照。

        逐字流式的 chunk 事件频率高、体积随文本线性增长，入快照会让迟到订阅者拿到无限膨胀的
        历史；这类事件用 replay=False，最终 segment/done 等结构性事件仍入快照供重连补发。
        """
        if self._closed:
            return
        if replay:
            self._emitted.append(event)
        for q in list(self._subscribers):
            q.put_nowait(event)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for q in list(self._subscribers):
            q.put_nowait(_SENTINEL)
        self._subscribers.clear()
        _registry.pop(self.battle_id, None)


_registry: dict[int, BattleStream] = {}


def _get_stream(battle_id: int) -> BattleStream:
    """取该战场的总线（不存在则创建）。推演任务与 SSE 端点共用同一注册表。"""
    stream = _registry.get(battle_id)
    if stream is None:
        stream = BattleStream(battle_id)
        _registry[battle_id] = stream
    return stream
