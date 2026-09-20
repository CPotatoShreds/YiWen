"""Drop unused legacy roster-revision workflow fields (submit/review/lock flow retired).

All five columns were verified write-only/never-read with no data (NULL or server default).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "b4c5d6e7f8a9"
down_revision: str | Sequence[str] | None = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("scenario_roster_revisions", "lock_version")
    op.drop_column("scenario_roster_revisions", "based_on_revision_id")
    op.drop_column("scenario_roster_revisions", "submitted_at")
    op.drop_column("scenario_roster_revisions", "deleted_at")
    op.drop_column("scenario_rosters", "work_revision_id")


def downgrade() -> None:
    # Structure-only restoration for migration tooling; dropped default data is not reconstructed.
    op.add_column("scenario_rosters", sa.Column("work_revision_id", sa.Uuid(), nullable=True))
    op.add_column("scenario_roster_revisions", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.add_column("scenario_roster_revisions", sa.Column("submitted_at", sa.DateTime(), nullable=True))
    op.add_column("scenario_roster_revisions", sa.Column("based_on_revision_id", sa.Uuid(), nullable=True))
    op.add_column(
        "scenario_roster_revisions",
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
    )
