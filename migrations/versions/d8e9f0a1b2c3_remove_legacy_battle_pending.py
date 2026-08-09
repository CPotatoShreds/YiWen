"""remove legacy battle pending table

Revision ID: d8e9f0a1b2c3
Revises: 7a8b9c0d1e2f
Create Date: 2026-08-09 23:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d8e9f0a1b2c3"
down_revision: str | Sequence[str] | None = "7a8b9c0d1e2f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the obsolete recovery table no longer used by the application."""
    op.drop_table("battle_pending")


def downgrade() -> None:
    """Restore the legacy table for downgrades across this cleanup migration."""
    op.create_table(
        "battle_pending",
        sa.Column("battle_id", sa.Integer(), nullable=False),
        sa.Column("opening", sa.Text(), nullable=False),
        sa.Column("done_rounds", sa.Integer(), nullable=False),
        sa.Column("segments", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("battle_id"),
    )
