"""Drop scenario roster category."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "fb1c2d3e4f5a"
down_revision: str | Sequence[str] | None = "fa1b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("scenario_rosters", "kind")


def downgrade() -> None:
    op.add_column(
        "scenario_rosters",
        sa.Column("kind", sa.String(16), nullable=False, server_default="player"),
    )
