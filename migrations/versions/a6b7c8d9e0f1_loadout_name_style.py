"""add loadout name/style (奇人姓名 / 战斗风格)

Revision ID: a6b7c8d9e0f1
Revises: 1c2d3e4f5a6b
Create Date: 2026-08-09 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a6b7c8d9e0f1'
down_revision: str | Sequence[str] | None = '1c2d3e4f5a6b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add 奇人姓名 / 战斗风格 columns（纯新增，向后兼容）。"""
    op.add_column('loadouts', sa.Column('name', sa.Text(), server_default='', nullable=False))
    op.add_column('loadouts', sa.Column('style', sa.Text(), server_default='', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('loadouts') as batch_op:
        batch_op.drop_column('style')
        batch_op.drop_column('name')
