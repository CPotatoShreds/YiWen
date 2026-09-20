"""Align character ownership constraints with mutable private assets."""
from collections.abc import Sequence

from alembic import op

revision = "f2a3b4c5d6e7"
down_revision: str | Sequence[str] | None = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Names are display data, so users may keep multiple drafts with the same name.
    op.drop_constraint("uq_character_owner_name", "characters", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint("uq_character_owner_name", "characters", ["owner_id", "name"])
