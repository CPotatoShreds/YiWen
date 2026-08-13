"""奇人榜刻印：玩家把奇人「上榜」时冻结的当前状态，供任何异闻师点榜发起切磋。

上榜 = 刻印当前奇人（名字/风格/战术 + 所装奇术快照）为一条榜单条目；删除奇人不清榜
（loadout_id 仅溯源）。一奇人可多席（每次上榜生成新刻印）。
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BoardEntry(Base):
    __tablename__ = "board_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)  # 榜主
    loadout_id: Mapped[int | None] = mapped_column(ForeignKey("loadouts.id"), nullable=True)  # 来源奇人（仅溯源，删除不清榜）
    name: Mapped[str] = mapped_column(Text, server_default="")  # 奇人姓名（刻印）
    style: Mapped[str] = mapped_column(Text, server_default="")  # 战斗风格（刻印）
    tactic: Mapped[str] = mapped_column(Text, server_default="")  # 战术（刻印，榜上仅保密展示）
    abilities: Mapped[list] = mapped_column(JSON, default=list)  # [{name, effect, detail, tactic, understanding}] 冻结奇术快照（榜上保密，发起对决时作快照）
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
