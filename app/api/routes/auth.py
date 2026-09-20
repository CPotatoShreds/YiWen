"""认证路由：注册 / 登录 / 刷新 / 登出 / 当前用户 / 邮箱 / 注销与导出。

凭证模型（2026-09-12 P0.3）：短时 access（2h，JWT）+ 长期 refresh（30 天，
服务端存 sha256 哈希，每次刷新旋转）。refresh 泄露窗口与吊销能力由此获得；
旧 access 在剩余有效期内仍可用属已知残留窗口，换取无状态校验。

错误约定（P2.2）：认证域业务错误抛 AppError（{detail, code} + X-Error-Code 头），
前端按 code 分支。
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from redis.exceptions import RedisError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.core.logger import get_logger
from app.core.ratelimit import limiter
from app.core.redis import get_redis
from app.core.security import create_access_token, get_current_user, hash_password, verify_password
from app.db.base import get_db
from app.models.ability import Ability
from app.models.character import Character, CharacterAbility
from app.models.refresh_token import RefreshToken
from app.models.scenario_domain import ScenarioChallengeRun, ScenarioRosterProgress
from app.models.user import User
from app.schemas.user import (
    BindEmailRequest,
    DeleteAccountRequest,
    ForgotPasswordRequest,
    RefreshRequest,
    ResetPasswordRequest,
    Token,
    UserLogin,
    UserOut,
    UserRegister,
    VerifyEmailRequest,
)
from app.services.mail import send_email

router = APIRouter(prefix="/auth", tags=["auth"])

logger = get_logger("auth")

_REFRESH_COOKIE_PATH = "/api/auth"  # 限制刷新令牌仅随认证端点出站
_LOGIN_FAIL_LIMIT = 5  # 同一用户名连续失败 N 次后锁定
_LOGIN_LOCK_SECONDS = 900
_EMAIL_TOKEN_MAX_AGE = 900  # 邮件链接令牌 15 分钟

_serializer = URLSafeTimedSerializer(settings.SECRET_KEY, salt="ynfight-email")


def _make_email_token(payload: dict) -> str:
    return _serializer.dumps(payload)


def _load_email_token(token: str) -> dict:
    try:
        return _serializer.loads(token, max_age=_EMAIL_TOKEN_MAX_AGE)
    except (BadSignature, SignatureExpired) as exc:
        raise AppError("AUTH_LINK_INVALID", "链接无效或已过期") from exc


def _login_fail_key(username: str) -> str:
    return f"login:fail:{username}"


async def _login_locked(username: str) -> bool:
    """用户名级失败锁定；Redis 不可用时放行（仍有 IP 限流兜底）。"""
    try:
        count = await get_redis().get(_login_fail_key(username))
        return int(count or 0) >= _LOGIN_FAIL_LIMIT
    except (RedisError, OSError, TimeoutError):
        return False


async def _record_login_failure(username: str) -> None:
    try:
        redis = get_redis()
        count = await redis.incr(_login_fail_key(username))
        if count == 1:
            await redis.expire(_login_fail_key(username), _LOGIN_LOCK_SECONDS)
    except (RedisError, OSError, TimeoutError):
        pass


async def _clear_login_failures(username: str) -> None:
    try:
        await get_redis().delete(_login_fail_key(username))
    except (RedisError, OSError, TimeoutError):
        pass


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
    )
    response.set_cookie(
        key=settings.AUTH_REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path=_REFRESH_COOKIE_PATH,
    )


async def _issue_refresh_token(db: AsyncSession, user_id: int) -> str:
    token = secrets.token_urlsafe(48)
    db.add(RefreshToken(
        user_id=user_id,
        token_hash=_hash_refresh_token(token),
        expires_at=_now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    ))
    await db.commit()
    return token


async def _load_refresh_token(db: AsyncSession, token: str | None) -> RefreshToken | None:
    if not token:
        return None
    return (await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == _hash_refresh_token(token))
    )).scalar_one_or_none()


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.RATELIMIT_REGISTER)
async def register(request: Request, body: UserRegister, db: Annotated[AsyncSession, Depends(get_db)]) -> User:
    """注册：邮箱必填但不做验证（找回密码凭证）；换绑/更正邮箱走验证流程。"""
    taken_username = (await db.execute(select(User.id).where(User.username == body.username))).scalar_one_or_none()
    if taken_username is not None:
        raise AppError("AUTH_USERNAME_TAKEN", "用户名已被占用")
    taken_email = (await db.execute(select(User.id).where(User.email == body.email))).scalar_one_or_none()
    if taken_email is not None:
        raise AppError("AUTH_EMAIL_TAKEN", "邮箱已被占用")
    user = User(username=body.username, email=body.email, password_hash=await hash_password(body.password))
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        # 并发注册：先查后插有竞态，唯一索引兜底（无法区分哪个约束，给合并文案）
        await db.rollback()
        raise AppError("AUTH_REGISTER_CONFLICT", "用户名或邮箱已被占用")
    await db.refresh(user)
    return user


@router.post("/login", response_model=Token)
@limiter.limit(settings.RATELIMIT_LOGIN)
async def login(
    request: Request,
    body: UserLogin,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Token:
    if await _login_locked(body.username):
        raise AppError("AUTH_LOCKED", "失败次数过多，请 15 分钟后再试", status.HTTP_429_TOO_MANY_REQUESTS)
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()
    if user is not None and user.deleted_at is not None:
        # 先于口令校验：注销后口令已随机化，永远过不了校验（用户名本就游戏内公开，泄露面可接受）
        raise AppError("AUTH_ACCOUNT_DELETED", "该账号已注销", status.HTTP_401_UNAUTHORIZED)
    if user is None or not await verify_password(body.password, user.password_hash):
        await _record_login_failure(body.username)
        raise AppError("AUTH_INVALID_CREDENTIALS", "用户名或密码错误", status.HTTP_401_UNAUTHORIZED)
    await _clear_login_failures(body.username)
    access_token = create_access_token(user.id)
    refresh_token = await _issue_refresh_token(db, user.id)
    _set_auth_cookies(response, access_token, refresh_token)
    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=Token)
async def refresh(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    body: RefreshRequest | None = None,
) -> Token:
    """旋转刷新令牌：旧令牌作废、签发新对。已旋转令牌再次出现按泄露处理，全量吊销。"""
    token = (body.refresh_token if body else None) or request.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)
    row = await _load_refresh_token(db, token)
    if row is None:
        raise AppError("AUTH_SESSION_EXPIRED", "登录状态已过期，请重新登录", status.HTTP_401_UNAUTHORIZED)
    now = _now()
    if row.revoked_at is not None or row.expires_at < now:
        if row.revoked_at is not None:
            # 已旋转令牌再次出现：按泄露处理，撤销该用户全部刷新令牌
            await db.execute(
                update(RefreshToken)
                .where(RefreshToken.user_id == row.user_id, RefreshToken.revoked_at.is_(None))
                .values(revoked_at=now)
            )
            await db.commit()
        raise AppError("AUTH_SESSION_EXPIRED", "登录状态已过期，请重新登录", status.HTTP_401_UNAUTHORIZED)
    user_id = row.user_id
    row.revoked_at = now  # 旋转：旧令牌立即作废（与签发新令牌同一事务提交）
    access_token = create_access_token(user_id)
    refresh_token = await _issue_refresh_token(db, user_id)
    _set_auth_cookies(response, access_token, refresh_token)
    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    body: RefreshRequest | None = None,
) -> None:
    token = (body.refresh_token if body else None) or request.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)
    row = await _load_refresh_token(db, token)
    if row is not None and row.revoked_at is None:
        row.revoked_at = _now()
        await db.commit()
    response.delete_cookie(
        settings.AUTH_COOKIE_NAME, httponly=True,
        secure=settings.auth_cookie_secure, samesite="lax",
    )
    response.delete_cookie(
        settings.AUTH_REFRESH_COOKIE_NAME, path=_REFRESH_COOKIE_PATH, httponly=True,
        secure=settings.auth_cookie_secure, samesite="lax",
    )


@router.get("/me", response_model=UserOut)
async def me(current: Annotated[User, Depends(get_current_user)]) -> User:
    """当前用户。"""
    return current


@router.get("/me/export")
async def export_me(
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """个人数据导出（P3）：可携带数据以 JSON 附件形式下载。"""
    abilities = (await db.scalars(select(Ability).where(Ability.owner_id == current.id).order_by(Ability.created_at))).all()
    characters = (await db.scalars(select(Character).where(Character.owner_id == current.id).order_by(Character.created_at))).all()
    char_links = (await db.scalars(select(CharacterAbility).where(CharacterAbility.character_id.in_([c.id for c in characters] or [None])))).all()
    challenges = (await db.scalars(select(ScenarioChallengeRun).where(ScenarioChallengeRun.challenger_id == current.id).order_by(ScenarioChallengeRun.created_at))).all()
    progresses = (await db.scalars(select(ScenarioRosterProgress).where(ScenarioRosterProgress.challenger_id == current.id))).all()

    def _iso(value):
        return value.isoformat() if value is not None else None

    payload = {
        "exported_at": _now().isoformat(),
        "profile": {"id": current.id, "username": current.username, "email": current.email,
                    "role": current.role, "created_at": _iso(current.created_at)},
        "abilities": [{"id": str(a.id), "name": a.name, "effect": a.effect, "detail": a.detail,
                       "understanding": a.understanding, "created_at": _iso(a.created_at)} for a in abilities],
        "characters": [{"id": str(c.id), "name": c.name, "bio": c.bio,
                        "ability_ids": [str(link.ability_id) for link in char_links if link.character_id == c.id],
                        "created_at": _iso(c.created_at)} for c in characters],
        "challenges": [{"id": str(ch.id), "roster_id": str(ch.roster_id), "status": ch.status,
                        "challenge_number": ch.challenge_number, "is_preview": ch.is_preview,
                        "won": ch.won, "created_at": _iso(ch.created_at),
                        "messages": ch.messages, "guesses": ch.guesses} for ch in challenges],
        "roster_progress": [{"roster_id": str(p.roster_id), "attempts": p.attempts,
                             "guess_credits": p.guess_credits, "guess_history": p.guess_history} for p in progresses],
    }
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": 'attachment; filename="ynfight_export.json"'},
    )


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(
    body: DeleteAccountRequest,
    current: Annotated[User, Depends(get_current_user)],
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """账号注销（P3）：软删 + 匿名化。创作内容保留但归属显示为已注销。"""
    if not await verify_password(body.password, current.password_hash):
        raise AppError("AUTH_INVALID_CREDENTIALS", "口令错误，账号未注销", status.HTTP_403_FORBIDDEN)
    # 匿名化：用户名以 id 兜底保证唯一，展示层呈现为"已注销_xxxxxx"
    current.username = f"已注销_{current.id:06d}"
    current.email = None
    current.password_hash = await hash_password(secrets.token_urlsafe(32))
    current.deleted_at = _now()
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == current.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
    await db.commit()
    response.delete_cookie(
        settings.AUTH_COOKIE_NAME, httponly=True,
        secure=settings.auth_cookie_secure, samesite="lax",
    )
    response.delete_cookie(
        settings.AUTH_REFRESH_COOKIE_NAME, path=_REFRESH_COOKIE_PATH, httponly=True,
        secure=settings.auth_cookie_secure, samesite="lax",
    )


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("5/minute")
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """发起密码找回。无论邮箱是否存在一律 202，不泄露账号注册情况。"""
    user = (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    if user is not None and user.deleted_at is None:
        token = _make_email_token({"action": "reset", "user_id": user.id})
        link = f"{settings.PUBLIC_FRONTEND_URL}/reset-password?token={token}"
        try:
            await send_email(body.email, "异闻录 · 重置密码", f"请在 15 分钟内点击以下链接重置密码：\n{link}\n\n若非本人操作请忽略本邮件。")
        except Exception as exc:  # noqa: BLE001 - 发信失败不向调用方泄露
            logger.warning("密码找回邮件发送失败 to=%s: %s", body.email, exc)
    return {"status": "accepted"}


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest, db: Annotated[AsyncSession, Depends(get_db)]) -> dict:
    payload = _load_email_token(body.token)
    if payload.get("action") != "reset":
        raise AppError("AUTH_LINK_INVALID", "链接无效或已过期")
    user = await db.get(User, int(payload["user_id"]))
    if user is None or user.deleted_at is not None:
        raise AppError("AUTH_LINK_INVALID", "链接无效或已过期")
    user.password_hash = await hash_password(body.new_password)
    # 密码重置后全量吊销该用户的刷新令牌，踢掉所有已登录会话
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
    await db.commit()
    return {"status": "ok"}


@router.post("/me/email", status_code=status.HTTP_202_ACCEPTED)
async def request_email_bind(
    body: BindEmailRequest,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """申请绑定/换绑邮箱：向新邮箱发验证链接，验证通过才落库。"""
    taken = (await db.execute(select(User.id).where(User.email == body.email))).scalar_one_or_none()
    if taken is not None and taken != current.id:
        raise AppError("AUTH_EMAIL_TAKEN", "该邮箱已被其他异闻师使用")
    token = _make_email_token({"action": "bind", "user_id": current.id, "email": body.email})
    link = f"{settings.PUBLIC_FRONTEND_URL}/verify-email?token={token}"
    await send_email(body.email, "异闻录 · 邮箱验证", f"请在 15 分钟内点击以下链接完成绑定：\n{link}")
    return {"status": "accepted"}


@router.post("/verify-email")
async def verify_email(body: VerifyEmailRequest, db: Annotated[AsyncSession, Depends(get_db)]) -> dict:
    payload = _load_email_token(body.token)
    if payload.get("action") != "bind":
        raise AppError("AUTH_LINK_INVALID", "链接无效或已过期")
    email = str(payload["email"])
    taken = (await db.execute(select(User.id).where(User.email == email))).scalar_one_or_none()
    if taken is not None and taken != int(payload["user_id"]):
        raise AppError("AUTH_EMAIL_TAKEN", "该邮箱已被其他异闻师使用")
    user = await db.get(User, int(payload["user_id"]))
    if user is None:
        raise AppError("AUTH_LINK_INVALID", "链接无效或已过期")
    user.email = email
    await db.commit()
    return {"status": "ok", "email": email}
