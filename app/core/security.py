"""认证：密码哈希（bcrypt）与 JWT。

- 密码用 bcrypt 直接哈希（不用 passlib，避免停维护的兼容问题）。
- JWT 用 PyJWT，sub 携带 user_id。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.base import get_db
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def hash_password_sync(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password_sync(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


async def hash_password(password: str) -> str:
    """bcrypt 单次约 0.2s 纯 CPU；其 Rust/C 实现释放 GIL，扔线程池后不阻塞事件循环
    （实测 4 并发加速 3.8x），100 人同时登录也不再冻结全站请求。"""
    return await asyncio.to_thread(hash_password_sync, password)


async def verify_password(plain: str, hashed: str) -> bool:
    return await asyncio.to_thread(verify_password_sync, plain, hashed)


def create_access_token(user_id: int) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


async def get_current_user(
    request: Request,
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效或过期的凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = token or request.cookies.get(settings.AUTH_COOKIE_NAME)
    if not token:
        raise credentials_exc
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id = int(payload.get("sub"))  # type: ignore[arg-type]
    except (jwt.PyJWTError, ValueError, TypeError):
        raise credentials_exc
    user = await db.get(User, user_id)
    if user is None or user.deleted_at is not None:  # 注销账号的残留 token 一律拒绝
        raise credentials_exc
    return user


async def get_current_admin(current: Annotated[User, Depends(get_current_user)]) -> User:
    """后台专用依赖：非管理员一律 403。"""
    if not current.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return current
