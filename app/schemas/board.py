"""奇人榜相关 Pydantic 模型。"""

from datetime import datetime

from pydantic import BaseModel


class BoardEntryOut(BaseModel):
    id: int
    user: str  # 榜主异闻师名
    name: str  # 奇人姓名（刻印）
    style: str  # 战斗风格（刻印）
    ability_count: int = 0  # 奇术数（保密，仅展示数量）
    mine: bool = False  # 是否自己的榜单条目（他人条目可发起挑战）
    created_at: datetime


class BoardEntryIn(BaseModel):
    loadout_id: int  # 要上榜的奇人（需归属本人且装有 ≥1 奇术）


class BoardChallengeIn(BaseModel):
    loadout_id: int  # 点将：挑战者自己已解封且装奇术的出战奇人
