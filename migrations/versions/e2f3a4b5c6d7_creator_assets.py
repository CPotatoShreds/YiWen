"""Private creator asset workspace with immutable revisions.

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
"""
from collections.abc import Sequence
from hashlib import sha256
import re
import unicodedata
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "e2f3a4b5c6d7"
down_revision: str | Sequence[str] | None = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("test_abilities", sa.Column("id", sa.String(64), primary_key=True), sa.Column("name", sa.String(10), nullable=False), sa.Column("effect", sa.String(50), nullable=False), sa.Column("detail", sa.String(500), nullable=False, server_default=""), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False))
    op.create_table("test_ability_revisions", sa.Column("id", sa.String(64), primary_key=True), sa.Column("test_ability_id", sa.String(64), nullable=False), sa.Column("revision_number", sa.Integer(), nullable=False, server_default="1"), sa.Column("name", sa.String(10), nullable=False), sa.Column("effect", sa.String(50), nullable=False), sa.Column("detail", sa.String(500), nullable=False, server_default=""))
    op.create_index("ix_test_ability_revisions_test_ability_id", "test_ability_revisions", ["test_ability_id"])
    uuid = sa.Uuid()
    op.create_table(
        "creator_assets",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("current_title", sa.String(50), nullable=False),
        sa.Column("normalized_title", sa.String(50), nullable=False),
        sa.Column("current_published_revision_id", uuid, nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("purge_after", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_creator_assets_owner_id", "creator_assets", ["owner_id"])
    op.create_index("ix_creator_assets_deleted_at", "creator_assets", ["deleted_at"])
    op.create_index("uq_creator_asset_owner_kind_title", "creator_assets", ["owner_id", "kind", "normalized_title"], unique=True, postgresql_where=sa.text("deleted_at IS NULL"), sqlite_where=sa.text("deleted_at IS NULL"))

    op.create_table(
        "creator_asset_revisions",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("asset_id", uuid, sa.ForeignKey("creator_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("based_on_revision_id", uuid, nullable=True),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("content_sha256", sa.String(64), nullable=False, server_default=""),
        sa.Column("publish_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("asset_id", "revision_number", name="uq_creator_revision_number"),
    )
    op.create_index("ix_creator_asset_revisions_asset_id", "creator_asset_revisions", ["asset_id"])
    op.create_index("ix_creator_asset_revisions_status", "creator_asset_revisions", ["status"])
    op.create_index("uq_creator_asset_work_revision", "creator_asset_revisions", ["asset_id"], unique=True, postgresql_where=sa.text("status IN ('draft', 'publishing', 'publish_failed')"), sqlite_where=sa.text("status IN ('draft', 'publishing', 'publish_failed')"))

    op.create_table("ability_revision_contents", sa.Column("revision_id", uuid, sa.ForeignKey("creator_asset_revisions.id", ondelete="CASCADE"), primary_key=True), sa.Column("name", sa.String(10), nullable=False), sa.Column("effect", sa.String(50), nullable=False), sa.Column("detail", sa.String(500), nullable=False, server_default=""))
    op.create_table("character_revision_contents", sa.Column("revision_id", uuid, sa.ForeignKey("creator_asset_revisions.id", ondelete="CASCADE"), primary_key=True), sa.Column("name", sa.String(30), nullable=False, server_default=""), sa.Column("style", sa.String(200), nullable=False, server_default=""), sa.Column("tactic", sa.String(500), nullable=False, server_default=""))
    op.create_table("character_revision_abilities", sa.Column("revision_id", uuid, sa.ForeignKey("creator_asset_revisions.id", ondelete="CASCADE"), primary_key=True), sa.Column("ability_revision_id", uuid, sa.ForeignKey("creator_asset_revisions.id", ondelete="RESTRICT"), primary_key=True), sa.Column("position", sa.Integer(), primary_key=True), sa.UniqueConstraint("revision_id", "position", name="uq_character_revision_position"))

    op.create_table("creator_tags", sa.Column("id", uuid, primary_key=True), sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("name", sa.String(30), nullable=False), sa.Column("normalized_name", sa.String(30), nullable=False), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False), sa.UniqueConstraint("owner_id", "normalized_name", name="uq_creator_tag_owner_name"))
    op.create_table("creator_asset_tags", sa.Column("asset_id", uuid, sa.ForeignKey("creator_assets.id", ondelete="CASCADE"), primary_key=True), sa.Column("tag_id", uuid, sa.ForeignKey("creator_tags.id", ondelete="CASCADE"), primary_key=True))
    op.create_table("asset_revision_derivations", sa.Column("revision_id", uuid, sa.ForeignKey("creator_asset_revisions.id", ondelete="CASCADE"), primary_key=True), sa.Column("status", sa.String(20), nullable=False, server_default="pending"), sa.Column("result", sa.JSON(), nullable=True), sa.Column("error", sa.Text(), nullable=True), sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"), sa.Column("task_id", sa.String(128), nullable=True), sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False))
    op.create_table("asset_events", sa.Column("id", uuid, primary_key=True), sa.Column("asset_id", uuid, sa.ForeignKey("creator_assets.id", ondelete="RESTRICT"), nullable=False), sa.Column("revision_id", uuid, nullable=True), sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True), sa.Column("event_type", sa.String(40), nullable=False), sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_asset_events_asset_id", "asset_events", ["asset_id"])
    op.create_table("outbox_events", sa.Column("id", uuid, primary_key=True), sa.Column("topic", sa.String(80), nullable=False), sa.Column("aggregate_id", uuid, nullable=False), sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"), sa.Column("published_at", sa.DateTime(), nullable=True), sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"), sa.Column("available_at", sa.DateTime(), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_outbox_events_topic", "outbox_events", ["topic"])
    op.create_index("ix_outbox_events_aggregate_id", "outbox_events", ["aggregate_id"])
    op.create_table("idempotency_records", sa.Column("id", uuid, primary_key=True), sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("command_key", sa.String(128), nullable=False), sa.Column("response_status", sa.Integer(), nullable=False), sa.Column("response_body", sa.JSON(), nullable=False, server_default="{}"), sa.Column("expires_at", sa.DateTime(), nullable=False), sa.UniqueConstraint("owner_id", "command_key", name="uq_idempotency_owner_key"))
    _migrate_legacy_assets()


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", value).strip()).casefold()


def _migrate_legacy_assets() -> None:
    """Copy legacy player content without making old battle references mutable.

    The old tables remain in place during the validation period. Unowned abilities
    intentionally stay there because they belong to the test arena, not a player.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    needed = {"abilities", "user_abilities", "loadouts", "loadout_abilities"}
    if not needed.issubset(inspector.get_table_names()):
        return
    metadata = sa.MetaData()
    abilities = sa.Table("abilities", metadata, autoload_with=bind)
    user_abilities = sa.Table("user_abilities", metadata, autoload_with=bind)
    loadouts = sa.Table("loadouts", metadata, autoload_with=bind)
    loadout_abilities = sa.Table("loadout_abilities", metadata, autoload_with=bind)
    assets = sa.Table("creator_assets", metadata, autoload_with=bind)
    revisions = sa.Table("creator_asset_revisions", metadata, autoload_with=bind)
    ability_content = sa.Table("ability_revision_contents", metadata, autoload_with=bind)
    character_content = sa.Table("character_revision_contents", metadata, autoload_with=bind)
    character_abilities = sa.Table("character_revision_abilities", metadata, autoload_with=bind)
    derivations = sa.Table("asset_revision_derivations", metadata, autoload_with=bind)
    events = sa.Table("asset_events", metadata, autoload_with=bind)

    legacy_abilities = {row.id: row for row in bind.execute(sa.select(abilities)).mappings()}
    owned = bind.execute(sa.select(user_abilities).order_by(user_abilities.c.user_id, user_abilities.c.obtained_at)).mappings()
    ability_revisions: dict[tuple[int, str], object] = {}
    titles: dict[tuple[int, str, str], int] = {}
    for owned_row in owned:
        old = legacy_abilities.get(owned_row["ability_id"])
        if old is None:
            continue
        owner_id = owned_row["user_id"]
        original_title = (old["name"] or "未命名奇术").strip()[:50]
        title = original_title
        norm = _normalized(title)
        key = (owner_id, "ability", norm)
        if key in titles:
            titles[key] += 1
            title = f"{original_title[:40]}（迁移副本 {titles[key]}）"
            norm = _normalized(title)
        else:
            titles[key] = 0
        asset_id, revision_id, event_id = uuid4(), uuid4(), uuid4()
        assets_insert = {"id": asset_id, "owner_id": owner_id, "kind": "ability", "current_title": title, "normalized_title": norm, "current_published_revision_id": revision_id}
        bind.execute(assets.insert().values(**assets_insert))
        content = {"name": (old["name"] or "")[:10], "effect": (old["effect"] or "")[:50], "detail": (old.get("detail") or "")[:500]}
        digest = sha256(f"{content['name']}\n{content['effect']}\n{content['detail']}".encode()).hexdigest()
        bind.execute(revisions.insert().values(id=revision_id, asset_id=asset_id, revision_number=1, status="published", lock_version=1, content_sha256=digest, published_at=old.get("created_at")))
        bind.execute(ability_content.insert().values(revision_id=revision_id, **content))
        bind.execute(derivations.insert().values(revision_id=revision_id, status="legacy", result=None, attempts=0))
        bind.execute(events.insert().values(id=event_id, asset_id=asset_id, revision_id=revision_id, actor_id=owner_id, event_type="migrated", payload={"legacy_ability_id": old["id"], "original_title": original_title}))
        ability_revisions[(owner_id, old["id"])] = revision_id

    for loadout in bind.execute(sa.select(loadouts).order_by(loadouts.c.id)).mappings():
        owner_id = loadout["user_id"]
        original_title = (loadout["name"] or "未命名奇人").strip()[:50]
        title, norm = original_title, _normalized(original_title)
        key = (owner_id, "character", norm)
        if key in titles:
            titles[key] += 1
            title, norm = f"{original_title[:40]}（迁移副本 {titles[key]}）", _normalized(f"{original_title[:40]}（迁移副本 {titles[key]}）")
        else:
            titles[key] = 0
        old_links = list(bind.execute(sa.select(loadout_abilities).where(loadout_abilities.c.loadout_id == loadout["id"])).mappings())
        linked_revisions = [ability_revisions[(owner_id, item["ability_id"])] for item in old_links if (owner_id, item["ability_id"]) in ability_revisions]
        published = 1 <= len(linked_revisions) <= 4
        asset_id, revision_id = uuid4(), uuid4()
        assets_insert = {"id": asset_id, "owner_id": owner_id, "kind": "character", "current_title": title, "normalized_title": norm, "current_published_revision_id": revision_id if published else None}
        bind.execute(assets.insert().values(**assets_insert))
        content = {"name": (loadout["name"] or "")[:30], "style": (loadout.get("style") or "")[:200], "tactic": (loadout.get("tactic") or "")[:500]}
        digest = sha256(f"{content['name']}\n{content['style']}\n{content['tactic']}".encode()).hexdigest()
        bind.execute(revisions.insert().values(id=revision_id, asset_id=asset_id, revision_number=1, status="published" if published else "draft", lock_version=1, content_sha256=digest, published_at=loadout.get("created_at") if published else None))
        bind.execute(character_content.insert().values(revision_id=revision_id, **content))
        for position, ability_revision_id in enumerate(linked_revisions, 1):
            bind.execute(character_abilities.insert().values(revision_id=revision_id, ability_revision_id=ability_revision_id, position=position))
        bind.execute(derivations.insert().values(revision_id=revision_id, status="legacy", result=None, attempts=0))
        bind.execute(events.insert().values(id=uuid4(), asset_id=asset_id, revision_id=revision_id, actor_id=owner_id, event_type="migrated", payload={"legacy_loadout_id": loadout["id"]}))


def downgrade() -> None:
    for table in ["idempotency_records", "outbox_events", "asset_events", "asset_revision_derivations", "creator_asset_tags", "creator_tags", "character_revision_abilities", "character_revision_contents", "ability_revision_contents", "creator_asset_revisions", "creator_assets", "test_ability_revisions", "test_abilities"]:
        op.drop_table(table)
