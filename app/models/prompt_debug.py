"""提示词方案调试数据模型：管理员预设提示词方案 + 某场行迹的重跑调试记录。

PromptScheme 存「各环节 system 提示词覆盖」（None = 用冻结默认，生产提示词行为不变）；
PromptDebugRun 存「用某方案重跑某场真实行迹」的产物——独立调试记录，不进入真实
行迹/排行榜/玩家可见面。仅管理员通过战报页对比查看。
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PromptScheme(Base):
    """提示词方案：每环节可空覆盖列，None = 用冻结默认模板。"""

    __tablename__ = "prompt_schemes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    discuss_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    deduce_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcribe_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    validate_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    repair_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    usage_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    guess_pair_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    guess_verify_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class PromptDebugRun(Base):
    """某场真实行迹用某方案重跑的调试记录（独立产物，不进玩家面）。"""

    __tablename__ = "prompt_debug_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    battle_id: Mapped[int] = mapped_column(ForeignKey("battles.id"), index=True)
    scheme_id: Mapped[int] = mapped_column(ForeignKey("prompt_schemes.id"))
    status: Mapped[str] = mapped_column(String(10), server_default="pending")  # pending/done/failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    story: Mapped[str] = mapped_column(Text, default="")  # JSON：{narration, narration_a, narration_b, result}
    discuss_report: Mapped[str] = mapped_column(Text, default="")
    winner_side: Mapped[str | None] = mapped_column(String(5), nullable=True)  # a/b/draw
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
