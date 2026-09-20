"""Converge DB schema with ORM models (drift cleanup).

- Drop orphan tables left behind by retired domains: test_abilities /
  test_ability_revisions (former trial ground) and anecdote_revision_contents
  (retired anecdote domain).
- Create the 7 model-declared indexes that prior migrations never materialized.
  (uq_scenario_roster_ability_position turned out to be the table's primary key
  name, not a missing constraint — the model's redundant UniqueConstraint was
  removed instead.)
- Align scenario_rosters.character_id FK with the model (RESTRICT → SET NULL).
- Tighten abilities/characters timestamp columns to NOT NULL (no NULL rows exist).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "6102d944c525"
down_revision: str | Sequence[str] | None = "b4c5d6e7f8a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index(op.f("ix_test_ability_revisions_test_ability_id"), table_name="test_ability_revisions")
    op.drop_table("test_ability_revisions")
    op.drop_table("test_abilities")
    op.drop_table("anecdote_revision_contents")
    op.alter_column("abilities", "created_at",
               existing_type=postgresql.TIMESTAMP(),
               nullable=False,
               existing_server_default=sa.text("now()"))
    op.alter_column("abilities", "updated_at",
               existing_type=postgresql.TIMESTAMP(),
               nullable=False,
               existing_server_default=sa.text("now()"))
    op.alter_column("characters", "created_at",
               existing_type=postgresql.TIMESTAMP(),
               nullable=False,
               existing_server_default=sa.text("now()"))
    op.alter_column("characters", "updated_at",
               existing_type=postgresql.TIMESTAMP(),
               nullable=False,
               existing_server_default=sa.text("now()"))
    op.create_index(op.f("ix_scenario_challenge_runs_challenger_id"), "scenario_challenge_runs", ["challenger_id"], unique=False)
    op.create_index(op.f("ix_scenario_challenge_runs_status"), "scenario_challenge_runs", ["status"], unique=False)
    op.create_index(op.f("ix_scenario_roster_revisions_roster_id"), "scenario_roster_revisions", ["roster_id"], unique=False)
    op.create_index(op.f("ix_scenario_roster_revisions_state"), "scenario_roster_revisions", ["state"], unique=False)
    op.create_index(op.f("ix_scenario_rosters_current_revision_id"), "scenario_rosters", ["current_revision_id"], unique=False)
    op.create_index(op.f("ix_scenario_rosters_owner_id"), "scenario_rosters", ["owner_id"], unique=False)
    op.drop_constraint(op.f("scenario_rosters_character_id_fkey"), "scenario_rosters", type_="foreignkey")
    op.create_foreign_key("scenario_rosters_character_id_fkey", "scenario_rosters", "characters", ["character_id"], ["id"], ondelete="SET NULL")
    op.create_index(op.f("ix_scenarios_created_by"), "scenarios", ["created_by"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_scenarios_created_by"), table_name="scenarios")
    op.drop_constraint("scenario_rosters_character_id_fkey", "scenario_rosters", type_="foreignkey")
    op.create_foreign_key("scenario_rosters_character_id_fkey", "scenario_rosters", "characters", ["character_id"], ["id"], ondelete="RESTRICT")
    op.drop_index(op.f("ix_scenario_rosters_owner_id"), table_name="scenario_rosters")
    op.drop_index(op.f("ix_scenario_rosters_current_revision_id"), table_name="scenario_rosters")
    op.drop_index(op.f("ix_scenario_roster_revisions_state"), table_name="scenario_roster_revisions")
    op.drop_index(op.f("ix_scenario_roster_revisions_roster_id"), table_name="scenario_roster_revisions")
    op.drop_index(op.f("ix_scenario_challenge_runs_status"), table_name="scenario_challenge_runs")
    op.drop_index(op.f("ix_scenario_challenge_runs_challenger_id"), table_name="scenario_challenge_runs")
    op.alter_column("characters", "updated_at",
               existing_type=postgresql.TIMESTAMP(),
               nullable=True,
               existing_server_default=sa.text("now()"))
    op.alter_column("characters", "created_at",
               existing_type=postgresql.TIMESTAMP(),
               nullable=True,
               existing_server_default=sa.text("now()"))
    op.alter_column("abilities", "updated_at",
               existing_type=postgresql.TIMESTAMP(),
               nullable=True,
               existing_server_default=sa.text("now()"))
    op.alter_column("abilities", "created_at",
               existing_type=postgresql.TIMESTAMP(),
               nullable=True,
               existing_server_default=sa.text("now()"))
    op.create_table("anecdote_revision_contents",
    sa.Column("revision_id", sa.UUID(), autoincrement=False, nullable=False),
    sa.Column("name", sa.VARCHAR(length=30), autoincrement=False, nullable=False),
    sa.Column("summary", sa.VARCHAR(length=120), autoincrement=False, nullable=False),
    sa.Column("background", sa.VARCHAR(length=1000), autoincrement=False, nullable=False),
    sa.Column("victory_condition", sa.VARCHAR(length=300), autoincrement=False, nullable=False),
    sa.PrimaryKeyConstraint("revision_id", name=op.f("anecdote_revision_contents_pkey"))
    )
    op.create_table("test_abilities",
    sa.Column("id", sa.VARCHAR(length=64), autoincrement=False, nullable=False),
    sa.Column("name", sa.VARCHAR(length=10), autoincrement=False, nullable=False),
    sa.Column("effect", sa.VARCHAR(length=50), autoincrement=False, nullable=False),
    sa.Column("detail", sa.VARCHAR(length=500), server_default=sa.text("''::character varying"), autoincrement=False, nullable=False),
    sa.Column("created_at", postgresql.TIMESTAMP(), server_default=sa.text("now()"), autoincrement=False, nullable=False),
    sa.PrimaryKeyConstraint("id", name=op.f("test_abilities_pkey"))
    )
    op.create_table("test_ability_revisions",
    sa.Column("id", sa.VARCHAR(length=64), autoincrement=False, nullable=False),
    sa.Column("test_ability_id", sa.VARCHAR(length=64), autoincrement=False, nullable=False),
    sa.Column("revision_number", sa.INTEGER(), server_default=sa.text("1"), autoincrement=False, nullable=False),
    sa.Column("name", sa.VARCHAR(length=10), autoincrement=False, nullable=False),
    sa.Column("effect", sa.VARCHAR(length=50), autoincrement=False, nullable=False),
    sa.Column("detail", sa.VARCHAR(length=500), server_default=sa.text("''::character varying"), autoincrement=False, nullable=False),
    sa.PrimaryKeyConstraint("id", name=op.f("test_ability_revisions_pkey"))
    )
    op.create_index(op.f("ix_test_ability_revisions_test_ability_id"), "test_ability_revisions", ["test_ability_id"], unique=False)
