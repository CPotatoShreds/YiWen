"""Compatibility revision for the previous legacy-domain cleanup pass."""
from collections.abc import Sequence

revision = "f9a0b1c2d3e4"
down_revision: str | Sequence[str] | None = "e3f4a5b6c7d8"
branch_labels = None
depends_on = None
def upgrade() -> None: pass
def downgrade() -> None: pass
