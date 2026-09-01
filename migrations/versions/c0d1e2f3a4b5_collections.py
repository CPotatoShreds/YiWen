"""小天下集初始表：卷、册、挑战与交互世界线。

Revision ID: c0d1e2f3a4b5
Revises: ab2cd34e5f60
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c0d1e2f3a4b5"
down_revision: str | Sequence[str] | None = "ab2cd34e5f60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "world_posts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=80), nullable=False),
        sa.Column("introduction", sa.Text(), nullable=False),
        sa.Column("responses_open", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_world_posts_user_id"), "world_posts", ["user_id"], unique=False)
    op.create_table(
        "world_answers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("defenders", sa.JSON(), nullable=False),
        sa.Column("opening", sa.Text(), nullable=False),
        sa.Column("guardian_brief", sa.Text(), nullable=False),
        sa.Column("challenger_max_people", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("challenger_max_abilities", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("challenges_open", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("stats_date", sa.String(length=10), nullable=True),
        sa.Column("stats", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["post_id"], ["world_posts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_world_answers_post_id"), "world_answers", ["post_id"], unique=False)
    op.create_index(op.f("ix_world_answers_user_id"), "world_answers", ["user_id"], unique=False)
    op.create_table(
        "world_challenges",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("answer_id", sa.Integer(), nullable=False),
        sa.Column("challenger_id", sa.Integer(), nullable=False),
        sa.Column("challengers", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("derived_at", sa.DateTime(), nullable=True),
        sa.Column("cracked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["answer_id"], ["world_answers.id"]),
        sa.ForeignKeyConstraint(["challenger_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_world_challenges_answer_id"), "world_challenges", ["answer_id"], unique=False)
    op.create_index(op.f("ix_world_challenges_challenger_id"), "world_challenges", ["challenger_id"], unique=False)
    op.create_table(
        "worldlines",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("challenge_id", sa.Integer(), nullable=False),
        sa.Column("challenger_id", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("token_budget", sa.Integer(), nullable=False, server_default="24000"),
        sa.Column("tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("derived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["challenge_id"], ["world_challenges.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["challenger_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_worldlines_challenge_id"), "worldlines", ["challenge_id"], unique=False)
    op.create_index(op.f("ix_worldlines_challenger_id"), "worldlines", ["challenger_id"], unique=False)
    op.create_index("uq_worldlines_active_challenger", "worldlines", ["challenger_id"], unique=True, postgresql_where=sa.text("status = 'active'"), sqlite_where=sa.text("status = 'active'"))
    op.create_table(
        "world_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("worldline_id", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("challenger_text", sa.Text(), nullable=False),
        sa.Column("guardian_text", sa.Text(), nullable=False),
        sa.Column("tokens_input", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_output", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["worldline_id"], ["worldlines.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_world_messages_worldline_id"), "world_messages", ["worldline_id"], unique=False)
    op.create_table(
        "world_guess_progress",
        sa.Column("challenger_id", sa.Integer(), nullable=False),
        sa.Column("answer_id", sa.Integer(), nullable=False),
        sa.Column("cards", sa.JSON(), nullable=False),
        sa.Column("history", sa.JSON(), nullable=False),
        sa.Column("comments", sa.JSON(), nullable=False),
        sa.Column("atom_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("verified_round", sa.Integer(), nullable=True),
        sa.Column("cracked_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["answer_id"], ["world_answers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["challenger_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("challenger_id", "answer_id"),
    )


def downgrade() -> None:
    op.drop_table("world_guess_progress")
    op.drop_index(op.f("ix_world_messages_worldline_id"), table_name="world_messages")
    op.drop_table("world_messages")
    op.drop_index("uq_worldlines_active_challenger", table_name="worldlines")
    op.drop_index(op.f("ix_worldlines_challenger_id"), table_name="worldlines")
    op.drop_index(op.f("ix_worldlines_challenge_id"), table_name="worldlines")
    op.drop_table("worldlines")
    op.drop_index(op.f("ix_world_challenges_challenger_id"), table_name="world_challenges")
    op.drop_index(op.f("ix_world_challenges_answer_id"), table_name="world_challenges")
    op.drop_table("world_challenges")
    op.drop_index(op.f("ix_world_answers_user_id"), table_name="world_answers")
    op.drop_index(op.f("ix_world_answers_post_id"), table_name="world_answers")
    op.drop_table("world_answers")
    op.drop_index(op.f("ix_world_posts_user_id"), table_name="world_posts")
    op.drop_table("world_posts")
