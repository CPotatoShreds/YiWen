"""Widen roster ability snapshot `effect` column to match abilities.

拓印（POST /api/creator/scenarios/{id}/rosters）把奇术原文快照写入
scenario_roster_abilities / scenario_roster_revision_abilities，而这两张表的
`effect` 从 2026-09-02 引入起就是 varchar(50)。

`abilities.effect` 是 text：2026-09-02 之前没有长度校验，存量 84 门奇术效果超过
50 字（当时 API 允许任意长度）。拓印这些旧奇术会触发 asyncpg
StringDataRightTruncationError（HTTP 500，报错点 app/api/routes/scenario_domain.py
的 db.flush()）。这里把快照列放宽为 text，与源表对齐；写入侧的 50 字上限不动。

`name`（varchar(10)）与 `detail`（varchar(500)）同样窄于源表，由后续迁移
c9d0e1f2a3b4 一并放宽。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7c8d9e0f1a2"
down_revision: str | Sequence[str] | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("scenario_roster_abilities", "scenario_roster_revision_abilities")


def upgrade() -> None:
    for table in _TABLES:
        op.alter_column(table, "effect", existing_type=sa.String(50), type_=sa.Text(), existing_nullable=False)


def downgrade() -> None:
    # 反向收窄会丢数据：按 50 字符截断，不阻断回滚。
    for table in _TABLES:
        op.alter_column(
            table,
            "effect",
            existing_type=sa.Text(),
            type_=sa.String(50),
            existing_nullable=False,
            postgresql_using="left(effect, 50)::varchar(50)",
        )
