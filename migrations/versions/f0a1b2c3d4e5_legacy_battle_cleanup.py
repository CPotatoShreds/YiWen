"""Remove the retired battle, loadout, social, notification and debug domains."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "f0a1b2c3d4e5"
down_revision: str | Sequence[str] | None = "f9a0b1c2d3e4"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Child tables first so this works on PostgreSQL with foreign-key checks enabled.
    for table in (
        "battle_guesses", "battles", "friendships", "loadout_abilities", "loadouts",
        "notifications", "prompt_debug_runs", "prompt_schemes", "test_battle_guesses",
        "test_battles", "test_loadout_abilities", "test_loadouts", "test_users",
    ):
        op.execute(sa.text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))
    for column in ("rank_points", "last_battle_date", "reveal_on_miss", "last_login_date", "exp"):
        op.execute(sa.text(f'ALTER TABLE users DROP COLUMN IF EXISTS "{column}"'))

def downgrade() -> None:
    # Retired data is intentionally not reconstructed; the revision is forward-only in practice.
    # Keep downgrade executable for migration tooling by restoring the user columns.
    op.add_column("users", sa.Column("exp", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("last_login_date", sa.String(10), nullable=True))
    op.add_column("users", sa.Column("last_battle_date", sa.String(10), nullable=True))
    op.add_column("users", sa.Column("reveal_on_miss", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("rank_points", sa.Integer(), nullable=False, server_default="1000"))
