"""自配 LLM 方案路由：一用户多套配置，激活一套生效（users.active_profile_id 单指针）。

api_key 全链路加密：前端 jsencrypt(RSA) 传输 → 私钥解密 → Fernet 落库加密；永不回传明文，
只给 has_api_key 布尔；更新时空 api_key = 保留原值。API 只接受已加密的 api_key（明文会被拒）。
"""

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.base import get_db
from app.models.llm_profile import LlmProfile
from app.models.user import User
from app.schemas.llm_profile import LlmProfileCreate, LlmProfileOut, LlmProfileUpdate
from app.services import profile_crypto

router = APIRouter(prefix="/llm-profiles", tags=["llm-profiles"])


def _decrypt_transit_api_key(body_api_key: str) -> str:
    """传输密文 → 明文；解密失败按 400 拒（不接收明文密钥）。"""
    try:
        return profile_crypto.decrypt_transit(body_api_key)
    except Exception:  # noqa: BLE001 - 密文非法/base64 错误/过长等统一按客户端错误
        raise HTTPException(status_code=400, detail="api_key 传输加密格式无效")


def _out(p: LlmProfile, active_id: int | None) -> LlmProfileOut:
    return LlmProfileOut(
        id=p.id,
        label=p.label,
        provider=p.provider,
        base_url=p.base_url,
        model=p.model,
        has_api_key=bool(p.api_key),
        is_active=p.id == active_id,
        created_at=p.created_at,
    )


async def _get_owned(db: AsyncSession, user_id: int, profile_id: int) -> LlmProfile:
    profile = await db.get(LlmProfile, profile_id)
    if profile is None or profile.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="方案不存在")
    return profile


@router.get("/public-key")
async def public_key() -> dict:
    """前端 jsencrypt 加密 api_key 所需的 RSA 公钥（公开信息，无需登录）。"""
    return {"public_key": profile_crypto.get_public_key_pem()}


@router.get("", response_model=list[LlmProfileOut])
async def list_profiles(
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[LlmProfileOut]:
    rows = await db.execute(
        select(LlmProfile).where(LlmProfile.user_id == current.id).order_by(LlmProfile.id)
    )
    return [_out(p, current.active_profile_id) for p in rows.scalars()]


@router.post("", response_model=LlmProfileOut, status_code=status.HTTP_201_CREATED)
async def create_profile(
    body: LlmProfileCreate,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LlmProfileOut:
    profile = LlmProfile(
        user_id=current.id,
        label=body.label,
        provider=body.provider,
        base_url=body.base_url,
        api_key=profile_crypto.encrypt_storage(_decrypt_transit_api_key(body.api_key)),
        model=body.model,
    )
    db.add(profile)
    await db.flush()
    count = await db.scalar(select(func.count()).select_from(LlmProfile).where(LlmProfile.user_id == current.id))
    if count == 1:
        current.active_profile_id = profile.id  # 首个方案自动激活
    await db.commit()
    await db.refresh(profile)
    return _out(profile, current.active_profile_id)


@router.put("/{profile_id}", response_model=LlmProfileOut)
async def update_profile(
    profile_id: int,
    body: LlmProfileUpdate,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LlmProfileOut:
    profile = await _get_owned(db, current.id, profile_id)
    data = body.model_dump(exclude_unset=True)
    if body.api_key in (None, ""):
        data.pop("api_key", None)  # 空 api_key 保留原值
    elif "api_key" in data:
        data["api_key"] = profile_crypto.encrypt_storage(_decrypt_transit_api_key(body.api_key))
    for field, value in data.items():
        setattr(profile, field, value)
    await db.commit()
    await db.refresh(profile)
    return _out(profile, current.active_profile_id)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    profile_id: int,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    profile = await _get_owned(db, current.id, profile_id)
    if current.active_profile_id == profile.id:
        current.active_profile_id = None
    await db.delete(profile)
    await db.commit()


@router.post("/{profile_id}/activate", response_model=LlmProfileOut)
async def activate_profile(
    profile_id: int,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LlmProfileOut:
    profile = await _get_owned(db, current.id, profile_id)
    current.active_profile_id = profile.id  # 单指针，天然互斥
    await db.commit()
    return _out(profile, current.active_profile_id)


@router.post("/{profile_id}/test")
async def test_profile(
    profile_id: int,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """调 {base_url}/models 验证连通性（不消耗 token），返回 ok/detail。"""
    profile = await _get_owned(db, current.id, profile_id)
    api_key = profile_crypto.decrypt_storage(profile.api_key) if profile.api_key else ""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.get(
                f"{profile.base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if res.status_code == 200:
            return {"ok": True, "detail": "连接成功"}
        return {"ok": False, "detail": f"HTTP {res.status_code}: {res.text[:200]}"}
    except Exception as e:  # noqa: BLE001 - 网络/超时/连接错误统一按失败返回
        return {"ok": False, "detail": str(e)[:200]}
