"""奇人榜相关 Pydantic 模型。"""

from datetime import datetime

from pydantic import BaseModel

from app.schemas.battle import BattleOut


class BoardEntryOut(BaseModel):
    id: int
    user: str  # 榜主异闻师名
    name: str  # 奇人姓名（刻印）
    style: str  # 角色介绍（原战斗风格，刻印）
    ability_count: int = 0  # 奇术数（保密，仅展示数量）
    challenge_count: int = 0  # 被点将次数（浏览量）
    win_rate: float | None = None  # 刻印胜率：被挑战场次中刻印胜场占比（无挑战 → None）
    avg_crack_attempts: float | None = None  # 平均每门看破花费的猜测次数（总猜测次数 / 总看破门数；无看破 → None）
    mine: bool = False  # 是否自己的榜单条目（他人条目可发起挑战）
    cracked: bool = False  # 当前查看者是否已看破该刻印全部奇术（榜单/详情对挑战者展示）
    created_at: datetime


class BoardAbilityOut(BaseModel):
    """刻印单门奇术的进度卡：已看破 → 亮出真实名/效果；未看破 → 最近检定给出的「还缺什么」，保密。"""

    index: int  # 第几门（1 起）
    cracked: bool = False  # 查看者是否已看破（榜主视角全亮）
    missing: str = ""  # 最近一次检定指出的「还缺什么」（未看破时展示，追踪进度）
    name: str | None = None  # 已看破才下发
    effect: str | None = None  # 已看破才下发


class BoardChallengerOut(BaseModel):
    """榜主追踪：某刻印的挑战者摘要。"""

    user_id: int
    username: str
    total_guesses: int = 0  # 累计猜词次数（guess_log 条数）
    cracked: int = 0  # 已看破门数
    total: int = 0  # 该刻印门数（供「已看破 X/Z」）


class GuessPathRecordOut(BaseModel):
    """榜主追踪：挑战者对某刻印的单条猜词记录。"""

    battle_id: int  # 对应战报（榜主己方视角打开）
    round: int  # 本场内第几次猜测（1 起）
    text: str  # 提交的猜测原文
    commentary: str = ""  # 该次猜测得到的点评文本
    cracked_after: int = 0  # 截至目前已看破门数
    at: str = ""  # 发生时间（ISO）


class BoardDetailOut(BoardEntryOut):
    """条目详情：查看者（挑战者）视角的看破进度 + 与该刻印的对战记录。

    榜主（mine=True）看刻印全貌 + 全部挑战局行迹（掩码猜词）；挑战者看自己的点将局。
    """

    progress: list[BoardAbilityOut] = []  # 按 entry.abilities 全量下标对齐
    battles: list[BattleOut] = []  # 榜主视角全部挑战局；挑战者视角自己的点将局（倒序）



class BoardEntryIn(BaseModel):
    loadout_id: int  # 要上榜的奇人（需归属本人且装有 ≥1 奇术）


class BoardChallengeIn(BaseModel):
    loadout_id: int  # 点将：挑战者自己已解封且装奇术的出战奇人
