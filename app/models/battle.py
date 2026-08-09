"""对决记录。story 存行迹 JSON。"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Battle(Base):
    __tablename__ = "battles"
    # 并发防重：同一用户最多一场在途对决（先查后插有竞态，唯一索引兜底）
    __table_args__ = (
        Index("uq_battles_user_a_pending", "user_a_id", unique=True, sqlite_where=text("status = 'pending'")),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_a_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    user_b_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    winner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(10), server_default="done")  # pending 推演中 / done / failed
    story: Mapped[str] = mapped_column(Text, default="")  # JSON：{narration, winner, abilities_a, abilities_b}（pending 时为空）
    rank_delta_a: Mapped[int] = mapped_column(Integer, default=0)  # 名望变化（Elo）
    rank_delta_b: Mapped[int] = mapped_column(Integer, default=0)
    friendly: Mapped[bool] = mapped_column(Boolean, default=False)  # 切磋局（不计名望）
    loadout_a_id: Mapped[int | None] = mapped_column(ForeignKey("loadouts.id"), nullable=True)  # 发起方本场奇人快照
    loadout_b_id: Mapped[int | None] = mapped_column(ForeignKey("loadouts.id"), nullable=True)  # 对家本场奇人快照
    guess_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)  # 败方（猜测者）；和局为 None
    guess_text: Mapped[str] = mapped_column(Text, default="")  # 败方最近一次道出的猜测（仅败方可见）
    guess_state: Mapped[str] = mapped_column(String(10), default="none")  # none（未开始）/ guessing（猜词中）/ done（已结束）
    guess_hit: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # 是否全破逆转（仅 done 时有值）
    guess_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # 看破/总数比值（0-1）
    revealed: Mapped[bool] = mapped_column(Boolean, default=False)  # 双方奇术是否已看破
    share_token: Mapped[str | None] = mapped_column(String(32), unique=True, index=True, nullable=True)  # 发起方 A 的传阅令牌（share_token）
    share_token_b: Mapped[str | None] = mapped_column(String(32), unique=True, index=True, nullable=True)  # 对家 B 的传阅令牌（share_token_b）
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class BattleGuess(Base):
    """猜奇术状态（结算时预生成）：赢家实际使用的奇术子集 + 逐卡进度 + 有限猜测次数。

    一张卡对应一门实际使用过的奇术：败方逐次道出猜测，匹配片段上卡、进度累计到
    CRACK_THRESHOLD 即看破该卡（揭示真实奇术）；全部看破 → 胜负逆转。和局无败方不建本行。
    """

    __tablename__ = "battle_guesses"

    battle_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    used_abilities: Mapped[list] = mapped_column(JSON, default=list)  # [{name, effect}] 实际使用子集（服务端保密，前端只见数量）
    cards: Mapped[list] = mapped_column(JSON, default=list)  # [{matched: [str], progress: int, cracked: bool}] 与 used_abilities 同序
    guess_history: Mapped[list] = mapped_column(JSON, default=list)  # 败方每次道出的猜测原文（按提交顺序，双方可见）
    attempts_used: Mapped[int] = mapped_column(Integer, default=0)
    attempts_max: Mapped[int] = mapped_column(Integer, default=5)
    flipped: Mapped[bool] = mapped_column(Boolean, default=False)  # 全破逆转
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
