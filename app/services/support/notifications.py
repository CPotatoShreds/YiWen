"""站内通知：写入（create_notification）与进程内实时总线（按 user_id 订阅推送）。

写侧收敛为唯一入口 `create_notification`——业务代码只调它，不关心投递方式。
现阶段总线是进程内 asyncio.Queue（单进程适用）；将来多实例时把 publish 换成
Redis Pub/Sub 或消息队列，业务代码无需改动。无订阅者时跳过投递（行已在库，
客户端下次拉取/重连对账即可），不缓存快照。
"""

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification

# 通知实时总线：user_id → 该用户在线订阅队列集合（无界队列）
_registry: dict[int, set[asyncio.Queue]] = {}


def subscribe(user_id: int) -> asyncio.Queue:
    """注册一个订阅队列，返回该队列；SSE 端点持有它等待事件。"""
    q: asyncio.Queue = asyncio.Queue()
    _registry.setdefault(user_id, set()).add(q)
    return q


def unsubscribe(user_id: int, q: asyncio.Queue) -> None:
    """注销订阅队列；无剩余订阅者时清掉该用户注册表（防对象泄漏）。"""
    subs = _registry.get(user_id)
    if subs is None:
        return
    subs.discard(q)
    if not subs:
        _registry.pop(user_id, None)


async def create_notification(
    db: AsyncSession,
    *,
    user_id: int,
    actor_id: int | None = None,
    type: str,
    title: str,
    body: str = "",
    ref_type: str | None = None,
    ref_id: int | None = None,
) -> Notification:
    """写一条通知（落库 + 实时投递给在线的接收者）。调用方须已结束当前事务再调用。

    commit 后才 publish：SSE 客户端收到事件即重拉列表，此时行已在库，不会读到半提交态。
    """
    notif = Notification(
        user_id=user_id,
        actor_id=actor_id,
        type=type,
        title=title,
        body=body,
        ref_type=ref_type,
        ref_id=ref_id,
    )
    db.add(notif)
    await db.commit()
    await db.refresh(notif)
    for q in list(_registry.get(user_id, set())):
        q.put_nowait({"type": "notification", "id": notif.id})
    return notif
