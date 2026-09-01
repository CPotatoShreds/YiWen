"""Add stable indexes for roster challenge history queries."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e3f4a5b6c7d8"
down_revision: str | Sequence[str] | None = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_scenario_challenge_runs_roster_challenger_created",
        "scenario_challenge_runs",
        ["roster_id", "challenger_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_scenario_challenge_runs_roster_created",
        "scenario_challenge_runs",
        ["roster_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_scenario_challenge_runs_roster_created", table_name="scenario_challenge_runs")
    op.drop_index("ix_scenario_challenge_runs_roster_challenger_created", table_name="scenario_challenge_runs")
