"""Rename `scenario_challenge_runs.is_preview` to `is_trial`.

`is_preview` 这个名字是历史遗留：它当初被当作"这一局是否可见/是否作者自看"的开关，
后来可见性改由关系现算（`views.sees_all` 与 `challenger|guardian|both` 侧别），
这个布尔只剩下唯一含义——**这一局是作者对自己的刻印发起的试炼，不计入公开统计**
（次数、胜率、首胜均值、猜词次数）。

留着旧名会让后来人继续误以为它是可见性开关，故做一次纯机械重命名，语义不变、数据不变。
"""
from collections.abc import Sequence

from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: str | Sequence[str] | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "scenario_challenge_runs"
_OLD_COLUMN = "is_preview"
_NEW_COLUMN = "is_trial"


def upgrade() -> None:
    op.drop_index(f"ix_{_TABLE}_{_OLD_COLUMN}", table_name=_TABLE)
    op.alter_column(_TABLE, _OLD_COLUMN, new_column_name=_NEW_COLUMN)
    op.create_index(f"ix_{_TABLE}_{_NEW_COLUMN}", _TABLE, [_NEW_COLUMN])


def downgrade() -> None:
    op.drop_index(f"ix_{_TABLE}_{_NEW_COLUMN}", table_name=_TABLE)
    op.alter_column(_TABLE, _NEW_COLUMN, new_column_name=_OLD_COLUMN)
    op.create_index(f"ix_{_TABLE}_{_OLD_COLUMN}", _TABLE, [_OLD_COLUMN])
