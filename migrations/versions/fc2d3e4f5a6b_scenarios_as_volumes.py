"""Rebuild scenarios as volumes and seed the first volume."""
from collections.abc import Sequence
from uuid import UUID

import bcrypt
import sqlalchemy as sa
from alembic import op

revision = "fc2d3e4f5a6b"
down_revision: str | Sequence[str] | None = "fb1c2d3e4f5a"
branch_labels = None
depends_on = None

VOLUME_ID = UUID("20000000-0000-4000-8000-000000000001")
SUOWENG = "蓑翁"
SUOWENG_PASSWORD_HASH = bcrypt.hashpw(b"suoweng123", bcrypt.gensalt()).decode()


def upgrade() -> None:
    bind = op.get_bind()

    # Challenge rows reference rosters with RESTRICT; clear the whole old playset first.
    op.execute(sa.text("DELETE FROM scenario_challenge_runs"))
    op.execute(sa.text("DELETE FROM scenario_rosters"))
    op.execute(sa.text("DELETE FROM scenarios"))

    op.drop_column("scenarios", "summary")
    op.add_column("scenarios", sa.Column("subtitle", sa.String(60), nullable=False, server_default=""))
    op.add_column("scenarios", sa.Column("introduction", sa.String(120), nullable=False, server_default=""))
    op.add_column("scenarios", sa.Column("rules", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("scenarios", sa.Column("judgement_rules", sa.JSON(), nullable=False, server_default="[]"))

    users = sa.table(
        "users",
        sa.column("id", sa.Integer),
        sa.column("username", sa.String),
        sa.column("password_hash", sa.String),
        sa.column("is_admin", sa.Boolean),
    )
    user_id = bind.execute(sa.select(users.c.id).where(users.c.username == SUOWENG)).scalar_one_or_none()
    if user_id is None:
        user_id = bind.execute(
            users.insert().values(
                username=SUOWENG,
                password_hash=SUOWENG_PASSWORD_HASH,
                is_admin=True,
            ).returning(users.c.id)
        ).scalar_one()
    else:
        bind.execute(
            users.update()
            .where(users.c.id == user_id)
            .values(password_hash=SUOWENG_PASSWORD_HASH, is_admin=True)
        )

    scenarios = sa.table(
        "scenarios",
        sa.column("id", sa.Uuid),
        sa.column("created_by", sa.Integer),
        sa.column("name", sa.String),
        sa.column("normalized_name", sa.String),
        sa.column("subtitle", sa.String),
        sa.column("introduction", sa.String),
        sa.column("background", sa.Text),
        sa.column("rules", sa.JSON),
        sa.column("victory_condition", sa.String),
        sa.column("judgement_rules", sa.JSON),
        sa.column("status", sa.String),
        sa.column("published_at", sa.DateTime),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    bind.execute(
        scenarios.insert().values(
            id=VOLUME_ID,
            created_by=user_id,
            name="封喉卷",
            normalized_name="封喉卷",
            subtitle="见招拆招，一剑封喉",
            introduction="正面对决，击溃对手",
            background="双方将被传送到一个半径三十米的圆形结界中，初始位置的间距同样也是三十米。倒计时归零的一瞬间，对决正式敲响。",
            rules=[
                "任何移动到结界外的行为将被无效化",
                "任何将对手移动到结界外的行为将被无效化",
            ],
            victory_condition="让对方死亡或失去战斗能力",
            judgement_rules=["双方皆失去战斗能力判定为失败"],
            status="published",
            published_at=sa.func.now(),
            created_at=sa.func.now(),
            updated_at=sa.func.now(),
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    scenarios = sa.table("scenarios", sa.column("id", sa.Uuid))
    bind.execute(scenarios.delete().where(scenarios.c.id == VOLUME_ID))

    op.add_column("scenarios", sa.Column("summary", sa.String(120), nullable=False, server_default=""))
    op.drop_column("scenarios", "judgement_rules")
    op.drop_column("scenarios", "rules")
    op.drop_column("scenarios", "introduction")
    op.drop_column("scenarios", "subtitle")
