"""add refresh_tokens：access+refresh 双 token 的旋转/吊销存储。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import func

revision = "c7d8e9f0a1b2"
down_revision = "ff5a6b7c8d9e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("refresh_tokens")
