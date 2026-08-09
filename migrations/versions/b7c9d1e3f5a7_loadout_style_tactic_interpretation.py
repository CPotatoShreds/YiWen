"""add loadout style/tactic interpretation (战斗风格/战术 异步解读缓存)

Revision ID: b7c9d1e3f5a7
Revises: c1d2e3f4a5b6
Create Date: 2026-08-09 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7c9d1e3f5a7'
down_revision: str | Sequence[str] | None = 'c1d2e3f4a5b6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add 战斗风格/战术解读缓存 columns（纯新增，向后兼容）。"""
    op.add_column('loadouts', sa.Column('style_interpretation', sa.Text(), server_default='', nullable=False))
    op.add_column('loadouts', sa.Column('tactic_interpretation', sa.Text(), server_default='', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('loadouts') as batch_op:
        batch_op.drop_column('tactic_interpretation')
        batch_op.drop_column('style_interpretation')
