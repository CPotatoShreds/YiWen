"""奇人数据模型。每位异闻师初始 3 位奇人（可新增），每位装入若干奇术，一个奇术可入多位奇人。

- enabled（解封）：已解封 = 可主动启程，且进入台下听客。
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

MAX_LOADOUT_ABILITIES = 4


class Loadout(Base):
    __tablename__ = "loadouts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(Text, server_default="")  # 奇人姓名（初始「奇人·壹/贰/叁」，可改名）
    style: Mapped[str] = mapped_column(Text, server_default="")  # 战斗风格（可选）
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    tactic: Mapped[str] = mapped_column(Text, server_default="")  # 这位奇人会怎么打（推演时指导整套打法）
    style_interpretation: Mapped[str] = mapped_column(Text, server_default="")  # 异步解读产出：剔除未装配奇术引用后的清洗风格
    tactic_interpretation: Mapped[str] = mapped_column(Text, server_default="")  # 异步解读产出：剔除未装配奇术引用后的清洗战术
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class LoadoutAbility(Base):
    __tablename__ = "loadout_abilities"

    loadout_id: Mapped[int] = mapped_column(ForeignKey("loadouts.id"), primary_key=True)
    ability_id: Mapped[str] = mapped_column(ForeignKey("abilities.id"), primary_key=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
