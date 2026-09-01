"""Add reviewable anecdote creator assets.

Revision ID: f7a8b9c0d1e2
Revises: e2f3a4b5c6d7, f6a7b8c9d0e1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: str | Sequence[str] | None = ("e2f3a4b5c6d7", "f6a7b8c9d0e1")
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = sa.Uuid()
    op.create_table(
        "anecdote_revision_contents",
        sa.Column("revision_id", uuid, sa.ForeignKey("creator_asset_revisions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("name", sa.String(30), nullable=False),
        sa.Column("summary", sa.String(120), nullable=False),
        sa.Column("background", sa.String(1000), nullable=False),
        sa.Column("victory_condition", sa.String(300), nullable=False),
    )
    op.add_column("creator_asset_revisions", sa.Column("review_reason", sa.Text(), nullable=True))
    op.add_column("creator_asset_revisions", sa.Column("submitted_at", sa.DateTime(), nullable=True))
    op.add_column("creator_asset_revisions", sa.Column("reviewed_at", sa.DateTime(), nullable=True))
    op.add_column(
        "creator_asset_revisions",
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_creator_asset_revisions_reviewed_by", "creator_asset_revisions", ["reviewed_by"])
    op.drop_index("uq_creator_asset_work_revision", table_name="creator_asset_revisions")
    op.create_index(
        "uq_creator_asset_work_revision",
        "creator_asset_revisions",
        ["asset_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('draft', 'pending_review', 'publishing', 'publish_failed')"),
        sqlite_where=sa.text("status IN ('draft', 'pending_review', 'publishing', 'publish_failed')"),
    )


def downgrade() -> None:
    op.drop_index("uq_creator_asset_work_revision", table_name="creator_asset_revisions")
    op.create_index(
        "uq_creator_asset_work_revision",
        "creator_asset_revisions",
        ["asset_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('draft', 'publishing', 'publish_failed')"),
        sqlite_where=sa.text("status IN ('draft', 'publishing', 'publish_failed')"),
    )
    op.drop_index("ix_creator_asset_revisions_reviewed_by", table_name="creator_asset_revisions")
    op.drop_column("creator_asset_revisions", "reviewed_by")
    op.drop_column("creator_asset_revisions", "reviewed_at")
    op.drop_column("creator_asset_revisions", "submitted_at")
    op.drop_column("creator_asset_revisions", "review_reason")
    op.drop_table("anecdote_revision_contents")
