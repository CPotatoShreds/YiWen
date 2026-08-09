"""merge loadout toggles into enabled; drop legacy ability/battle columns

Revision ID: f2e3d4c5b6a7
Revises: e5f6a7b8c9d0
Create Date: 2026-08-08 18:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f2e3d4c5b6a7'
down_revision: str | Sequence[str] | None = 'e5f6a7b8c9d0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Merge loadout toggles into a single `enabled`; drop legacy columns."""
    # 装配位：participate + active → enabled（现有数据全为启用）
    with op.batch_alter_table('loadouts') as batch_op:
        batch_op.add_column(sa.Column('enabled', sa.Boolean(), server_default=sa.text('1'), nullable=False))
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE loadouts SET enabled = (participate = 1 OR active = 1)"))
    with op.batch_alter_table('loadouts') as batch_op:
        batch_op.drop_column('participate')
        batch_op.drop_column('active')

    # 对战记录：删除遗留积分列（积分不再由对战结算）
    with op.batch_alter_table('battles') as batch_op:
        batch_op.drop_column('score_delta_a')
        batch_op.drop_column('score_delta_b')

    # 异能：删除遗留/恒空列（seed 带索引，batch 重建表时需先显式删索引）
    op.drop_index('ix_abilities_seed', table_name='abilities')
    with op.batch_alter_table('abilities') as batch_op:
        batch_op.drop_column('seed')
        batch_op.drop_column('description')
        batch_op.drop_column('activation')
        batch_op.drop_column('hand_motion')
        batch_op.drop_column('target_attribute')
        batch_op.drop_column('target_relation')


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('abilities') as batch_op:
        batch_op.add_column(sa.Column('seed', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('description', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('activation', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('hand_motion', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('target_attribute', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('target_relation', sa.Text(), nullable=True))

    with op.batch_alter_table('battles') as batch_op:
        batch_op.add_column(sa.Column('score_delta_a', sa.Integer(), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('score_delta_b', sa.Integer(), server_default=sa.text('0'), nullable=False))

    with op.batch_alter_table('loadouts') as batch_op:
        batch_op.add_column(sa.Column('participate', sa.Boolean(), server_default=sa.text('1'), nullable=False))
        batch_op.add_column(sa.Column('active', sa.Boolean(), server_default=sa.text('0'), nullable=False))
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE loadouts SET participate = enabled, active = enabled"))
    with op.batch_alter_table('loadouts') as batch_op:
        batch_op.drop_column('enabled')
