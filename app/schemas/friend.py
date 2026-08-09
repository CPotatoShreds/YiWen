"""故人相关 Pydantic 模型。"""

from pydantic import BaseModel


class FriendRequest(BaseModel):
    friend_id: int


class FriendOut(BaseModel):
    id: int
    username: str
    status: str  # pending / accepted
