"""异闻资产：作者创作、管理员审核与已发布内容的只读访问。"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_admin, get_current_user
from app.db.base import get_db
from app.models.creator_asset import (
    AnecdoteRevisionContent,
    AssetEvent,
    CreatorAsset,
    CreatorAssetRevision,
    IdempotencyRecord,
    RevisionStatus,
)
from app.models.user import User
from app.schemas.creator import (
    AnecdoteDraftIn,
    AnecdotePublicOut,
    AnecdotePublicPage,
    AnecdoteRejectIn,
    AnecdoteReviewOut,
    AssetOut,
    RevisionOut,
)
from app.services.creator.normalization import normalize_title

creator_router = APIRouter(prefix="/creator/anecdotes", tags=["creator-anecdotes"])
admin_router = APIRouter(prefix="/admin/creator/anecdotes", tags=["admin-anecdotes"])
public_router = APIRouter(prefix="/anecdotes", tags=["anecdotes"])

def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _content_values(body: AnecdoteDraftIn) -> dict[str, str]:
    values = {
        "name": body.name.strip(),
        "summary": body.summary.strip(),
        "background": body.background.strip(),
        "victory_condition": body.victory_condition.strip(),
    }
    if any(not value for value in values.values()):
        raise HTTPException(status_code=400, detail="异闻四项内容均不能为空")
    return values


def _revision_out(revision: CreatorAssetRevision, content: dict[str, str]) -> RevisionOut:
    return RevisionOut(
        id=revision.id,
        asset_id=revision.asset_id,
        revision_number=revision.revision_number,
        status=revision.status,
        lock_version=revision.lock_version,
        based_on_revision_id=revision.based_on_revision_id,
        publish_error=revision.publish_error,
        review_reason=revision.review_reason,
        submitted_at=revision.submitted_at,
        reviewed_at=revision.reviewed_at,
        reviewed_by=revision.reviewed_by,
        created_at=revision.created_at,
        updated_at=revision.updated_at,
        published_at=revision.published_at,
        content=content,
    )


async def _owned_asset(db: AsyncSession, asset_id: UUID, user: User) -> CreatorAsset:
    asset = await db.get(CreatorAsset, asset_id)
    if asset is None or asset.owner_id != user.id or asset.kind != "anecdote":
        raise HTTPException(status_code=404, detail="异闻不存在")
    return asset


async def _revision_content(db: AsyncSession, revision_id: UUID) -> dict[str, str]:
    content = await db.get(AnecdoteRevisionContent, revision_id)
    if content is None:
        raise HTTPException(status_code=500, detail="异闻修订内容缺失")
    return {
        "name": content.name,
        "summary": content.summary,
        "background": content.background,
        "victory_condition": content.victory_condition,
    }


async def _work_revision(db: AsyncSession, asset_id: UUID) -> CreatorAssetRevision | None:
    return (
        await db.execute(
            select(CreatorAssetRevision).where(
                CreatorAssetRevision.asset_id == asset_id,
                CreatorAssetRevision.status.in_([
                    RevisionStatus.DRAFT.value,
                    RevisionStatus.PENDING_REVIEW.value,
                ]),
            )
        )
    ).scalar_one_or_none()


async def _creator_asset_out(db: AsyncSession, asset: CreatorAsset) -> AssetOut:
    work = await _work_revision(db, asset.id)
    return AssetOut(
        id=asset.id,
        owner_id=asset.owner_id,
        kind=asset.kind,
        current_title=asset.current_title,
        normalized_title=asset.normalized_title,
        current_published_revision_id=asset.current_published_revision_id,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
        deleted_at=asset.deleted_at,
        work_revision=_revision_out(work, await _revision_content(db, work.id)) if work else None,
    )


@creator_router.post("", response_model=RevisionOut, status_code=status.HTTP_201_CREATED)
async def create_anecdote(
    body: AnecdoteDraftIn,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> RevisionOut:
    if not body.name.strip():
        base = "未命名异闻"
        used = set((await db.execute(select(CreatorAsset.current_title).where(CreatorAsset.owner_id == current.id, CreatorAsset.kind == "anecdote", CreatorAsset.deleted_at.is_(None), CreatorAsset.current_title.like(f"{base}%")))).scalars().all())
        index, candidate = 1, base
        while candidate in used:
            index += 1
            candidate = f"{base} {index}"
        body = body.model_copy(update={"name": candidate})
    values = _content_values(body)
    if idempotency_key:
        existing = (
            await db.execute(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.owner_id == current.id,
                    IdempotencyRecord.command_key == idempotency_key,
                    IdempotencyRecord.expires_at > _now(),
                )
            )
        ).scalar_one_or_none()
        if existing:
            revision = await db.get(CreatorAssetRevision, UUID(existing.response_body["revision_id"]))
            asset = await db.get(CreatorAsset, UUID(existing.response_body["asset_id"]))
            if revision is not None and asset is not None and asset.kind == "anecdote":
                return _revision_out(revision, await _revision_content(db, revision.id))
            raise HTTPException(status_code=409, detail="Idempotency-Key 已用于其他命令")

    asset = CreatorAsset(
        owner_id=current.id,
        kind="anecdote",
        current_title=values["name"],
        normalized_title=normalize_title(values["name"]),
    )
    db.add(asset)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="同作者已有同名异闻")

    revision = CreatorAssetRevision(
        asset_id=asset.id,
        revision_number=1,
        status=RevisionStatus.DRAFT.value,
    )
    db.add(revision)
    await db.flush()
    db.add(AnecdoteRevisionContent(revision_id=revision.id, **values))
    db.add(AssetEvent(asset_id=asset.id, revision_id=revision.id, actor_id=current.id, event_type="created", payload={}))
    if idempotency_key:
        db.add(
            IdempotencyRecord(
                owner_id=current.id,
                command_key=idempotency_key,
                response_status=status.HTTP_201_CREATED,
                response_body={"asset_id": str(asset.id), "revision_id": str(revision.id)},
                expires_at=_now() + timedelta(hours=24),
            )
        )
    await db.commit()
    await db.refresh(revision)
    return _revision_out(revision, values)


@creator_router.get("/{asset_id}", response_model=AssetOut)
async def get_anecdote(
    asset_id: UUID,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AssetOut:
    return await _creator_asset_out(db, await _owned_asset(db, asset_id, current))


@creator_router.put("/{asset_id}/draft", response_model=RevisionOut)
async def save_anecdote_draft(
    asset_id: UUID,
    body: AnecdoteDraftIn,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RevisionOut:
    asset = await _owned_asset(db, asset_id, current)
    values = _content_values(body)
    revision = await _work_revision(db, asset.id)
    if revision is None or revision.status != RevisionStatus.DRAFT.value:
        raise HTTPException(status_code=409, detail="当前异闻修订已提交审核或不可编辑")
    if body.lock_version is not None and body.lock_version != revision.lock_version:
        raise HTTPException(
            status_code=409,
            detail={"revision_id": str(revision.id), "lock_version": revision.lock_version},
        )
    old_name = asset.current_title
    asset.current_title = values["name"]
    asset.normalized_title = normalize_title(values["name"])
    content = await db.get(AnecdoteRevisionContent, revision.id)
    if content is None:
        raise HTTPException(status_code=500, detail="异闻修订内容缺失")
    content.name = values["name"]
    content.summary = values["summary"]
    content.background = values["background"]
    content.victory_condition = values["victory_condition"]
    revision.lock_version += 1
    db.add(AssetEvent(asset_id=asset.id, revision_id=revision.id, actor_id=current.id, event_type="draft_saved", payload={}))
    if old_name != values["name"]:
        db.add(AssetEvent(asset_id=asset.id, revision_id=revision.id, actor_id=current.id, event_type="renamed", payload={"from": old_name, "to": values["name"]}))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="同作者已有同名异闻")
    await db.refresh(revision)
    return _revision_out(revision, values)


@creator_router.post("/{asset_id}/submit", response_model=RevisionOut, status_code=status.HTTP_202_ACCEPTED)
async def submit_anecdote(
    asset_id: UUID,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RevisionOut:
    asset = await _owned_asset(db, asset_id, current)
    revision = await _work_revision(db, asset.id)
    if revision is None or revision.status != RevisionStatus.DRAFT.value:
        raise HTTPException(status_code=409, detail="没有可提交审核的草稿")
    values = await _revision_content(db, revision.id)
    if any(not value for value in values.values()):
        raise HTTPException(status_code=400, detail="异闻四项内容均不能为空")
    revision.status = RevisionStatus.PENDING_REVIEW.value
    revision.submitted_at = _now()
    revision.review_reason = None
    db.add(AssetEvent(asset_id=asset.id, revision_id=revision.id, actor_id=current.id, event_type="review_requested", payload={}))
    await db.commit()
    await db.refresh(revision)
    return _revision_out(revision, values)


@creator_router.get("/{asset_id}/revisions", response_model=list[RevisionOut])
async def list_anecdote_revisions(
    asset_id: UUID,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[RevisionOut]:
    asset = await _owned_asset(db, asset_id, current)
    revisions = list(
        (
            await db.execute(
                select(CreatorAssetRevision)
                .where(CreatorAssetRevision.asset_id == asset.id)
                .order_by(CreatorAssetRevision.revision_number.desc())
            )
        ).scalars()
    )
    return [_revision_out(revision, await _revision_content(db, revision.id)) for revision in revisions]


@creator_router.post("/{asset_id}/revisions/{revision_id}/copy", response_model=RevisionOut, status_code=status.HTTP_201_CREATED)
async def copy_anecdote_revision(
    asset_id: UUID,
    revision_id: UUID,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RevisionOut:
    asset = await _owned_asset(db, asset_id, current)
    if await _work_revision(db, asset.id):
        raise HTTPException(status_code=409, detail="已有工作修订")
    source = await db.get(CreatorAssetRevision, revision_id)
    if source is None or source.asset_id != asset.id:
        raise HTTPException(status_code=404, detail="修订不存在")
    values = await _revision_content(db, source.id)
    number = (
        await db.execute(select(CreatorAssetRevision.revision_number).where(CreatorAssetRevision.asset_id == asset.id).order_by(CreatorAssetRevision.revision_number.desc()).limit(1))
    ).scalar_one() + 1
    draft = CreatorAssetRevision(
        asset_id=asset.id,
        revision_number=number,
        status=RevisionStatus.DRAFT.value,
        based_on_revision_id=source.id,
    )
    db.add(draft)
    await db.flush()
    db.add(AnecdoteRevisionContent(revision_id=draft.id, **values))
    asset.current_title = values["name"]
    asset.normalized_title = normalize_title(values["name"])
    db.add(AssetEvent(asset_id=asset.id, revision_id=draft.id, actor_id=current.id, event_type="draft_copied", payload={"source_revision_id": str(source.id)}))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="恢复该名字会与其他异闻重名")
    await db.refresh(draft)
    return _revision_out(draft, values)


@creator_router.post("/{asset_id}/trash", status_code=status.HTTP_204_NO_CONTENT)
async def trash_anecdote(
    asset_id: UUID,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    asset = await _owned_asset(db, asset_id, current)
    asset.deleted_at = _now()
    asset.purge_after = _now() + timedelta(days=30)
    db.add(AssetEvent(asset_id=asset.id, actor_id=current.id, event_type="recycled", payload={}))
    await db.commit()


@creator_router.post("/{asset_id}/restore", response_model=AssetOut)
async def restore_anecdote(
    asset_id: UUID,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AssetOut:
    asset = await _owned_asset(db, asset_id, current)
    if asset.deleted_at is None:
        return await _creator_asset_out(db, asset)
    conflict = (
        await db.execute(
            select(CreatorAsset.id).where(
                CreatorAsset.owner_id == current.id,
                CreatorAsset.kind == "anecdote",
                CreatorAsset.normalized_title == asset.normalized_title,
                CreatorAsset.deleted_at.is_(None),
                CreatorAsset.id != asset.id,
            )
        )
    ).scalar_one_or_none()
    if conflict:
        raise HTTPException(status_code=409, detail="恢复后会与现有异闻重名")
    asset.deleted_at = None
    asset.purge_after = None
    db.add(AssetEvent(asset_id=asset.id, actor_id=current.id, event_type="restored", payload={}))
    await db.commit()
    await db.refresh(asset)
    return await _creator_asset_out(db, asset)


def _encode_cursor(published_at: datetime, asset_id: UUID) -> str:
    payload = json.dumps({"at": published_at.isoformat(), "id": str(asset_id)}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(value: str) -> tuple[datetime, UUID]:
    try:
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        return datetime.fromisoformat(payload["at"]), UUID(payload["id"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="游标无效")


async def _published_query(db: AsyncSession, asset_id: UUID | None = None):
    query = (
        select(CreatorAsset, CreatorAssetRevision, AnecdoteRevisionContent)
        .join(CreatorAssetRevision, CreatorAssetRevision.id == CreatorAsset.current_published_revision_id)
        .join(AnecdoteRevisionContent, AnecdoteRevisionContent.revision_id == CreatorAssetRevision.id)
        .where(
            CreatorAsset.kind == "anecdote",
            CreatorAsset.deleted_at.is_(None),
            CreatorAssetRevision.status == RevisionStatus.PUBLISHED.value,
        )
    )
    if asset_id is not None:
        query = query.where(CreatorAsset.id == asset_id)
    return query


def _public_out(asset: CreatorAsset, revision: CreatorAssetRevision, content: AnecdoteRevisionContent) -> AnecdotePublicOut:
    return AnecdotePublicOut(
        id=asset.id,
        revision_id=revision.id,
        name=content.name,
        summary=content.summary,
        background=content.background,
        victory_condition=content.victory_condition,
        published_at=revision.published_at,
        created_at=asset.created_at,
    )


@public_router.get("", response_model=AnecdotePublicPage)
async def list_public_anecdotes(
    db: Annotated[AsyncSession, Depends(get_db)],
    q: str | None = Query(default=None, max_length=120),
    cursor: str | None = None,
    limit: int = Query(default=30, ge=1, le=100),
) -> AnecdotePublicPage:
    query = await _published_query(db)
    if q:
        query = query.where(AnecdoteRevisionContent.name.contains(q.strip()))
    if cursor:
        at, asset_id = _decode_cursor(cursor)
        query = query.where(
            or_(
                CreatorAssetRevision.published_at < at,
                and_(CreatorAssetRevision.published_at == at, CreatorAsset.id < asset_id),
            )
        )
    query = query.order_by(CreatorAssetRevision.published_at.desc(), CreatorAsset.id.desc()).limit(limit + 1)
    rows = list((await db.execute(query)).all())
    next_cursor = None
    if len(rows) > limit:
        last = rows.pop()
        next_cursor = _encode_cursor(last[1].published_at, last[0].id)
    return AnecdotePublicPage(items=[_public_out(*row) for row in rows], next_cursor=next_cursor)


@public_router.get("/{asset_id}", response_model=AnecdotePublicOut)
async def get_public_anecdote(asset_id: UUID, db: Annotated[AsyncSession, Depends(get_db)]) -> AnecdotePublicOut:
    row = (await db.execute(await _published_query(db, asset_id))).first()
    if row is None:
        raise HTTPException(status_code=404, detail="异闻不存在")
    return _public_out(*row)


async def _review_out(db: AsyncSession, asset: CreatorAsset, revision: CreatorAssetRevision) -> AnecdoteReviewOut:
    owner = await db.get(User, asset.owner_id)
    return AnecdoteReviewOut(
        id=asset.id,
        owner_id=asset.owner_id,
        owner_name=owner.username if owner else None,
        revision=_revision_out(revision, await _revision_content(db, revision.id)),
    )


@admin_router.get("", response_model=list[AnecdoteReviewOut])
async def list_anecdote_reviews(
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    review_status: Annotated[str | None, Query(alias="status")] = None,
) -> list[AnecdoteReviewOut]:
    state = review_status or RevisionStatus.PENDING_REVIEW.value
    rows = (
        await db.execute(
            select(CreatorAsset, CreatorAssetRevision)
            .join(CreatorAssetRevision, CreatorAssetRevision.asset_id == CreatorAsset.id)
            .where(CreatorAsset.kind == "anecdote", CreatorAssetRevision.status == state)
            .order_by(CreatorAssetRevision.submitted_at.asc(), CreatorAsset.id.asc())
        )
    ).all()
    return [await _review_out(db, asset, revision) for asset, revision in rows]


@admin_router.get("/{asset_id}", response_model=AnecdoteReviewOut)
async def get_anecdote_review(
    asset_id: UUID,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AnecdoteReviewOut:
    row = (
        await db.execute(
            select(CreatorAsset, CreatorAssetRevision)
            .join(CreatorAssetRevision, CreatorAssetRevision.asset_id == CreatorAsset.id)
            .where(CreatorAsset.id == asset_id, CreatorAsset.kind == "anecdote")
            .order_by(CreatorAssetRevision.revision_number.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="异闻不存在")
    return await _review_out(db, *row)


@admin_router.post("/{asset_id}/approve", response_model=RevisionOut)
async def approve_anecdote(
    asset_id: UUID,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RevisionOut:
    asset = await db.get(CreatorAsset, asset_id)
    if asset is None or asset.kind != "anecdote":
        raise HTTPException(status_code=404, detail="异闻不存在")
    revision = await db.scalar(
        select(CreatorAssetRevision).where(
            CreatorAssetRevision.asset_id == asset.id,
            CreatorAssetRevision.status == RevisionStatus.PENDING_REVIEW.value,
        )
    )
    if revision is None:
        raise HTTPException(status_code=409, detail="当前没有待审核修订")
    values = await _revision_content(db, revision.id)
    revision.status = RevisionStatus.PUBLISHED.value
    revision.published_at = _now()
    revision.reviewed_at = _now()
    revision.reviewed_by = admin.id
    revision.review_reason = None
    asset.current_title = values["name"]
    asset.normalized_title = normalize_title(values["name"])
    asset.current_published_revision_id = revision.id
    db.add(AssetEvent(asset_id=asset.id, revision_id=revision.id, actor_id=admin.id, event_type="review_approved", payload={}))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="异闻名字与现有资产冲突")
    await db.refresh(revision)
    return _revision_out(revision, values)


@admin_router.post("/{asset_id}/reject", response_model=RevisionOut)
async def reject_anecdote(
    asset_id: UUID,
    body: AnecdoteRejectIn,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RevisionOut:
    asset = await db.get(CreatorAsset, asset_id)
    if asset is None or asset.kind != "anecdote":
        raise HTTPException(status_code=404, detail="异闻不存在")
    revision = await db.scalar(
        select(CreatorAssetRevision).where(
            CreatorAssetRevision.asset_id == asset.id,
            CreatorAssetRevision.status == RevisionStatus.PENDING_REVIEW.value,
        )
    )
    if revision is None:
        raise HTTPException(status_code=409, detail="当前没有待审核修订")
    reason = body.reason.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="驳回原因不能为空")
    revision.status = RevisionStatus.REJECTED.value
    revision.reviewed_at = _now()
    revision.reviewed_by = admin.id
    revision.review_reason = reason
    values = await _revision_content(db, revision.id)
    db.add(AssetEvent(asset_id=asset.id, revision_id=revision.id, actor_id=admin.id, event_type="review_rejected", payload={"reason": reason}))
    await db.commit()
    await db.refresh(revision)
    return _revision_out(revision, values)
