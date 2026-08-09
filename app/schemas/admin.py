"""后台管理相关 Pydantic 模型。"""

from datetime import datetime

from pydantic import BaseModel, Field


class AdminUserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=20)
    password: str = Field(min_length=6, max_length=64)
    is_admin: bool = False
    exp: int = Field(default=0, ge=0)
    rank_points: int = Field(default=1000)
    reveal_on_miss: bool = False


class AdminUserUpdate(BaseModel):
    """全部可空：None = 保持不变。"""

    username: str | None = Field(default=None, min_length=2, max_length=20)
    password: str | None = Field(default=None, min_length=6, max_length=64)
    exp: int | None = Field(default=None, ge=0)
    rank_points: int | None = None
    reveal_on_miss: bool | None = None
    is_admin: bool | None = None


class AdminUserOut(BaseModel):
    id: int
    username: str
    exp: int
    rank_points: int
    reveal_on_miss: bool
    is_admin: bool
    last_login_date: str | None = None
    last_battle_date: str | None = None
    created_at: datetime
    loadout_count: int = 0  # 奇人数
    ability_count: int = 0  # 奇术数
    battle_count: int = 0  # 参与行迹数


class AbilityAdminIn(BaseModel):
    name: str = Field(max_length=50)
    effect: str = Field(max_length=500)
    detail: str | None = Field(default=None, max_length=1000)
    tactic: str | None = Field(default=None, max_length=500)
    owner_id: int | None = Field(default=None, description="挂到指定异闻师名下（可选）")


class AdminBattleOut(BaseModel):
    """管理员视角：story 返回完整未过滤 JSON（含上帝视角与双方奇术表）。"""

    id: int
    user_a: str | None = None  # 异闻师名（可能已删，兜底 None）
    user_b: str | None = None
    winner: str | None = None
    status: str
    friendly: bool
    story: dict | None = None
    rank_delta_a: int
    rank_delta_b: int
    loadout_a_id: int | None = None
    loadout_b_id: int | None = None
    guess_by: str | None = None
    guess_state: str
    guess_hit: bool | None = None
    guess_score: float | None = None
    revealed: bool
    share_token: str | None = None
    share_token_b: str | None = None
    created_at: datetime


class AdminLoadoutOut(BaseModel):
    id: int
    user_id: int
    username: str | None = None
    name: str
    style: str
    enabled: bool
    tactic: str
    ability_count: int = 0
    created_at: datetime


class FriendshipRowOut(BaseModel):
    user_id: int
    friend_id: int
    user: str | None = None  # 发起方名
    friend: str | None = None  # 接收方名
    status: str
    created_at: datetime


class RequestLogOut(BaseModel):
    id: int
    method: str
    path: str
    status_code: int
    duration_ms: int
    user_id: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class RecentBattle(BaseModel):
    id: int
    user_a: str | None = None
    user_b: str | None = None
    winner: str | None = None
    status: str
    friendly: bool
    created_at: datetime


class StatsOut(BaseModel):
    total_users: int
    total_abilities: int
    total_loadouts: int
    total_battles: int
    battles_pending: int
    battles_done: int
    battles_failed: int
    recent_battles: list[RecentBattle]


class DailyPoint(BaseModel):
    date: str  # YYYY-MM-DD
    count: int


class EndpointStat(BaseModel):
    path: str  # 数字段已归一化为 {id}
    count: int
    avg_ms: float


class TrafficOut(BaseModel):
    total_requests: int
    last_24h: int
    avg_ms: float
    daily: list[DailyPoint]  # 近 7 日，旧→新
    endpoints: list[EndpointStat]  # TOP 12
    recent: list[RequestLogOut]  # 最近 50 条
