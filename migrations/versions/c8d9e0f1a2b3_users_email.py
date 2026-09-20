"""users 加 email 列：可空 + 部分唯一索引（仅对非空邮箱唯一，存量用户不受影响）。"""

import sqlalchemy as sa
from alembic import op

revision = "c8d9e0f1a2b3"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email", sa.String(255), nullable=True))
    op.create_index(
        "uq_users_email", "users", ["email"], unique=True,
        postgresql_where=sa.text("email IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_users_email", table_name="users")
    op.drop_column("users", "email")
