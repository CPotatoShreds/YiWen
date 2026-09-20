"""Replace creator assets and global abilities with mutable user-owned entities."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None

def upgrade() -> None:
    for table in ("character_revision_abilities", "character_revision_contents", "ability_revision_contents", "creator_asset_revisions", "creator_asset_tags", "creator_tags", "asset_revision_derivations", "asset_events", "outbox_events", "idempotency_records", "creator_assets", "user_abilities"):
        op.execute(sa.text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))
    op.execute(sa.text('DROP TABLE IF EXISTS "abilities" CASCADE'))
    op.create_table(
        "abilities",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(50), nullable=False), sa.Column("effect", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""), sa.Column("understanding", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_abilities_owner_id", "abilities", ["owner_id"])
    op.create_table(
        "characters",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(30), nullable=False, server_default=""), sa.Column("bio", sa.String(500), nullable=False, server_default=""),
        sa.Column("style", sa.String(200), nullable=False, server_default=""), sa.Column("tactic", sa.String(500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("owner_id", "name", name="uq_character_owner_name"),
    )
    op.create_index("ix_characters_owner_id", "characters", ["owner_id"])
    op.create_table(
        "character_abilities",
        sa.Column("character_id", sa.Uuid(), sa.ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("ability_id", sa.String(64), sa.ForeignKey("abilities.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("position", sa.Integer(), nullable=False), sa.UniqueConstraint("character_id", "position", name="uq_character_ability_position"),
    )
    op.add_column("scenario_rosters", sa.Column("character_id", sa.Uuid(), sa.ForeignKey("characters.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_scenario_rosters_character_id", "scenario_rosters", ["character_id"])
    op.execute(sa.text('ALTER TABLE scenario_rosters DROP COLUMN IF EXISTS "character_asset_id"'))

def downgrade() -> None:
    op.drop_index("ix_scenario_rosters_character_id", table_name="scenario_rosters")
    op.drop_column("scenario_rosters", "character_id")
    op.drop_table("character_abilities"); op.drop_table("characters"); op.drop_table("abilities")
