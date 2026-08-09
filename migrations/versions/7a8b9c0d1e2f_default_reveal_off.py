"""make reveal_on_miss default to disabled

Revision ID: 7a8b9c0d1e2f
Revises: 6f6f16e2ef53
Create Date: 2026-08-09 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7a8b9c0d1e2f"
down_revision: str | Sequence[str] | None = "6f6f16e2ef53"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Make newly inserted users keep their奇术 private by default."""
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "reveal_on_miss",
            existing_type=sa.Boolean(),
            existing_nullable=False,
            existing_server_default=sa.text("1"),
            server_default=sa.text("0"),
        )


def downgrade() -> None:
    """Restore the previous database default."""
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "reveal_on_miss",
            existing_type=sa.Boolean(),
            existing_nullable=False,
            existing_server_default=sa.text("0"),
            server_default=sa.text("1"),
        )
