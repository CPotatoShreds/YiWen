"""unique pending battle per user

Revision ID: f7e8d9c0b1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-08-09 06:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f7e8d9c0b1a2'
down_revision: str | Sequence[str] | None = 'a6b7c8d9e0f1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """并发防重：同一用户最多一场在途摆场（部分唯一索引兜底 start_battle 先查后插的竞态）。"""
    op.create_index(
        'uq_battles_user_a_pending',
        'battles',
        ['user_a_id'],
        unique=True,
        sqlite_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_battles_user_a_pending', table_name='battles')
