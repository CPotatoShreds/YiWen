"""Official scenarios, public rosters and one-worldline challenge runs."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("character_revision_contents", sa.Column("bio", sa.String(500), nullable=False, server_default=""))
    uuid = sa.Uuid()
    op.create_table("scenarios",
        sa.Column("id", uuid, primary_key=True), sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(30), nullable=False), sa.Column("normalized_name", sa.String(30), nullable=False), sa.Column("summary", sa.String(120), nullable=False),
        sa.Column("background", sa.Text(), nullable=False), sa.Column("victory_condition", sa.String(300), nullable=False), sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("published_at", sa.DateTime(), nullable=True), sa.Column("deleted_at", sa.DateTime(), nullable=True), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_scenarios_status", "scenarios", ["status"])
    op.create_index("uq_scenarios_name", "scenarios", ["normalized_name"], unique=True, postgresql_where=sa.text("deleted_at IS NULL"), sqlite_where=sa.text("deleted_at IS NULL"))
    op.create_table("scenario_rosters",
        sa.Column("id", uuid, primary_key=True), sa.Column("scenario_id", uuid, sa.ForeignKey("scenarios.id", ondelete="RESTRICT"), nullable=False), sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False, server_default="player"), sa.Column("name", sa.String(30), nullable=False), sa.Column("state", sa.String(16), nullable=False, server_default="draft"), sa.Column("character_asset_id", uuid, nullable=True),
        sa.Column("character_name", sa.String(30), nullable=False), sa.Column("character_bio", sa.String(500), nullable=False, server_default=""), sa.Column("guidance", sa.String(1000), nullable=False, server_default=""),
        sa.Column("challenge_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("completed_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("first_victory_avg_challenges", sa.Float(), nullable=True), sa.Column("deleted_at", sa.DateTime(), nullable=True), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False), sa.Column("published_at", sa.DateTime(), nullable=True))
    op.create_index("ix_scenario_rosters_scenario_id", "scenario_rosters", ["scenario_id"])
    op.create_index("ix_scenario_rosters_state", "scenario_rosters", ["state"])
    op.create_table("scenario_roster_revisions", sa.Column("id", uuid, primary_key=True), sa.Column("roster_id", uuid, sa.ForeignKey("scenario_rosters.id", ondelete="CASCADE"), nullable=False), sa.Column("revision_number", sa.Integer(), nullable=False), sa.Column("state", sa.String(16), nullable=False, server_default="draft"), sa.Column("character_name", sa.String(30), nullable=False), sa.Column("character_bio", sa.String(500), nullable=False, server_default=""), sa.Column("guidance", sa.String(1000), nullable=False, server_default=""), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False), sa.Column("published_at", sa.DateTime(), nullable=True), sa.UniqueConstraint("roster_id", "revision_number", name="uq_scenario_roster_revision_number"))
    op.create_table("scenario_roster_abilities", sa.Column("roster_id", uuid, sa.ForeignKey("scenario_rosters.id", ondelete="CASCADE"), primary_key=True), sa.Column("position", sa.Integer(), primary_key=True), sa.Column("name", sa.String(10), nullable=False), sa.Column("effect", sa.String(50), nullable=False), sa.Column("detail", sa.String(500), nullable=False, server_default=""), sa.UniqueConstraint("roster_id", "position", name="uq_scenario_roster_ability_position"))
    op.create_table("scenario_challenge_runs", sa.Column("id", uuid, primary_key=True), sa.Column("roster_id", uuid, sa.ForeignKey("scenario_rosters.id", ondelete="RESTRICT"), nullable=False), sa.Column("challenger_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False), sa.Column("scenario_snapshot", sa.JSON(), nullable=False), sa.Column("roster_snapshot", sa.JSON(), nullable=False), sa.Column("challenger_snapshot", sa.JSON(), nullable=False), sa.Column("status", sa.String(16), nullable=False, server_default="active"), sa.Column("challenge_number", sa.Integer(), nullable=False, server_default="1"), sa.Column("guess_attempts", sa.Integer(), nullable=False, server_default="0"), sa.Column("won", sa.Boolean(), nullable=True), sa.Column("finished_at", sa.DateTime(), nullable=True), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_scenario_challenge_runs_roster_id", "scenario_challenge_runs", ["roster_id"])
    op.create_table("scenario_roster_progress", sa.Column("roster_id", uuid, sa.ForeignKey("scenario_rosters.id", ondelete="CASCADE"), primary_key=True), sa.Column("challenger_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True), sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"), sa.Column("first_victory_challenges", sa.Integer(), nullable=True), sa.Column("guess_history", sa.JSON(), nullable=False, server_default="[]"), sa.Column("cracked_cards", sa.JSON(), nullable=False, server_default="[]"), sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False))


def downgrade() -> None:
    op.drop_column("character_revision_contents", "bio")
    for table in ("scenario_roster_progress", "scenario_challenge_runs", "scenario_roster_abilities", "scenario_roster_revisions", "scenario_rosters", "scenarios"):
        op.drop_table(table)
