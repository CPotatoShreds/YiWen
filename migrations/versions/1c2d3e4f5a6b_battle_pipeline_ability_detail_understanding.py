"""battle pipeline: ability detail / understanding + battle share_token_b

Revision ID: 1c2d3e4f5a6b
Revises: 5a9c2e7d3b8f
Create Date: 2026-08-08 17:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '1c2d3e4f5a6b'
down_revision: str | Sequence[str] | None = '5a9c2e7d3b8f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # 异能：补充说明（detail）+ AI 生成的异能理解（understanding，缓存复用，供推演 LLM）
    op.add_column('abilities', sa.Column('detail', sa.Text(), server_default='', nullable=False))
    op.add_column('abilities', sa.Column('understanding', sa.Text(), server_default='', nullable=False))
    # 战报：对手 B 的分享 token（分享 = 分享者自己的视角，每侧各一个 token）。
    # SQLite 的 ADD COLUMN 不允许 UNIQUE 约束，用唯一索引代替（命名与 create_all 的 ix_<table>_<column> 一致）。
    op.add_column('battles', sa.Column('share_token_b', sa.String(32), nullable=True))
    op.create_index('ix_battles_share_token_b', 'battles', ['share_token_b'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_battles_share_token_b', table_name='battles')
    op.drop_column('battles', 'share_token_b')
    op.drop_column('abilities', 'understanding')
    op.drop_column('abilities', 'detail')
