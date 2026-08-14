"""自配 LLM 方案表 + users.active_profile_id

Revision ID: d4e5f6a7b8c9
Revises: b1c2d3e4f5a6
Create Date: 2026-08-14 00:00:00.000000

建 llm_profiles 表（用户自配模型方案：provider/base_url/api_key/model），users 加
active_profile_id 指向当前激活方案（未配则 None，用服务器默认）。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: str | Sequence[str] | None = 'b1c2d3e4f5a6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'llm_profiles',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=100), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False, server_default='openai'),
        sa.Column('base_url', sa.String(length=500), nullable=False),
        sa.Column('api_key', sa.Text(), nullable=False),
        sa.Column('model', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_llm_profiles_user_id'), 'llm_profiles', ['user_id'], unique=False)

    op.add_column('users', sa.Column('active_profile_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'users_active_profile_id_fkey', 'users', 'llm_profiles', ['active_profile_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('users_active_profile_id_fkey', 'users', type_='foreignkey')
    op.drop_column('users', 'active_profile_id')
    op.drop_index(op.f('ix_llm_profiles_user_id'), table_name='llm_profiles')
    op.drop_table('llm_profiles')
