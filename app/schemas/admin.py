"""后台管理相关 Pydantic 模型。"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.ability import AbilityOut
from app.schemas.battle import GuessCommentaryGroup


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
    name: str = Field(max_length=10)
    effect: str = Field(max_length=50)
    detail: str | None = Field(default=None, max_length=500)
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
    guess_history: list[str] = []
    guess_total: int = 0
    guess_cards: list[dict] | None = None
    guess_attempts_used: int = 0
    guess_attempts_max: int = 200
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
    battle_count: int = 0
    abilities: list[AbilityOut] = []
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


# ---------- 对战试验场 ----------


class TestUserOut(BaseModel):
    id: int
    username: str
    exp: int
    rank_points: int
    created_at: datetime


class TestUserCreate(BaseModel):
    username: str | None = Field(default=None, min_length=2, max_length=20)  # 缺省用词库自动起名
    exp: int = Field(default=0, ge=0)
    rank_points: int = Field(default=1000)


class TestFighterIn(BaseModel):
    """一侧奇人：持久测试奇人按 test_loadout_id 读装配（优先），或玩家奇人按 loadout_id，
    或临时奇人内联 name + abilities。

    三选一：test_loadout_id → loadout_id → name/abilities 内联（兼容保留，UI 不再产生）。
    """

    test_loadout_id: int | None = Field(default=None, description="持久测试奇人 id（优先，绑定账号随奇人）")
    loadout_id: int | None = Field(default=None, description="玩家奇人 id（兼容保留）")
    name: str | None = Field(default=None, max_length=20, description="临时奇人名（loadout_id 为空时必填）")
    style: str = ""
    abilities: list[str] = Field(default_factory=list, description="临时奇人的奇术 id 列表（loadout_id 为空时必填）")
    owner: str | None = Field(default=None, max_length=20, description="测试账号名；缺省用默认测试账号")


class TestBattleStartIn(BaseModel):
    """真实推演：两个奇人 + 可各自挂到测试账号。"""

    fighter_a: TestFighterIn
    fighter_b: TestFighterIn


class TestSkipIn(BaseModel):
    """指定胜负（跳过对战）：零 LLM，直接进猜词阶段。"""

    fighter_a: TestFighterIn
    fighter_b: TestFighterIn
    winner: str = Field(description='"A" / "B" / "draw"')


class TestGuessIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class TestReportOut(BaseModel):
    """仅生成战前讨论报告（不推演、不落库）的输出。"""

    report: str


class TestLoadoutCreateIn(BaseModel):
    """生成持久测试奇人：只选奇术，名字随机、风格空、账号自动绑定。"""

    abilities: list[str] = Field(min_length=1, description="奇术 id 列表（须存在于奇术库）")


class TestLoadoutOut(BaseModel):
    """持久测试奇人（含绑定测试账号名与装配奇术）。"""

    id: int
    user_id: int
    username: str | None = None
    name: str
    style: str
    abilities: list[AbilityOut]


class TestGuessVerifyOut(BaseModel):
    """一次检定对某卡的结论（看破 / 未看破 + 还缺什么）。"""

    round: int
    cracked: bool
    missing: str = ""


class TestGuessCardOut(BaseModel):
    """试验场单门奇术的进度卡：已看破 → 亮出真实名/效果；未看破 → 最近检定给出的「还缺什么」。"""

    index: int
    missing: str = ""
    cracked: bool = False
    cracked_round: int | None = None
    verifies: list[TestGuessVerifyOut] = []
    name: str | None = None
    effect: str | None = None


class TestBattleOut(BaseModel):
    id: int
    user_a: str
    user_b: str
    fighter_a: str
    fighter_b: str
    status: str
    winner: str | None = None
    winner_fighter: str | None = None
    story: dict | None = None
    rank_delta_a: int
    rank_delta_b: int
    guess_by: str | None = None
    guess_state: str
    guess_hit: bool | None = None
    guess_score: float | None = None
    revealed: bool
    guess_history: list[str] = []
    comments: list[list[GuessCommentaryGroup]] = []  # 与 guess_history 平行：每轮点评 = 逐门原子判定组列表（reason 已剥离）
    guess_total: int = 0
    guess_cards: list[TestGuessCardOut] | None = None
    guess_attempts_used: int = 0
    guess_attempts_max: int = 200
    verified_round: int | None = None  # 最近一次检定时的点评数（can_verify 判据）
    can_verify: bool = False  # 当前是否可发起检定（自上次检定后又有新点评）
    created_at: datetime


# ---------- LLM 链路追踪 ----------


class LlmTraceOut(BaseModel):
    id: int
    kind: str
    operation: str
    status: str
    trace_id: str | None = None
    error: str | None = None
    latency_ms: int
    tokens_input: int
    tokens_output: int
    created_at: datetime

    model_config = {"from_attributes": True}


class LlmTraceDetailOut(LlmTraceOut):
    request_json: object | None = None
    response_json: object | None = None


class LlmTraceOpStat(BaseModel):
    operation: str
    count: int
    fail_count: int
    avg_ms: float


class LlmTraceStatsOut(BaseModel):
    total: int
    fail_total: int
    by_operation: list[LlmTraceOpStat]


# ---------- 提示词方案调试 ----------


class PromptSchemeOut(BaseModel):
    id: int
    name: str
    description: str
    enabled: bool
    discuss_prompt: str | None = None
    deduce_prompt: str | None = None
    transcribe_prompt: str | None = None
    validate_prompt: str | None = None
    repair_prompt: str | None = None
    usage_prompt: str | None = None
    guess_pair_prompt: str | None = None
    guess_verify_prompt: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PromptSchemeIn(BaseModel):
    """新建/更新方案：name 必填，各环节提示词 None = 用冻结默认。"""

    name: str = Field(min_length=1, max_length=50)
    description: str = ""
    enabled: bool = True
    discuss_prompt: str | None = None
    deduce_prompt: str | None = None
    transcribe_prompt: str | None = None
    validate_prompt: str | None = None
    repair_prompt: str | None = None
    usage_prompt: str | None = None
    guess_pair_prompt: str | None = None
    guess_verify_prompt: str | None = None


class PromptSchemeUpdate(BaseModel):
    """更新方案：全部可空，None = 保持不变（与 PromptSchemeIn 区别：name 也可不改）。"""

    name: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = None
    enabled: bool | None = None
    discuss_prompt: str | None = None
    deduce_prompt: str | None = None
    transcribe_prompt: str | None = None
    validate_prompt: str | None = None
    repair_prompt: str | None = None
    usage_prompt: str | None = None
    guess_pair_prompt: str | None = None
    guess_verify_prompt: str | None = None


class RerunIn(BaseModel):
    scheme_id: int


class PromptDebugRunOut(BaseModel):
    id: int
    battle_id: int
    scheme_id: int
    scheme_name: str | None = None
    status: str
    error: str | None = None
    story: dict | None = None
    discuss_report: str = ""
    winner_side: str | None = None
    created_at: datetime


