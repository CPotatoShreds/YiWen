"""loadouts and battle loadout snapshot

Revision ID: e5f6a7b8c9d0
Revises: d4b5c6a7e8f9
Create Date: 2026-08-08 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: str | Sequence[str] | None = 'd4b5c6a7e8f9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # 装配位：每用户固定 3 个（participate 参与匹配 / active 使用位）
    op.create_table(
        'loadouts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('participate', sa.Boolean(), server_default=sa.text('1'), nullable=False),
        sa.Column('active', sa.Boolean(), server_default=sa.text('0'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_loadouts_user_id'), 'loadouts', ['user_id'], unique=False)

    # 装配位 ↔ 异能（多对多）
    op.create_table(
        'loadout_abilities',
        sa.Column('loadout_id', sa.Integer(), nullable=False),
        sa.Column('ability_id', sa.String(length=64), nullable=False),
        sa.Column('added_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['ability_id'], ['abilities.id'], ),
        sa.ForeignKeyConstraint(['loadout_id'], ['loadouts.id'], ),
        sa.PrimaryKeyConstraint('loadout_id', 'ability_id'),
    )

    # 对战记录本场每侧装配位快照（SQLite 不支持 ALTER 加 FK 约束，外键仅保留在 ORM 层）
    op.add_column('battles', sa.Column('loadout_a_id', sa.Integer(), nullable=True))
    op.add_column('battles', sa.Column('loadout_b_id', sa.Integer(), nullable=True))

    # 回填老用户：每人 3 个装配位（全 participate=1，第一个 active=1），已有异能并入第一个装配位
    conn = op.get_bind()
    for (user_id,) in conn.execute(sa.text("SELECT id FROM users")):
        first = conn.execute(
            sa.text(
                "INSERT INTO loadouts (user_id, participate, active, created_at) "
                "VALUES (:u, 1, 1, CURRENT_TIMESTAMP)"
            ),
            {"u": user_id},
        ).lastrowid
        for _ in range(2):
            conn.execute(
                sa.text(
                    "INSERT INTO loadouts (user_id, participate, active, created_at) "
                    "VALUES (:u, 1, 0, CURRENT_TIMESTAMP)"
                ),
                {"u": user_id},
            )
        conn.execute(
            sa.text(
                "INSERT INTO loadout_abilities (loadout_id, ability_id, added_at) "
                "SELECT :l, ability_id, CURRENT_TIMESTAMP FROM user_abilities WHERE user_id = :u"
            ),
            {"l": first, "u": user_id},
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('battles', 'loadout_b_id')
    op.drop_column('battles', 'loadout_a_id')
    op.drop_table('loadout_abilities')
    op.drop_index(op.f('ix_loadouts_user_id'), table_name='loadouts')
    op.drop_table('loadouts')
