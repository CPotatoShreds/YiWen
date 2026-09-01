"""Complete roster revision snapshots and challenge transcript fields."""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scenario_rosters", sa.Column("current_revision_id", sa.Uuid(), nullable=True))
    op.add_column("scenario_rosters", sa.Column("work_revision_id", sa.Uuid(), nullable=True))
    op.add_column("scenario_roster_revisions", sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("scenario_roster_revisions", sa.Column("based_on_revision_id", sa.Uuid(), nullable=True))
    op.add_column("scenario_roster_revisions", sa.Column("submitted_at", sa.DateTime(), nullable=True))
    op.add_column("scenario_roster_revisions", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.create_table(
        "scenario_roster_revision_abilities",
        sa.Column("revision_id", sa.Uuid(), sa.ForeignKey("scenario_roster_revisions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(10), nullable=False),
        sa.Column("effect", sa.String(50), nullable=False),
        sa.Column("detail", sa.String(500), nullable=False, server_default=""),
    )
    op.add_column("scenario_challenge_runs", sa.Column("messages", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("scenario_challenge_runs", sa.Column("guesses", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("scenario_challenge_runs", sa.Column("derived", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("scenario_challenge_runs", "derived")
    op.drop_column("scenario_challenge_runs", "guesses")
    op.drop_column("scenario_challenge_runs", "messages")
    op.drop_table("scenario_roster_revision_abilities")
    for name in ("deleted_at", "submitted_at", "based_on_revision_id", "lock_version"):
        op.drop_column("scenario_roster_revisions", name)
    op.drop_column("scenario_rosters", "work_revision_id")
    op.drop_column("scenario_rosters", "current_revision_id")
