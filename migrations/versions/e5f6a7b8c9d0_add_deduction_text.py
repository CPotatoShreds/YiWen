"""Add scenario_challenge_runs.deduction_text for decoupled deduction stage.

推演/叙述解耦（docs/plans/2026-10-02-deduction-narration-split.md）：推演任务
先落全文到本列（站间 checkpoint + 数据契约），叙述/检定任务从列读取输入。
终局后保留作审计（turn.omniscient 照旧另存）。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | Sequence[str] | None = "6102d944c525"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("scenario_challenge_runs", sa.Column("deduction_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("scenario_challenge_runs", "deduction_text")
