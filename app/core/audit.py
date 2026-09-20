"""管理操作审计埋点：与业务写同事务落库，调用方负责 commit。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_audit import AdminAuditLog


async def audit(
    db: AsyncSession,
    operator_id: int | None,
    action: str,
    *,
    target_type: str = "",
    target_id=None,
    detail: dict | None = None,
) -> None:
    db.add(
        AdminAuditLog(
            operator_id=operator_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else "",
            detail=detail,
        )
    )
