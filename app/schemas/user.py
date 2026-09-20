"""异闻师相关 Pydantic 模型。"""

from datetime import datetime

from pydantic import BaseModel, Field

_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class UserRegister(BaseModel):
    username: str = Field(min_length=2, max_length=20, description="异闻师名号")
    email: str = Field(min_length=5, max_length=255, pattern=_EMAIL_PATTERN, description="邮箱（找回密码凭证，注册不验证）")
    password: str = Field(min_length=6, max_length=64, description="口令")


class UserLogin(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    email: str | None = None
    is_admin: bool  # 管理员：可登录后台
    created_at: datetime

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    refresh_token: str | None = None  # Bearer 客户端用；Cookie 会话下由 httponly cookie 承载
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255, pattern=_EMAIL_PATTERN)


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=6, max_length=64)


class BindEmailRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255, pattern=_EMAIL_PATTERN)


class VerifyEmailRequest(BaseModel):
    token: str


class DeleteAccountRequest(BaseModel):
    password: str = Field(min_length=1, max_length=64, description="确认口令")
