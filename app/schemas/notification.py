"""通知相关 Pydantic 模型。"""

from datetime import datetime

from pydantic import BaseModel, computed_field


class NotificationOut(BaseModel):
    id: int
    type: str  # board_challenge / battle_report / guess_progress
    title: str
    body: str
    ref_type: str | None  # battle / board（跳转目标）
    ref_id: int | None
    read_at: datetime | None  # 空 = 未读
    created_at: datetime

    model_config = {"from_attributes": True}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def read(self) -> bool:
        return self.read_at is not None


class NotificationList(BaseModel):
    items: list[NotificationOut]  # 近 30 条倒序
    unread: int  # 未读总数（角标）
