from datetime import datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.base import get_db
from app.models.creator_asset import (
    AbilityRevisionContent,
    AssetEvent,
    CharacterRevisionAbility,
    CharacterRevisionContent,
    CreatorAsset,
    CreatorAssetRevision,
    CreatorAssetTag,
    CreatorTag,
    IdempotencyRecord,
    RevisionStatus,
)
from app.models.user import User
from app.schemas.creator import (
    AbilityDraftIn,
    AssetOut,
    CharacterComponentIn,
    CharacterDraftIn,
    ComponentOut,
    CursorPage,
    TagIn,
    TagOut,
    TagsReplaceIn,
)
from app.services.creator.normalization import normalize_tag, normalize_title

router = APIRouter(prefix="/creator", tags=["creator"])
_now = datetime.utcnow


async def _asset(db: AsyncSession, asset_id: UUID, user: User) -> CreatorAsset:
    asset = await db.get(CreatorAsset, asset_id)
    if asset is None or asset.owner_id != user.id:
        raise HTTPException(404, "资产不存在")
    return asset


async def _current_component_revision(db: AsyncSession, asset: CreatorAsset) -> CreatorAssetRevision:
    revision = await db.scalar(
        select(CreatorAssetRevision)
        .where(CreatorAssetRevision.asset_id == asset.id)
        .order_by(CreatorAssetRevision.revision_number.desc())
        .limit(1)
    )
    if revision is None:
        raise HTTPException(409, "资产缺少可用内容")
    return revision


async def _component_out(db: AsyncSession, asset: CreatorAsset) -> ComponentOut:
    revision = await _current_component_revision(db, asset)
    if asset.kind == "ability":
        content = await db.get(AbilityRevisionContent, revision.id)
        if content is None:
            raise HTTPException(409, "奇术内容缺失")
        return ComponentOut(
            id=asset.id, kind=asset.kind, name=content.name, lock_version=revision.lock_version,
            content={"name": content.name, "effect": content.effect, "detail": content.detail}, updated_at=asset.updated_at,
        )
    content = await db.get(CharacterRevisionContent, revision.id)
    if content is None:
        raise HTTPException(409, "奇人内容缺失")
    ability_revision_ids = list((await db.execute(
        select(CharacterRevisionAbility.ability_revision_id)
        .where(CharacterRevisionAbility.revision_id == revision.id)
        .order_by(CharacterRevisionAbility.position)
    )).scalars())
    revision_assets = dict((await db.execute(
        select(CreatorAssetRevision.id, CreatorAssetRevision.asset_id)
        .where(CreatorAssetRevision.id.in_(ability_revision_ids))
    )).all())
    ability_asset_ids = [revision_assets[revision_id] for revision_id in ability_revision_ids if revision_id in revision_assets]
    return ComponentOut(
        id=asset.id, kind=asset.kind, name=content.name, lock_version=revision.lock_version,
        content={"name": content.name, "bio": content.bio or content.style}, ability_asset_ids=ability_asset_ids,
        updated_at=asset.updated_at,
    )


async def _component_asset(db: AsyncSession, asset_id: UUID, user: User, kind: str) -> CreatorAsset:
    asset = await _asset(db, asset_id, user)
    if asset.kind != kind or asset.deleted_at is not None:
        raise HTTPException(404, "资产不存在")
    return asset


async def _rename_component(db: AsyncSession, asset: CreatorAsset, name: str) -> None:
    name = name.strip()
    if not name:
        raise HTTPException(400, "名字不能为空")
    asset.current_title = name
    asset.normalized_title = normalize_title(name)


