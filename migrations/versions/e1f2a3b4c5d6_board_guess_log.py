"""奇人榜猜词记录列（榜主追踪）

Revision ID: e1f2a3b4c5d6
Revises: d4e5f6a7b8c9
Create Date: 2026-08-15 10:00:00.000000

board_guess_progress 加 guess_log JSON 列：逐条猜词记录（提交文本/本猜词爆出的线索/当时看破门数/对应战报），
供榜主在自己的刻印详情追踪挑战者的猜词路径。纯新增列，已有行留 NULL（服务端按 [] 读取）。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: str | Sequence[str] | None = 'd4e5f6a7b8c9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('board_guess_progress', sa.Column('guess_log', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('board_guess_progress', 'guess_log')
