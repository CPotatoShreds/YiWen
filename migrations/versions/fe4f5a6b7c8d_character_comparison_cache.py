"""Cache ability comparison reports for character snapshot pairs."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "fe4f5a6b7c8d"
down_revision: str | Sequence[str] | None = "fd3e4f5a6b7c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "character_comparisons",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("first_character_id", sa.Uuid(), nullable=False),
        sa.Column("second_character_id", sa.Uuid(), nullable=False),
        sa.Column("first_abilities_hash", sa.String(64), nullable=False),
        sa.Column("second_abilities_hash", sa.String(64), nullable=False),
        sa.Column("report", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["first_character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["second_character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "first_character_id",
            "second_character_id",
            "first_abilities_hash",
            "second_abilities_hash",
            name="uq_character_comparison_snapshots",
        ),
    )
    op.create_index("ix_character_comparisons_first_character_id", "character_comparisons", ["first_character_id"])
    op.create_index("ix_character_comparisons_second_character_id", "character_comparisons", ["second_character_id"])


def downgrade() -> None:
    op.drop_index("ix_character_comparisons_second_character_id", table_name="character_comparisons")
    op.drop_index("ix_character_comparisons_first_character_id", table_name="character_comparisons")
    op.drop_table("character_comparisons")
