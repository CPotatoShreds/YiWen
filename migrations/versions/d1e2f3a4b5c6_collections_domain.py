"""Rename the unpublished initial domain to collection / volume / booklet.

Revision ID: d1e2f3a4b5c6
Revises: c0d1e2f3a4b5
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "d1e2f3a4b5c6"
down_revision: str | Sequence[str] | None = "c0d1e2f3a4b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _remove_empty_orm_tables() -> None:
    """DEBUG create_all may create the renamed tables before Alembic runs.

    They are safe to remove only when empty. Existing content means an operator
    must reconcile two independently written domains instead of losing data.
    """
    if context.is_offline_mode():
        return
    bind = op.get_bind()
    table_names = set(sa.inspect(bind).get_table_names())
    collection_tables = [
        "collection_volumes",
        "collection_booklets",
        "collection_challenges",
        "collection_worldlines",
        "collection_messages",
        "collection_guess_progress",
    ]
    present = [table for table in collection_tables if table in table_names]
    if not present:
        return
    nonempty = [table for table in present if bind.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first()]
    if nonempty:
        raise RuntimeError(f"collection migration found existing data in {', '.join(nonempty)}")
    for table in reversed(collection_tables):
        if table in table_names:
            op.drop_table(table)


def upgrade() -> None:
    _remove_empty_orm_tables()
    op.rename_table("world_posts", "collection_volumes")
    with op.batch_alter_table("collection_volumes") as batch:
        batch.drop_column("responses_open")
        batch.add_column(sa.Column("booklet_requirements", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("victory_condition", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("tianji", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))

    op.rename_table("world_answers", "collection_booklets")
    with op.batch_alter_table("collection_booklets") as batch:
        batch.alter_column("post_id", new_column_name="volume_id")
        batch.drop_column("challenger_max_people")
        batch.drop_column("challenger_max_abilities")

    op.rename_table("world_challenges", "collection_challenges")
    with op.batch_alter_table("collection_challenges") as batch:
        batch.alter_column("answer_id", new_column_name="booklet_id")

    op.drop_index("uq_worldlines_active_challenger", table_name="worldlines")
    op.rename_table("worldlines", "collection_worldlines")
    with op.batch_alter_table("collection_worldlines") as batch:
        batch.drop_column("challenger_id")
    op.create_index(
        "uq_collection_worldlines_active_challenge",
        "collection_worldlines",
        ["challenge_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )

    op.rename_table("world_messages", "collection_messages")
    with op.batch_alter_table("collection_messages") as batch:
        batch.add_column(sa.Column("omniscient_text", sa.Text(), nullable=False, server_default=""))
    op.execute("UPDATE collection_messages SET omniscient_text = challenger_text WHERE omniscient_text = ''")

    op.rename_table("world_guess_progress", "collection_guess_progress")
    with op.batch_alter_table("collection_guess_progress") as batch:
        batch.alter_column("answer_id", new_column_name="booklet_id")
        batch.add_column(sa.Column("first_derived_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("first_derived_worldlines", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("first_cracked_atoms", sa.Integer(), nullable=True))

    op.create_index(
        "uq_collection_challenges_active_challenger_booklet",
        "collection_challenges",
        ["booklet_id", "challenger_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("uq_collection_challenges_active_challenger_booklet", table_name="collection_challenges")
    with op.batch_alter_table("collection_guess_progress") as batch:
        batch.drop_column("first_cracked_atoms")
        batch.drop_column("first_derived_worldlines")
        batch.drop_column("first_derived_at")
        batch.alter_column("booklet_id", new_column_name="answer_id")
    op.rename_table("collection_guess_progress", "world_guess_progress")
    with op.batch_alter_table("collection_messages") as batch:
        batch.drop_column("omniscient_text")
    op.rename_table("collection_messages", "world_messages")
    op.drop_index("uq_collection_worldlines_active_challenge", table_name="collection_worldlines")
    with op.batch_alter_table("collection_worldlines") as batch:
        batch.add_column(sa.Column("challenger_id", sa.Integer(), nullable=True))
    op.rename_table("collection_worldlines", "worldlines")
    with op.batch_alter_table("collection_challenges") as batch:
        batch.alter_column("booklet_id", new_column_name="answer_id")
    op.rename_table("collection_challenges", "world_challenges")
    with op.batch_alter_table("collection_booklets") as batch:
        batch.add_column(sa.Column("challenger_max_abilities", sa.Integer(), nullable=False, server_default="4"))
        batch.add_column(sa.Column("challenger_max_people", sa.Integer(), nullable=False, server_default="1"))
        batch.alter_column("volume_id", new_column_name="post_id")
    op.rename_table("collection_booklets", "world_answers")
    with op.batch_alter_table("collection_volumes") as batch:
        batch.drop_column("tianji")
        batch.drop_column("victory_condition")
        batch.drop_column("booklet_requirements")
        batch.add_column(sa.Column("responses_open", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.rename_table("collection_volumes", "world_posts")
