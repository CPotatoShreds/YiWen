"""Mark author roster trials so they stay out of public statistics."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: str | Sequence[str] | None = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scenario_challenge_runs", sa.Column("is_preview", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_scenario_challenge_runs_is_preview", "scenario_challenge_runs", ["is_preview"])


def downgrade() -> None:
    op.drop_index("ix_scenario_challenge_runs_is_preview", table_name="scenario_challenge_runs")
    op.drop_column("scenario_challenge_runs", "is_preview")
