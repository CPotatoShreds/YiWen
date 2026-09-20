"""Convert scenario slugs to ASCII pinyin."""
import re
import unicodedata
from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from pypinyin import lazy_pinyin

revision = "ff5a6b7c8d9e"
down_revision: str | Sequence[str] | None = "fe4f5a6b7c8d"
branch_labels = None
depends_on = None


def _slugify(value: str) -> str:
    value = "-".join(lazy_pinyin(unicodedata.normalize("NFKC", value).casefold()))
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")[:80]


def upgrade() -> None:
    bind = op.get_bind()
    scenarios = sa.table(
        "scenarios",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("slug", sa.String()),
    )
    used: set[str] = set()
    rows = bind.execute(sa.select(scenarios.c.id, scenarios.c.name).order_by(scenarios.c.id)).mappings().all()
    for row in rows:
        scenario_id: UUID = row["id"]
        base = _slugify(row["name"]) or f"scenario-{scenario_id.hex[:8]}"
        slug = base
        if slug in used:
            slug = f"{base[:71].rstrip('-')}-{scenario_id.hex[:8]}"
        used.add(slug)
        bind.execute(scenarios.update().where(scenarios.c.id == scenario_id).values(slug=slug))


def downgrade() -> None:
    # The previous migration's slugs were not reversible transliterations.
    pass
