"""奇人榜点将局跨场看破进度表

Revision ID: a8b9c1d2e3f4
Revises: 7f3c9a1b5d2e
Create Date: 2026-08-13 12:00:00.000000

建 board_guess_progress 表：一行 = 挑战者 × 刻印，cards 按刻印全量奇术下标
跨场累积（点将局挑战者每场都可猜、进度用户级累积；全部看破后不再启动猜词）。
纯新增表。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a8b9c1d2e3f4'
down_revision: str | Sequence[str] | None = '7f3c9a1b5d2e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'board_guess_progress',
        sa.Column('challenger_id', sa.Integer(), nullable=False),
        sa.Column('board_entry_id', sa.Integer(), nullable=False),
        sa.Column('cards', sa.JSON(), nullable=True),
        sa.Column('guess_history', sa.JSON(), nullable=True),
        sa.Column('attempts_used', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('attempts_max', sa.Integer(), nullable=False, server_default=sa.text('99')),
        sa.Column('flipped', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('done', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['challenger_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['board_entry_id'], ['board_entries.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('challenger_id', 'board_entry_id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('board_guess_progress')
