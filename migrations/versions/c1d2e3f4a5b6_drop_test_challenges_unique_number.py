"""清空测试对局数据并为内部序号加正式局唯一约束。

`challenge_number` 降级为内部序号：正式局等于 attempts 递增结果，试炼局恒 1，
两者都不再对外下发（面向用户的是 created_at 时间戳）。它现在唯一的职责是配合下面的
partial unique index，让并发创建时同一 attempts 只能落一条记录。

约束必须排除试炼局（`is_trial = false`）：试炼局序号恒 1，作者连打多局会撞全量唯一约束。

升级前清空全部对局与进度——库里 41 条全为测试数据（均 is_trial=true、序号均为 1），
不清理就与唯一约束冲突。数据清理不可逆，downgrade 不恢复。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: str | Sequence[str] | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "uq_scenario_challenge_runs_number"
_TABLE = "scenario_challenge_runs"


def upgrade() -> None:
    op.execute(f"DELETE FROM {_TABLE}")
    op.execute("DELETE FROM scenario_roster_progress")
    op.execute(
        "UPDATE scenario_rosters SET challenge_count = 0, completed_count = 0, "
        "first_victory_avg_challenges = NULL"
    )
    op.create_index(
        _INDEX,
        _TABLE,
        ["roster_id", "challenger_id", "challenge_number"],
        unique=True,
        postgresql_where=sa.text("is_trial = false"),
        sqlite_where=sa.text("is_trial = false"),
    )


def downgrade() -> None:
    op.drop_index(_INDEX, table_name=_TABLE)
