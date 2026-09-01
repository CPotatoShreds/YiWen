"""Outbox publisher shared by Celery workers and the local development runner."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select

from app.db.base import async_session_factory
from app.models.creator_asset import (
    AbilityRevisionContent,
    AssetEvent,
    AssetRevisionDerivation,
    CharacterRevisionAbility,
    CharacterRevisionContent,
    CreatorAsset,
    CreatorAssetRevision,
    DerivationStatus,
    OutboxEvent,
    RevisionStatus,
)

_now = datetime.utcnow


async def process_publish_event(outbox_id: UUID) -> None:
    async with async_session_factory() as db:
        event = await db.get(OutboxEvent, outbox_id)
        if event is None or event.published_at is not None:
            return
        revision = await db.get(CreatorAssetRevision, event.aggregate_id)
        if revision is None:
            event.published_at = _now()
            await db.commit()
            return
        derivation = await db.get(AssetRevisionDerivation, revision.id)
        try:
            if revision.status not in (RevisionStatus.PUBLISHING.value, RevisionStatus.PUBLISH_FAILED.value):
                return
            asset = await db.get(CreatorAsset, revision.asset_id)
            if asset is None:
                raise ValueError("资产不存在")
            if asset.kind == "ability":
                content = await db.get(AbilityRevisionContent, revision.id)
                if content is None or not content.name.strip() or not content.effect.strip():
                    raise ValueError("奇术内容不完整")
            else:
                content = await db.get(CharacterRevisionContent, revision.id)
                links = list(
                    (
                        await db.execute(
                            select(CharacterRevisionAbility)
                            .where(CharacterRevisionAbility.revision_id == revision.id)
                            .order_by(CharacterRevisionAbility.position)
                        )
                    ).scalars()
                )
                if content is None or not (1 <= len(links) <= 4):
                    raise ValueError("奇人发布时必须装配 1-4 门已发布奇术")
                for link in links:
                    ability_revision = await db.get(CreatorAssetRevision, link.ability_revision_id)
                    if ability_revision is None or ability_revision.status != RevisionStatus.PUBLISHED.value:
                        raise ValueError("装配的奇术必须是已发布版本")
            if derivation is None:
                derivation = AssetRevisionDerivation(revision_id=revision.id)
                db.add(derivation)
            derivation.status = DerivationStatus.SUCCEEDED.value
            derivation.result = {"validated": True}
            derivation.attempts = (derivation.attempts or 0) + 1
            revision.status = RevisionStatus.PUBLISHED.value
            revision.publish_error = None
            revision.published_at = _now()
            asset.current_published_revision_id = revision.id
            asset.updated_at = _now()
            event.published_at = _now()
            db.add(AssetEvent(asset_id=asset.id, revision_id=revision.id, actor_id=asset.owner_id, event_type="published", payload={}))
            await db.commit()
        except Exception as exc:  # noqa: BLE001 - persisted for manual retry
            if derivation is None:
                derivation = AssetRevisionDerivation(revision_id=revision.id)
                db.add(derivation)
            derivation.status = DerivationStatus.FAILED.value
            derivation.error = str(exc)
            derivation.attempts = (derivation.attempts or 0) + 1
            revision.status = RevisionStatus.PUBLISH_FAILED.value
            revision.publish_error = str(exc)
            event.attempts = (event.attempts or 0) + 1
            await db.commit()


def enqueue_local_publish(outbox_id: UUID) -> None:
    import asyncio

    asyncio.create_task(process_publish_event(outbox_id))


try:
    from celery import Celery

    celery_app = Celery("ynfight", broker="redis://localhost:6380/0", backend="redis://localhost:6380/1")

    @celery_app.task(name="creator.publish_revision")
    def publish_revision_task(outbox_id: str) -> None:
        import asyncio

        asyncio.run(process_publish_event(UUID(outbox_id)))
except ImportError:  # pragma: no cover - Celery is optional in unit tests
    celery_app = None
