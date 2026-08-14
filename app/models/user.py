"""异闻师模型：账号 + 名望（天梯分）/见闻（唯一养成属性）+ 奇人槽位上限。"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# 奇人槽位：初始 3 位，每满 50 见闻解锁 +1 槽，上限 99
LOADOUT_BASE = 3
LOADOUT_PER_XJ = 50
LOADOUT_CAP = 99


def loadout_capacity(exp: int) -> int:
    """按见闻推导奇人槽位上限：3 + 见闻//50，封顶 99。"""
    return min(LOADOUT_CAP, LOADOUT_BASE + exp // LOADOUT_PER_XJ)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    exp: Mapped[int] = mapped_column(Integer, default=0)  # 见闻：唯一养成属性，满档解锁更多奇人槽位
    rank_points: Mapped[int] = mapped_column(Integer, default=1000)  # 名望：Elo 天梯分，仅排名
    last_login_date: Mapped[str | None] = mapped_column(String(10), nullable=True)  # YYYY-MM-DD 开张日
    last_battle_date: Mapped[str | None] = mapped_column(String(10), nullable=True)  # 当日首次启程
    reveal_on_miss: Mapped[bool] = mapped_column(Boolean, default=False)  # 对家猜奇术未中时是否看破我的奇术
    active_profile_id: Mapped[int | None] = mapped_column(  # 当前激活的自配 LLM 方案（未配则 None，用服务器默认）
        ForeignKey("llm_profiles.id", ondelete="SET NULL"), nullable=True
    )
    active_profile: Mapped["LlmProfile | None"] = relationship(foreign_keys=[active_profile_id])
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))  # 管理员：可登录后台
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    @property
    def max_loadouts(self) -> int:
        """当前见闻可解锁的奇人槽位上限（Pydantic from_attributes 读取）。"""
        return loadout_capacity(self.exp)
