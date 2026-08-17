"""后台对战试验场数据模型：纯测试，对玩家面完全隔离。

TestUser 是后台一键生成/持久化的测试账号（无密码）；TestLoadout / TestLoadoutAbility
持久保存试验场奇人（每奇人自动绑定一个 TestUser）；TestBattle / TestBattleGuess
复刻 Battle / BattleGuess 的字段，但只落 test_* 表——绝不写入 battles / battle_guesses，
不触发玩家 Elo/见闻结算。管理员用它反复测试对战与猜词，不污染任何玩家数据。
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TestUser(Base):
    """测试账号：后台一键生成/持久化的对战对手（无密码、不登录）。"""

    __tablename__ = "test_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    exp: Mapped[int] = mapped_column(Integer, default=0)  # 见闻（测试域内结算用）
    rank_points: Mapped[int] = mapped_column(Integer, default=1000)  # 名望（测试域内 Elo）
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TestLoadout(Base):
    """持久测试奇人：管理员勾选奇术自动生成，自动绑定一个测试账号（名字随机、风格空）。"""

    __tablename__ = "test_loadouts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("test_users.id"), index=True)  # 自动绑定账号
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True)  # 词库生成，唯一（碰撞重抽）
    style: Mapped[str] = mapped_column(Text, server_default="")  # 需求：恒空
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TestLoadoutAbility(Base):
    """测试奇人的装配奇术（join 表，复刻 LoadoutAbility）。"""

    __tablename__ = "test_loadout_abilities"

    loadout_id: Mapped[int] = mapped_column(ForeignKey("test_loadouts.id"), primary_key=True)
    ability_id: Mapped[str] = mapped_column(ForeignKey("abilities.id"), primary_key=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TestBattle(Base):
    """测试行迹：一场试验场对决的结果与猜词状态（只落 test_*，不影响玩家对战）。"""

    __tablename__ = "test_battles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_a_id: Mapped[int] = mapped_column(ForeignKey("test_users.id"))
    user_b_id: Mapped[int] = mapped_column(ForeignKey("test_users.id"))
    winner_id: Mapped[int | None] = mapped_column(ForeignKey("test_users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(10), server_default="done")  # pending 推演中 / done / failed
    story: Mapped[str] = mapped_column(Text, default="")  # JSON：{narration, narration_a, narration_b, result, abilities_a, abilities_b}
    rank_delta_a: Mapped[int] = mapped_column(Integer, default=0)
    rank_delta_b: Mapped[int] = mapped_column(Integer, default=0)
    loadout_a_name: Mapped[str] = mapped_column(Text, default="")  # 双方奇人名字快照（只存名，不存玩家 Loadout 引用）
    loadout_b_name: Mapped[str] = mapped_column(Text, default="")
    guess_by: Mapped[int | None] = mapped_column(ForeignKey("test_users.id"), nullable=True)
    guess_state: Mapped[str] = mapped_column(String(10), default="none")
    guess_hit: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    guess_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    revealed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TestBattleGuess(Base):
    """测试猜词状态：复刻 BattleGuess，只作用于 test_battles。"""

    __tablename__ = "test_battle_guesses"

    battle_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    used_abilities: Mapped[list] = mapped_column(JSON, default=list)  # [{name, effect}]
    cards: Mapped[list] = mapped_column(JSON, default=list)  # [{cracked, missing, cracked_round, verifies}]
    guess_history: Mapped[list] = mapped_column(JSON, default=list)
    comments: Mapped[list] = mapped_column(JSON, default=list)  # 与 guess_history 平行：点评文本
    attempts_used: Mapped[int] = mapped_column(Integer, default=0)
    attempts_max: Mapped[int] = mapped_column(Integer, default=200)
    verified_round: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 最近一次检定时的点评数（can_verify 判据）
    flipped: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
