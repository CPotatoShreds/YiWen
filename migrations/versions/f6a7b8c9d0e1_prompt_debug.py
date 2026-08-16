"""提示词方案调试表：prompt_schemes + prompt_debug_runs

Revision ID: f6a7b8c9d0e1
Revises: e1f2a3b4c5d6
Create Date: 2026-08-16 00:00:00.000000

管理员提示词方案调试：prompt_schemes 存各环节整段 system 提示词覆盖（None = 冻结默认，
生产行为不变）；prompt_debug_runs 存「用某方案重跑某场真实行迹」的独立调试记录
（story/discuss_report/winner_side），仅管理员战报页对比查看，不进入玩家面。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: str | Sequence[str] | None = 'e1f2a3b4c5d6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'prompt_schemes',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=False, server_default=''),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('discuss_prompt', sa.Text(), nullable=True),
        sa.Column('deduce_prompt', sa.Text(), nullable=True),
        sa.Column('transcribe_prompt', sa.Text(), nullable=True),
        sa.Column('validate_prompt', sa.Text(), nullable=True),
        sa.Column('repair_prompt', sa.Text(), nullable=True),
        sa.Column('usage_prompt', sa.Text(), nullable=True),
        sa.Column('guess_pair_prompt', sa.Text(), nullable=True),
        sa.Column('guess_verify_prompt', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )

    op.create_table(
        'prompt_debug_runs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('battle_id', sa.Integer(), nullable=False),
        sa.Column('scheme_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=10), nullable=False, server_default='pending'),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('story', sa.Text(), nullable=False, server_default=''),
        sa.Column('discuss_report', sa.Text(), nullable=False, server_default=''),
        sa.Column('winner_side', sa.String(length=5), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['battle_id'], ['battles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['scheme_id'], ['prompt_schemes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_prompt_debug_runs_battle_id'), 'prompt_debug_runs', ['battle_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_prompt_debug_runs_battle_id'), table_name='prompt_debug_runs')
    op.drop_table('prompt_debug_runs')
    op.drop_table('prompt_schemes')
