"""ability / loadout tactic (战术描述)

Revision ID: 5a9c2e7d3b8f
Revises: 7f3c9e1a2b4d
Create Date: 2026-08-08 16:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '5a9c2e7d3b8f'
down_revision: str | Sequence[str] | None = '7f3c9e1a2b4d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # 战术描述：异能 = 我会怎么使用它；配置 = 如果我用这个配置，我会怎么打（推演时注入 prompt）
    op.add_column('abilities', sa.Column('tactic', sa.Text(), server_default='', nullable=False))
    op.add_column('loadouts', sa.Column('tactic', sa.Text(), server_default='', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('loadouts', 'tactic')
    op.drop_column('abilities', 'tactic')
