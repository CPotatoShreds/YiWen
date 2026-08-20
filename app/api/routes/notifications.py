"""通知路由：列表（含未读数）/ 已读 / 全部已读 / 实时流（SSE）。

SSE 端点订阅用户级事件总线，新通知落库后由 create_notification 即时投递；
客户端收到事件或重连时全量重拉列表对账（无快照补发，靠拉取兜底正确性）。
"""

import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.base import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import NotificationList, NotificationOut
from app.services.support.notifications import subscribe, unsubscribe

router = APIRouter(prefix="/notifications", tags=["notifications"])

_LIST_LIMIT = 30


@router.get("", response_model=NotificationList)
async def list_notifications(
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationList:
    """我的通知：近 30 条倒序 + 未读总数（角标）。"""
    rows = (
        await db.execute(
            select(Notification)
            .where(Notification.user_id == current.id)
            .order_by(Notification.id.desc())
            .limit(_LIST_LIMIT)
        )
    ).scalars().all()
    unread = (
        await db.execute(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == current.id, Notification.read_at.is_(None))
        )
    ).scalar_one()
    return NotificationList(
        items=[NotificationOut.model_validate(n) for n in rows],
        unread=unread,
    )


async def _owned_notification(db: AsyncSession, user_id: int, notification_id: int) -> Notification:
    """取本人通知（不存在或非本人 → 404）。"""
    notif = await db.get(Notification, notification_id)
    if notif is None or notif.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="通知不存在")
    return notif


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(
    notification_id: int,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """标记单条已读（幂等）。"""
    notif = await _owned_notification(db, current.id, notification_id)
    if notif.read_at is None:
        notif.read_at = datetime.now(UTC).replace(tzinfo=None)  # 与 created_at 同为 naive UTC
        await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_read(
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """全部标记已读。"""
    rows = (
        await db.execute(
            select(Notification).where(Notification.user_id == current.id, Notification.read_at.is_(None))
        )
    ).scalars().all()
    now = datetime.now(UTC).replace(tzinfo=None)
    for n in rows:
        n.read_at = now
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/stream")
async def notifications_stream(
    current: Annotated[User, Depends(get_current_user)],
) -> StreamingResponse:
    """通知实时流（SSE）：有新的落库通知时即时推送 {type: notification, id}；客户端据此重拉列表。"""

    def _encode(ev: dict) -> str:
        return f"event: {ev['type']}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"

    async def gen():
        q = subscribe(current.id)
        try:
            while True:
                ev = await q.get()
                if ev is None:  # 关闭哨兵（预留）
                    break
                yield _encode(ev)
        finally:
            unsubscribe(current.id, q)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
