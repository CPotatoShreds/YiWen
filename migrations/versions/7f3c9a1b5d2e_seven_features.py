"""七项功能：对决快照列 + 奇人榜 + 猜词行复合主键

Revision ID: 7f3c9a1b5d2e
Revises: db966a2d581b
Create Date: 2026-08-13 10:00:00.000000

- battles 增 snapshot_a/snapshot_b/revealed_a/revealed_b/board_entry_id（纯新增）。
- 建 board_entries 表（奇人榜冻结刻印）。
- battle_guesses 重建为复合主键 (battle_id, guesser_id)：一行一猜测者（和局双方并行猜的底座）。
  既有行 guesser_id 用 battles.guess_by 回填（旧逻辑只给非和局建行，guess_by 必非空）；
  done 用 flipped 或次数耗尽回填。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7f3c9a1b5d2e'
down_revision: str | Sequence[str] | None = 'db966a2d581b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. 奇人榜：冻结刻印表
    op.create_table(
        'board_entries',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('loadout_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.Text(), server_default='', nullable=False),
        sa.Column('style', sa.Text(), server_default='', nullable=False),
        sa.Column('tactic', sa.Text(), server_default='', nullable=False),
        sa.Column('abilities', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['loadout_id'], ['loadouts.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_board_entries_user_id'), 'board_entries', ['user_id'], unique=False)

    # 2. battles 加快照/揭示/榜来源列
    op.add_column('battles', sa.Column('snapshot_a', sa.JSON(), nullable=True))
    op.add_column('battles', sa.Column('snapshot_b', sa.JSON(), nullable=True))
    op.add_column('battles', sa.Column('revealed_a', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('battles', sa.Column('revealed_b', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('battles', sa.Column('board_entry_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'battles_board_entry_id_fkey', 'battles', 'board_entries', ['board_entry_id'], ['id'],
        ondelete='SET NULL',
    )

    # 3. 猜词行重建：复合主键 (battle_id, guesser_id) + done
    with op.batch_alter_table('battle_guesses') as batch:
        batch.add_column(sa.Column('guesser_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('done', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.execute(
        'UPDATE battle_guesses SET guesser_id = '
        '(SELECT guess_by FROM battles WHERE battles.id = battle_guesses.battle_id)'
    )
    # 旧逻辑只在非和局建猜词行（guess_by 必非空），此处防御性清理孤儿行
    op.execute('DELETE FROM battle_guesses WHERE guesser_id IS NULL')
    # done 回填：全破（flipped）或次数耗尽
    op.execute('UPDATE battle_guesses SET done = (flipped OR attempts_used >= attempts_max)')
    with op.batch_alter_table('battle_guesses') as batch:
        batch.drop_constraint('battle_guesses_pkey', type_='primary')
        batch.alter_column('guesser_id', existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key(
            'battle_guesses_guesser_id_fkey', 'users', ['guesser_id'], ['id']
        )
        batch.create_primary_key('battle_guesses_pkey', ['battle_id', 'guesser_id'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('battle_guesses') as batch:
        batch.drop_constraint('battle_guesses_pkey', type_='primary')
        batch.drop_constraint('battle_guesses_guesser_id_fkey', type_='foreignkey')
        batch.create_primary_key('battle_guesses_pkey', ['battle_id'])
    with op.batch_alter_table('battle_guesses') as batch:
        batch.drop_column('done')
        batch.drop_column('guesser_id')
    op.drop_constraint('battles_board_entry_id_fkey', 'battles', type_='foreignkey')
    op.drop_column('battles', 'board_entry_id')
    op.drop_column('battles', 'revealed_b')
    op.drop_column('battles', 'revealed_a')
    op.drop_column('battles', 'snapshot_b')
    op.drop_column('battles', 'snapshot_a')
    op.drop_index(op.f('ix_board_entries_user_id'), table_name='board_entries')
    op.drop_table('board_entries')
