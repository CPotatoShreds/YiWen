"""Collapse characters to name and bio, preserving the old style as bio."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "f3a4b5c6d7e8"
down_revision: str | Sequence[str] | None = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        UPDATE characters
        SET bio = style
        WHERE (bio IS NULL OR btrim(bio) = '')
          AND style IS NOT NULL
          AND btrim(style) <> ''
    """))
    op.drop_column("characters", "style")
    op.drop_column("characters", "tactic")


def downgrade() -> None:
    op.add_column("characters", sa.Column("style", sa.String(200), nullable=False, server_default=""))
    op.add_column("characters", sa.Column("tactic", sa.String(500), nullable=False, server_default=""))
    op.execute(sa.text("UPDATE characters SET style = left(bio, 200) WHERE bio IS NOT NULL"))
