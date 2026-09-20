"""异闻师模型：账号（角色）+ 邮箱 + 当前激活 LLM 方案。"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

ROLE_USER = "user"
ROLE_ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)  # 仅经验证流程写入
    role: Mapped[str] = mapped_column(String(16), default=ROLE_USER, server_default=ROLE_USER)  # user / admin
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # 注销：软删 + 匿名化
    active_profile_id: Mapped[int | None] = mapped_column(  # 当前激活的自配 LLM 方案（未配则 None，用服务器默认）
        ForeignKey("llm_profiles.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        # 多个未绑定邮箱的用户（NULL）不参与唯一约束
        Index("uq_users_email", "email", unique=True, postgresql_where=text("email IS NOT NULL")),
    )

    @property
    def is_admin(self) -> bool:
        """兼容既有调用点（get_current_admin / 响应模型 from_attributes）的角色判定。"""
        return self.role == ROLE_ADMIN
