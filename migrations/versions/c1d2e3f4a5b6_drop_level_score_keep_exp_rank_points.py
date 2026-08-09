"""drop level/score: 属性收敛为 见闻(exp) + 名望(rank_points)

Revision ID: c1d2e3f4a5b6
Revises: f7e8d9c0b1a2
Create Date: 2026-08-09 00:00:00.000000

取消 段位(level)/赏钱(score) 制度：保留 exp（见闻）与 rank_points（名望）为仅有两项属性。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: str | Sequence[str] | None = 'f7e8d9c0b1a2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column('users', 'level')
    op.drop_column('users', 'score')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('users', op.Column('score', sa.Integer(), server_default='0', nullable=False))
    op.add_column('users', op.Column('level', sa.Integer(), server_default='1', nullable=False))