@router.get("/abilities", response_model=list[ComponentOut])
async def list_abilities(current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    assets = list((await db.execute(
        select(CreatorAsset)
        .where(CreatorAsset.owner_id == current.id, CreatorAsset.kind == "ability", CreatorAsset.deleted_at.is_(None))
        .order_by(CreatorAsset.updated_at.desc(), CreatorAsset.id.desc())
    )).scalars())
    return [await _component_out(db, asset) for asset in assets]


@router.get("/characters", response_model=list[ComponentOut])
async def list_characters(current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    assets = list((await db.execute(
        select(CreatorAsset)
        .where(CreatorAsset.owner_id == current.id, CreatorAsset.kind == "character", CreatorAsset.deleted_at.is_(None))
        .order_by(CreatorAsset.updated_at.desc(), CreatorAsset.id.desc())
    )).scalars())
    return [await _component_out(db, asset) for asset in assets]


async def _create_asset(db: AsyncSession, user: User, kind: str, title: str, revision: CreatorAssetRevision):
    asset = CreatorAsset(owner_id=user.id, kind=kind, current_title=title, normalized_title=normalize_title(title))
    db.add(asset)
    await db.flush()
    revision.asset_id = asset.id
    db.add(AssetEvent(asset_id=asset.id, revision_id=revision.id, actor_id=user.id, event_type="created", payload={}))
    return asset


@router.get("/assets", response_model=CursorPage)
async def list_assets(current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)], kind: str | None = None, q: str | None = None, tag: str | None = None, cursor: UUID | None = None, limit: int = Query(30, ge=1, le=100)):
    stmt = select(CreatorAsset).where(CreatorAsset.owner_id == current.id, CreatorAsset.deleted_at.is_(None)).order_by(CreatorAsset.updated_at.desc(), CreatorAsset.id.desc()).limit(limit + 1)
    if kind: stmt = stmt.where(CreatorAsset.kind == kind)
    if q: stmt = stmt.where(CreatorAsset.normalized_title.contains(normalize_title(q)))
    if tag: stmt = stmt.join(CreatorAssetTag, CreatorAssetTag.asset_id == CreatorAsset.id).join(CreatorTag, CreatorTag.id == CreatorAssetTag.tag_id).where(CreatorTag.normalized_name == normalize_tag(tag))
    if cursor: stmt = stmt.where(CreatorAsset.id < cursor)
    assets = list((await db.execute(stmt)).scalars())
    next_cursor = str(assets.pop().id) if len(assets) > limit else None
    return CursorPage(items=[AssetOut.model_validate(a) for a in assets], next_cursor=next_cursor)


async def _create_revision(db: AsyncSession, user: User, kind: str, title: str, content: dict, key: str | None):
    if not title.strip():
        base = "未命名奇术" if kind == "ability" else "未命名奇人"
        existing = (await db.execute(select(CreatorAsset.current_title).where(CreatorAsset.owner_id == user.id, CreatorAsset.kind == kind, CreatorAsset.deleted_at.is_(None), CreatorAsset.current_title.like(f"{base}%")))).scalars().all()
        used = set(existing)
        index = 1
        title = base
        while title in used:
            index += 1
            title = f"{base} {index}"
        content["name"] = title
    if key:
        existing = (await db.execute(select(IdempotencyRecord).where(IdempotencyRecord.owner_id == user.id, IdempotencyRecord.command_key == key, IdempotencyRecord.expires_at > _now()))).scalar_one_or_none()
        if existing:
            revision = await db.get(CreatorAssetRevision, UUID(existing.response_body["revision_id"]))
            asset = await db.get(CreatorAsset, UUID(existing.response_body["asset_id"]))
            if revision and asset: return asset, revision
    normalized = normalize_title(title)
    asset = CreatorAsset(owner_id=user.id, kind=kind, current_title=title.strip(), normalized_title=normalized)
    db.add(asset)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback(); raise HTTPException(409, "同类型下已有同名资产")
    rev = CreatorAssetRevision(asset_id=asset.id, revision_number=1, status=RevisionStatus.DRAFT.value)
    db.add(rev); await db.flush()
    if kind == "ability": db.add(AbilityRevisionContent(revision_id=rev.id, **content))
    else: db.add(CharacterRevisionContent(revision_id=rev.id, **content))
    db.add(AssetEvent(asset_id=asset.id, revision_id=rev.id, actor_id=user.id, event_type="created", payload={}))
    if key:
        db.add(IdempotencyRecord(owner_id=user.id, command_key=key, response_status=201, response_body={"asset_id": str(asset.id), "revision_id": str(rev.id)}, expires_at=_now() + timedelta(hours=24)))
    await db.commit(); await db.refresh(rev); await db.refresh(asset)
    return asset, rev


@router.post("/abilities", response_model=ComponentOut, status_code=201)
async def create_ability(body: AbilityDraftIn, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)], idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None):
    content = {"name": body.name.strip(), "effect": body.effect.strip(), "detail": body.detail.strip()}
    asset, _ = await _create_revision(db, current, "ability", body.name, content, idempotency_key)
    return await _component_out(db, asset)


