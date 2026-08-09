"""battle guess score (判定均分)

Revision ID: 7f3c9e1a2b4d
Revises: f2e3d4c5b6a7
Create Date: 2026-08-08 15:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7f3c9e1a2b4d'
down_revision: str | Sequence[str] | None = 'f2e3d4c5b6a7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # 猜底牌判定均分（1-4）：均分 ≥3 胜负逆转，≥3.5 双倍扣分
    op.add_column('battles', sa.Column('guess_score', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('battles', 'guess_score')
