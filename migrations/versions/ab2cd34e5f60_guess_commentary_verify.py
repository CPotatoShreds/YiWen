"""猜词点评/检定状态列（点评评论 + 检定进度）

Revision ID: ab2cd34e5f60
Revises: f6a7b8c9d0e1
Create Date: 2026-08-17 12:00:00.000000

猜词链路重构（拆分/配对取消 → 点评 + 独立检定）：battle_guesses / board_guess_progress /
test_battle_guesses 三张猜词行各加两列：
- comments JSON：与 guess_history 平行的点评文本（每次点评追加一条）；
- verified_round Integer：最近一次检定时的点评数（can_verify = len(comments) > verified_round）。
纯新增列，已有行留 NULL（服务端按 None/[] 读取）。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'ab2cd34e5f60'
down_revision: str | Sequence[str] | None = 'f6a7b8c9d0e1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    for table in ('battle_guesses', 'board_guess_progress', 'test_battle_guesses'):
        op.add_column(table, sa.Column('comments', sa.JSON(), nullable=True))
        op.add_column(table, sa.Column('verified_round', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    for table in ('battle_guesses', 'board_guess_progress', 'test_battle_guesses'):
        op.drop_column(table, 'verified_round')
        op.drop_column(table, 'comments')
