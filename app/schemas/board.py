"""奇人榜相关 Pydantic 模型。"""

from datetime import datetime

from pydantic import BaseModel

from app.schemas.battle import BattleOut


class BoardEntryOut(BaseModel):
    id: int
    user: str  # 榜主异闻师名
    name: str  # 奇人姓名（刻印）
    style: str  # 战斗风格（刻印）
    ability_count: int = 0  # 奇术数（保密，仅展示数量）
    challenge_count: int = 0  # 被点将次数（浏览量，榜主只看得到聚合数）
    mine: bool = False  # 是否自己的榜单条目（他人条目可发起挑战）
    created_at: datetime


class BoardAbilityOut(BaseModel):
    """刻印单门奇术的进度卡：已看破 → 亮出真实名/效果；未看破 → 仅线索片段，保密。"""

    index: int  # 第几门（1 起）
    cracked: bool = False  # 查看者是否已看破（榜主视角全亮）
    matched: list[str] = []  # 已积累的猜测线索片段（未看破时展示，追踪进度）
    name: str | None = None  # 已看破才下发
    effect: str | None = None  # 已看破才下发


class BoardDetailOut(BoardEntryOut):
    """条目详情：查看者（挑战者）视角的看破进度 + 与该刻印的对战记录。

    榜主（mine=True）看刻印全貌、无任何挑战者行迹（battles 恒空，发帖语义）。
    """

    progress: list[BoardAbilityOut] = []  # 按 entry.abilities 全量下标对齐
    battles: list[BattleOut] = []  # 仅查看者自己的点将局（倒序）



class BoardEntryIn(BaseModel):
    loadout_id: int  # 要上榜的奇人（需归属本人且装有 ≥1 奇术）


class BoardChallengeIn(BaseModel):
    loadout_id: int  # 点将：挑战者自己已解封且装奇术的出战奇人
