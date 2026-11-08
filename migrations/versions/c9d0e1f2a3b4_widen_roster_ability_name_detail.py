"""Widen roster ability snapshot `name` and `detail` columns to match abilities.

接续 b7c8d9e0f1a2（该次把 `effect` 放宽为 text）。快照表另两列同样窄于源表：

    abilities.name    varchar(50)  ->  快照 name    varchar(10)
    abilities.detail  text         ->  快照 detail  varchar(500)

拓印（app/api/routes/scenario_domain.py::creator_create_roster）是把 abilities 的行
原样复制进这两张快照表，中间没有 schema 校验、也没有截断，因此凡是「源表比目标表宽」
的字段都有同样的 500 风险（asyncpg StringDataRightTruncationError）。

`effect` 因为存量 84 门旧奇术已经暴露；`name` / `detail` 只是当前存量数据恰好没超
（最长 8 字 / 216 字），结构风险与 effect 相同。快照的语义是冻结当时的内容，应当
完整承载源字段，故一并放宽到与 abilities 对齐。

creator/admin 入参 schema 的 10 / 500 上限不动 —— 它约束的是新建奇术，管不到快照。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: str | Sequence[str] | None = "b7c8d9e0f1a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("scenario_roster_abilities", "scenario_roster_revision_abilities")


def upgrade() -> None:
    for table in _TABLES:
        op.alter_column(table, "name", existing_type=sa.String(10), type_=sa.String(50), existing_nullable=False)
        op.alter_column(table, "detail", existing_type=sa.String(500), type_=sa.Text(), existing_nullable=False)


def downgrade() -> None:
    # 反向收窄会丢数据：按原列宽截断，不阻断回滚。
    for table in _TABLES:
        op.alter_column(
            table,
            "name",
            existing_type=sa.String(50),
            type_=sa.String(10),
            existing_nullable=False,
            postgresql_using="left(name, 10)::varchar(10)",
        )
        op.alter_column(
            table,
            "detail",
            existing_type=sa.Text(),
            type_=sa.String(500),
            existing_nullable=False,
            postgresql_using="left(detail, 500)::varchar(500)",
        )
