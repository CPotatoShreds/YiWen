"""add battle_guess guess_history (败方每次猜测原文，双方可见)

Revision ID: c3d4e5f6a7b8
Revises: b7c9d1e3f5a7
Create Date: 2026-08-09 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: str | Sequence[str] | None = 'b7c9d1e3f5a7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add guess_history column（纯新增，向后兼容）。"""
    op.add_column('battle_guesses', sa.Column('guess_history', sa.JSON(), server_default='[]', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('battle_guesses', 'guess_history')
