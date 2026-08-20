"""认证路由：注册 / 登录 / 当前用户。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, get_current_user, hash_password, verify_password
from app.db.base import get_db
from app.models.user import User
from app.schemas.user import SettingsIn, Token, UserLogin, UserOut, UserRegister
from app.services.battle import economy

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(body: UserRegister, db: Annotated[AsyncSession, Depends(get_db)]) -> User:
    exists = await db.execute(select(User).where(User.username == body.username))
    if exists.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已被占用")
    user = User(username=body.username, password_hash=hash_password(body.password))
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        # 并发同名注册：先查后插有竞态，唯一索引兜底（前端预检之外的并发窗口）
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已被占用")
    await db.refresh(user)
    return user


@router.post("/login", response_model=Token)
async def login(
    body: UserLogin,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Token:
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    economy.apply_daily_login(user)  # 每日开张：+10 见闻
    await db.commit()
    access_token = create_access_token(user.id)
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
    )
    await db.refresh(user)
    return Token(access_token=access_token, token_type="bearer")


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    response.delete_cookie(
        settings.AUTH_COOKIE_NAME,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
    )


@router.get("/me", response_model=UserOut)
async def me(
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """当前用户；每日首次访问自动开张（+10 见闻）。"""
    economy.apply_daily_login(current)
    await db.commit()
    return current


@router.put("/settings", response_model=UserOut)
async def update_settings(
    body: SettingsIn,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """更新个人设置：对家猜奇术未中时是否看破我的奇术。"""
    current.reveal_on_miss = body.reveal_on_miss
    await db.commit()
    await db.refresh(current)
    return current
