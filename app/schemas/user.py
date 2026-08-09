"""异闻师相关 Pydantic 模型。"""

from datetime import datetime

from pydantic import BaseModel, Field


class UserRegister(BaseModel):
    username: str = Field(min_length=2, max_length=20, description="异闻师名号")
    password: str = Field(min_length=6, max_length=64, description="口令")


class UserLogin(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    exp: int  # 见闻：唯一养成属性
    rank_points: int  # 名望：天梯分
    max_loadouts: int  # 按见闻解锁的奇人槽位上限
    reveal_on_miss: bool  # 对家猜奇术未中时是否看破我的奇术
    is_admin: bool  # 管理员：可登录后台
    created_at: datetime

    model_config = {"from_attributes": True}


class SettingsIn(BaseModel):
    reveal_on_miss: bool = False


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
