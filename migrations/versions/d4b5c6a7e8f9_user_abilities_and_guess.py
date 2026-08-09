"""user-defined abilities and battle guess

Revision ID: d4b5c6a7e8f9
Revises: b0aff016cb51
Create Date: 2026-08-08 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4b5c6a7e8f9'
down_revision: str | Sequence[str] | None = 'b0aff016cb51'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # 设置项：对手猜错时是否展示我的异能（默认展示）
    op.add_column('users', sa.Column('reveal_on_miss', sa.Boolean(), server_default=sa.text('1'), nullable=False))
    # 猜底牌相关 + 友谊赛标记
    op.add_column('battles', sa.Column('guess_by', sa.Integer(), nullable=True))  # 输家（猜测者）
    op.add_column('battles', sa.Column('guess_text', sa.Text(), server_default='', nullable=False))
    op.add_column('battles', sa.Column('guess_state', sa.String(length=10), server_default='none', nullable=False))  # none/pending/judged
    op.add_column('battles', sa.Column('guess_hit', sa.Boolean(), nullable=True))
    op.add_column('battles', sa.Column('revealed', sa.Boolean(), server_default=sa.text('0'), nullable=False))  # 双方异能是否已揭示
    op.add_column('battles', sa.Column('friendly', sa.Boolean(), server_default=sa.text('0'), nullable=False))  # 友谊赛（不计天梯分）


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('battles', 'friendly')
    op.drop_column('battles', 'revealed')
    op.drop_column('battles', 'guess_hit')
    op.drop_column('battles', 'guess_state')
    op.drop_column('battles', 'guess_text')
    op.drop_column('battles', 'guess_by')
    op.drop_column('users', 'reveal_on_miss')
