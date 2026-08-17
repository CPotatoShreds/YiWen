"""对决相关 Pydantic 模型。"""

from datetime import datetime

from pydantic import BaseModel, Field


class GuessCardOut(BaseModel):
    """一张猜词空白卡片：未看破 → 检定给出的「还缺什么」；看破 → 揭示真实奇术。"""

    index: int  # 卡片编号（1 起）
    missing: str = ""  # 最近一次检定指出的「还缺什么」（未看破时展示，看破后为空）
    cracked: bool = False  # 是否已看破
    name: str | None = None  # 看破后揭示的真实奇术名称
    effect: str | None = None  # 看破后揭示的真实奇术效果


class GuessCommentaryItem(BaseModel):
    """一条原子判定：对用户猜测中一个原子片段的四态点评（reason 为内部字段，绝不进前端）。"""

    text: str  # 被单独判定的原子片段（忠实引用用户原文）
    verdict: str  # 四态之一：是 / 否 / 半对 / 不能确定


class GuessCommentaryGroup(BaseModel):
    """一个点评回合对单门的原子判定组（index = 卡序号+1，与 GuessCardOut.index 对齐）。"""

    index: int
    items: list[GuessCommentaryItem] = []


class GuessBlock(BaseModel):
    """单个猜词者视角的猜词面板（和局双方各一，my_guess/opp_guess）。"""

    total: int = 0  # 空白卡片数量（被猜侧实际使用的奇术数）
    cards: list[GuessCardOut] | None = None  # 逐卡状态（未看破卡不带真实奇术）
    history: list[str] = []  # 该猜词者每次提交的猜测原文（按提交顺序，双方可见）
    comments: list[list[GuessCommentaryGroup]] = []  # 与 history 平行：每轮点评 = 逐门原子判定组列表（reason 已剥离）
    attempts_used: int = 0
    attempts_max: int = 200
    verified_round: int | None = None  # 最近一次检定时的点评数（can_verify 判据）
    can_verify: bool = False  # 当前是否可发起检定（自上次检定后又有新点评）
    done: bool = False  # 该行已结束（全破/收手/次数耗尽）
    flipped: bool = False  # 该行全破逆转


class BattleStartIn(BaseModel):
    no_repeat: bool = False  # 启程「不匹配相同对决」：避免与具体配对重复（我方奇人 × 对家奇人）


class BattleOut(BaseModel):
    id: int
    user_a: str  # 异闻师名字（副字；身份/归属判断用）
    user_b: str
    fighter_a: str  # 本场出战的奇人名字（主字；推演与展示用）
    fighter_b: str
    status: str  # pending / done / failed
    winner: str | None  # 胜者异闻师名字
    winner_fighter: str | None = None  # 胜者奇人名字（展示主字）
    story: dict | None  # {narration(上帝,恒过滤), narration_a, narration_b, result, abilities_a, abilities_b}；pending 时 None，叙述/奇术表按查看者过滤
    rank_delta_a: int  # 名望变化（Elo）
    rank_delta_b: int
    share_token: str  # 发起方 A 的传阅令牌（share_token；A 传阅出去即 A 视角）
    share_token_b: str | None = None  # 对家 B 的传阅令牌（share_token_b；B 传阅出去即 B 视角）
    created_at: datetime
    board_entry_id: int | None = None  # 点将局所挑战的榜单刻印（None = 普通对决）
    unlocked: bool = False  # 点将局挑战者已看破该刻印全部奇术（解锁完整三视角）
    can_guess: bool = False  # 当前查看者是否有未结束的猜词行可继续道出猜测
    guessed: bool = False  # 猜词是否已结束（全部猜词行 done）
    guess_hit: bool | None = None  # 是否全破逆转（guessed 后有效）
    guess_score: float | None = None  # 看破/总数比值（0-1）
    guess_by: str | None = None  # 非和局败方（猜词者）异闻师名；和局为 None（双方皆可猜）；前端据此区分 UI
    guess_history: list[str] = []  # 猜词者每次提交的猜测原文（按提交顺序，双方可见）
    guess_comments: list[list[GuessCommentaryGroup]] = []  # 与 guess_history 平行：每轮点评 = 逐门原子判定组列表（仅猜词者可见）
    guess_text: str = ""  # 猜词者最近一次道出的猜测（仅猜词者可见）
    guess_total: int = 0  # 空白卡片数量（被猜侧实际使用的奇术数，仅猜词者可见）
    guess_cards: list[GuessCardOut] | None = None  # 逐卡状态（仅猜词者可见；未看破卡不带真实奇术）
    guess_attempts_used: int = 0  # 已用猜测次数
    guess_attempts_max: int = 200  # 总猜测次数上限（后端硬上限，前端不显式展示）
    can_verify: bool = False  # 当前查看者是否可发起检定（自上次检定后又有新点评）
    revealed: bool = False  # 双方奇术是否已看破
    friendly: bool = False  # 切磋局（不计名望）
    my_guess: GuessBlock | None = None  # 查看者自己的猜词行（和局双方各一；非和局为败方行或 None）
    opp_guess: GuessBlock | None = None  # 对家的猜词行（和局观战用；非和局与 my_guess 同一行）


class GuessIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000, description="猜词者道出的猜测全文（可多次，点评后检定看破）")
