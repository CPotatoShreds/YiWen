"""Add persistent auxiliary guessing state for scenario challenges."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "fa1b2c3d4e5f"
down_revision: str | Sequence[str] | None = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scenario_roster_progress", sa.Column("guess_rounds", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("scenario_roster_progress", sa.Column("guess_credits", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("scenario_challenge_runs", sa.Column("guess_in_flight", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("scenario_challenge_runs", sa.Column("verify_in_flight", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("scenario_challenge_runs", sa.Column("guess_granted", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("scenario_challenge_runs", "guess_granted")
    op.drop_column("scenario_challenge_runs", "verify_in_flight")
    op.drop_column("scenario_challenge_runs", "guess_in_flight")
    op.drop_column("scenario_roster_progress", "guess_credits")
    op.drop_column("scenario_roster_progress", "guess_rounds")
