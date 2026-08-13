"""通知表

Revision ID: b1c2d3e4f5a6
Revises: a8b9c1d2e3f4
Create Date: 2026-08-13 14:00:00.000000

建 notifications 表：玩家交互产生的站内通知（铃铛）。纯新增表。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: str | Sequence[str] | None = 'a8b9c1d2e3f4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('actor_id', sa.Integer(), nullable=True),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('title', sa.String(length=80), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('ref_type', sa.String(length=10), nullable=True),
        sa.Column('ref_id', sa.Integer(), nullable=True),
        sa.Column('read_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_notifications_user_id'), 'notifications', ['user_id'], unique=False)
    op.create_index(op.f('ix_notifications_user_read'), 'notifications', ['user_id', 'read_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_notifications_user_read'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_user_id'), table_name='notifications')
    op.drop_table('notifications')
