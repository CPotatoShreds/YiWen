"""Create flat scenario composition and challenge tables; clear legacy collections."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # Explicitly clear legacy collection rows before dropping their tables.
    for table in ("collection_guess_progress", "collection_messages", "collection_worldlines", "collection_challenges", "collection_booklets", "collection_volumes"):
        if sa.inspect(bind).has_table(table):
            op.drop_table(table)
    uuid = sa.Uuid()
    op.create_table("creator_scenarios",
        sa.Column("id", uuid, primary_key=True), sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("normalized_name", sa.String(30), nullable=False), sa.Column("current_revision_id", uuid, nullable=True), sa.Column("work_revision_id", uuid, nullable=True),
        sa.Column("challenge_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("deleted_at", sa.DateTime(), nullable=True), sa.Column("purge_after", sa.DateTime(), nullable=True), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False))
    op.create_index("uq_creator_scenario_owner_name", "creator_scenarios", ["owner_id", "normalized_name"], unique=True, postgresql_where=sa.text("deleted_at IS NULL"), sqlite_where=sa.text("deleted_at IS NULL"))
    op.create_table("scenario_revisions",
        sa.Column("id", uuid, primary_key=True), sa.Column("scenario_id", uuid, sa.ForeignKey("creator_scenarios.id", ondelete="CASCADE"), nullable=False), sa.Column("revision_number", sa.Integer(), nullable=False), sa.Column("status", sa.String(20), nullable=False, server_default="draft"), sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"), sa.Column("based_on_revision_id", uuid, nullable=True), sa.Column("review_reason", sa.Text(), nullable=True), sa.Column("submitted_at", sa.DateTime(), nullable=True), sa.Column("reviewed_at", sa.DateTime(), nullable=True), sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True), sa.Column("published_at", sa.DateTime(), nullable=True), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False), sa.UniqueConstraint("scenario_id", "revision_number", name="uq_scenario_revision_number"))
    op.create_index("ix_scenario_revisions_scenario_id", "scenario_revisions", ["scenario_id"])
    op.create_table("scenario_revision_stories", sa.Column("revision_id", uuid, sa.ForeignKey("scenario_revisions.id", ondelete="CASCADE"), primary_key=True), sa.Column("name", sa.String(30), nullable=False), sa.Column("summary", sa.String(120), nullable=False), sa.Column("background", sa.String(1000), nullable=False), sa.Column("victory_condition", sa.String(300), nullable=False), sa.Column("guidance", sa.String(1000), nullable=False, server_default=""))
    op.create_table("scenario_revision_guardians", sa.Column("revision_id", uuid, sa.ForeignKey("scenario_revisions.id", ondelete="CASCADE"), primary_key=True), sa.Column("name", sa.String(30), nullable=False), sa.Column("style", sa.String(200), nullable=False, server_default=""), sa.Column("tactic", sa.String(500), nullable=False, server_default=""))
    op.create_table("scenario_revision_abilities", sa.Column("revision_id", uuid, sa.ForeignKey("scenario_revisions.id", ondelete="CASCADE"), primary_key=True), sa.Column("position", sa.Integer(), primary_key=True), sa.Column("name", sa.String(10), nullable=False), sa.Column("effect", sa.String(50), nullable=False), sa.Column("detail", sa.String(500), nullable=False, server_default=""), sa.UniqueConstraint("revision_id", "position", name="uq_scenario_revision_ability_position"))
    op.create_table("scenario_challenges", sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True), sa.Column("scenario_revision_id", uuid, sa.ForeignKey("scenario_revisions.id", ondelete="RESTRICT"), nullable=False), sa.Column("challenger_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("scenario_snapshot", sa.JSON(), nullable=False), sa.Column("challenger_snapshot", sa.JSON(), nullable=False), sa.Column("status", sa.String(16), nullable=False, server_default="active"), sa.Column("derived_at", sa.DateTime(), nullable=True), sa.Column("cracked_at", sa.DateTime(), nullable=True), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False), sa.Column("finished_at", sa.DateTime(), nullable=True))
    op.create_index("ix_scenario_challenges_revision", "scenario_challenges", ["scenario_revision_id"])
    op.create_index("uq_scenario_active_challenge", "scenario_challenges", ["scenario_revision_id", "challenger_id"], unique=True, postgresql_where=sa.text("status = 'active'"), sqlite_where=sa.text("status = 'active'"))
    op.create_table("scenario_worldlines", sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True), sa.Column("challenge_id", sa.Integer(), sa.ForeignKey("scenario_challenges.id", ondelete="CASCADE"), nullable=False), sa.Column("sequence", sa.Integer(), nullable=False), sa.Column("status", sa.String(16), nullable=False, server_default="active"), sa.Column("token_budget", sa.Integer(), nullable=False, server_default="24000"), sa.Column("tokens_used", sa.Integer(), nullable=False, server_default="0"), sa.Column("derived", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False), sa.Column("ended_at", sa.DateTime(), nullable=True))
    op.create_table("scenario_messages", sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True), sa.Column("worldline_id", sa.Integer(), sa.ForeignKey("scenario_worldlines.id", ondelete="CASCADE"), nullable=False), sa.Column("sequence", sa.Integer(), nullable=False), sa.Column("role", sa.String(16), nullable=False), sa.Column("challenger_text", sa.Text(), nullable=False, server_default=""), sa.Column("guardian_text", sa.Text(), nullable=False, server_default=""), sa.Column("omniscient_text", sa.Text(), nullable=False, server_default=""), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False))
    op.create_table("scenario_guess_progress", sa.Column("challenger_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True), sa.Column("challenge_id", sa.Integer(), sa.ForeignKey("scenario_challenges.id", ondelete="CASCADE"), primary_key=True), sa.Column("cards", sa.JSON(), nullable=False, server_default="[]"), sa.Column("history", sa.JSON(), nullable=False, server_default="[]"), sa.Column("comments", sa.JSON(), nullable=False, server_default="[]"), sa.Column("atom_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("verified_round", sa.Integer(), nullable=True), sa.Column("cracked_at", sa.DateTime(), nullable=True), sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False))


def downgrade() -> None:
    for table in ("scenario_guess_progress", "scenario_messages", "scenario_worldlines", "scenario_challenges", "scenario_revision_abilities", "scenario_revision_guardians", "scenario_revision_stories", "scenario_revisions", "creator_scenarios"):
        op.drop_table(table)