@router.post("/characters", response_model=ComponentOut, status_code=201)
async def create_character(body: CharacterDraftIn, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    content = {"name": body.name.strip(), "bio": body.bio.strip(), "style": "", "tactic": ""}
    asset, _ = await _create_revision(db, current, "character", body.name, content, None)
    return await _component_out(db, asset)


@router.get("/abilities/{asset_id}", response_model=ComponentOut)
async def get_ability(asset_id: UUID, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    return await _component_out(db, await _component_asset(db, asset_id, current, "ability"))


@router.get("/characters/{asset_id}", response_model=ComponentOut)
async def get_character(asset_id: UUID, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    return await _component_out(db, await _component_asset(db, asset_id, current, "character"))


@router.put("/abilities/{asset_id}", response_model=ComponentOut)
async def update_ability(asset_id: UUID, body: AbilityDraftIn, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    asset = await _component_asset(db, asset_id, current, "ability")
    revision = await _current_component_revision(db, asset)
    if body.lock_version is not None and body.lock_version != revision.lock_version:
        raise HTTPException(409, {"lock_version": revision.lock_version})
    await _rename_component(db, asset, body.name)
    content = await db.get(AbilityRevisionContent, revision.id)
    if content is None:
        raise HTTPException(409, "奇术内容缺失")
    content.name, content.effect, content.detail = body.name.strip(), body.effect.strip(), body.detail.strip()
    revision.lock_version += 1
    db.add(AssetEvent(asset_id=asset.id, revision_id=revision.id, actor_id=current.id, event_type="saved", payload={}))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "同类型下已有同名资产") from None
    await db.refresh(asset)
    return await _component_out(db, asset)


@router.put("/characters/{asset_id}", response_model=ComponentOut)
async def update_character(asset_id: UUID, body: CharacterComponentIn, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    asset = await _component_asset(db, asset_id, current, "character")
    revision = await _current_component_revision(db, asset)
    if body.lock_version is not None and body.lock_version != revision.lock_version:
        raise HTTPException(409, {"lock_version": revision.lock_version})
    if len(set(body.ability_asset_ids)) != len(body.ability_asset_ids):
        raise HTTPException(400, "奇术不可重复")
    abilities: list[CreatorAssetRevision] = []
    for ability_asset_id in body.ability_asset_ids:
        ability_asset = await _component_asset(db, ability_asset_id, current, "ability")
        abilities.append(await _current_component_revision(db, ability_asset))
    await _rename_component(db, asset, body.name)
    content = await db.get(CharacterRevisionContent, revision.id)
    if content is None:
        raise HTTPException(409, "奇人内容缺失")
    content.name, content.bio, content.style, content.tactic = body.name.strip(), body.bio.strip(), "", ""
    await db.execute(delete(CharacterRevisionAbility).where(CharacterRevisionAbility.revision_id == revision.id))
    db.add_all([
        CharacterRevisionAbility(revision_id=revision.id, ability_revision_id=ability.id, position=position)
        for position, ability in enumerate(abilities, start=1)
    ])
    revision.lock_version += 1
    db.add(AssetEvent(asset_id=asset.id, revision_id=revision.id, actor_id=current.id, event_type="saved", payload={}))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "同类型下已有同名资产") from None
    await db.refresh(asset)
    return await _component_out(db, asset)


@router.delete("/abilities/{asset_id}", status_code=204)
async def delete_ability(asset_id: UUID, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    await recycle_asset(asset_id, current, db)


@router.delete("/characters/{asset_id}", status_code=204)
async def delete_character(asset_id: UUID, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    await recycle_asset(asset_id, current, db)


@router.delete("/assets/{asset_id}", status_code=204)
async def recycle_asset(asset_id: UUID, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    asset = await _asset(db, asset_id, current)
    asset.deleted_at, asset.purge_after = _now(), _now() + timedelta(days=30)
    db.add(AssetEvent(asset_id=asset.id, actor_id=current.id, event_type="recycled", payload={}))
    await db.commit()


@router.get("/tags", response_model=list[TagOut])
async def list_tags(current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    return list((await db.execute(select(CreatorTag).where(CreatorTag.owner_id == current.id).order_by(CreatorTag.name))).scalars())


@router.post("/tags", response_model=TagOut, status_code=201)
async def create_tag(body: TagIn, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    tag = CreatorTag(owner_id=current.id, name=body.name.strip(), normalized_name=normalize_tag(body.name))
    db.add(tag)
    try: await db.commit()
    except IntegrityError: await db.rollback(); raise HTTPException(409, "标签已存在")
    await db.refresh(tag); return tag


@router.put("/assets/{asset_id}/tags", response_model=AssetOut)
async def replace_tags(asset_id: UUID, body: TagsReplaceIn, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    asset = await _asset(db, asset_id, current)
    owned = list((await db.execute(select(CreatorTag.id).where(CreatorTag.owner_id == current.id, CreatorTag.id.in_(body.tag_ids)))).scalars())
    if len(owned) != len(set(body.tag_ids)): raise HTTPException(400, "标签不存在或不属于当前用户")
    await db.execute(delete(CreatorAssetTag).where(CreatorAssetTag.asset_id == asset.id))
    db.add_all([CreatorAssetTag(asset_id=asset.id, tag_id=t) for t in owned]); await db.commit(); return asset
