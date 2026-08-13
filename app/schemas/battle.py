"""对决相关 Pydantic 模型。"""

from datetime import datetime

from pydantic import BaseModel, Field


class GuessCardOut(BaseModel):
    """一张猜词空白卡片：已匹配片段 + 是否看破（看破即揭示真实奇术）。"""

    index: int  # 卡片编号（1 起）
    matched: list[str] = []  # 已贴到该卡的败方片段
    cracked: bool = False  # 是否已看破
    name: str | None = None  # 看破后揭示的真实奇术名称
    effect: str | None = None  # 看破后揭示的真实奇术效果


class GuessBlock(BaseModel):
    """单个猜词者视角的猜词面板（和局双方各一，my_guess/opp_guess）。"""

    total: int = 0  # 空白卡片数量（被猜侧实际使用的奇术数）
    cards: list[GuessCardOut] | None = None  # 逐卡状态（未看破卡不带真实奇术）
    history: list[str] = []  # 该猜词者每次提交的猜测原文（按提交顺序，双方可见）
    attempts_used: int = 0
    attempts_max: int = 5
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
    story: dict | None  # {narration(上帝,恒过滤), narration_a, narration_b, result, abilities_a, abilities_b, insight_a, insight_b}；pending 时 None，叙述/奇术表/解读按查看者过滤
    rank_delta_a: int  # 名望变化（Elo）
    rank_delta_b: int
    share_token: str  # 发起方 A 的传阅令牌（share_token；A 传阅出去即 A 视角）
    share_token_b: str | None = None  # 对家 B 的传阅令牌（share_token_b；B 传阅出去即 B 视角）
    created_at: datetime
    can_guess: bool = False  # 当前查看者是否有未结束的猜词行可继续道出猜测
    guessed: bool = False  # 猜词是否已结束（全部猜词行 done）
    guess_hit: bool | None = None  # 是否全破逆转（guessed 后有效）
    guess_score: float | None = None  # 看破/总数比值（0-1）
    guess_by: str | None = None  # 非和局败方（猜词者）异闻师名；和局为 None（双方皆可猜）；前端据此区分 UI
    guess_history: list[str] = []  # 猜词者每次提交的猜测原文（按提交顺序，双方可见）
    guess_text: str = ""  # 猜词者最近一次道出的猜测（仅猜词者可见）
    guess_total: int = 0  # 空白卡片数量（被猜侧实际使用的奇术数，仅猜词者可见）
    guess_cards: list[GuessCardOut] | None = None  # 逐卡状态（仅猜词者可见；未看破卡不带真实奇术）
    guess_attempts_used: int = 0  # 已用猜测次数
    guess_attempts_max: int = 5  # 总猜测次数上限
    revealed: bool = False  # 双方奇术是否已看破
    friendly: bool = False  # 切磋局（不计名望）
    my_guess: GuessBlock | None = None  # 查看者自己的猜词行（和局双方各一；非和局为败方行或 None）
    opp_guess: GuessBlock | None = None  # 对家的猜词行（和局观战用；非和局与 my_guess 同一行）


class GuessIn(BaseModel):
    text: str = Field(min_length=1, max_length=300, description="猜词者道出的猜测（可多次，命中内容上卡）")
