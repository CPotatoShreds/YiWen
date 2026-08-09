"""添加对战测试用户（bot_*）：直接插库，赋予自定义异能。

用法：uv run python -m scripts.seed_users
密码统一 bot123456；重复运行会跳过已存在的 bot。
每个 bot 拥有 1-2 个自定义异能（对应"用户自己输入异能"的玩法）。
"""

from __future__ import annotations

import asyncio
import hashlib
import random

import bcrypt
from sqlalchemy import select

from app.db.base import async_session_factory
from app.models.ability import Ability
from app.models.loadout import Loadout, LoadoutAbility
from app.models.user import User
from app.models.user_ability import UserAbility

# (bot名, 主异能, 辅助异能或 None)
BOTS = [
    ("赤焰君临", "燃烬之握：接触的物体被点燃为不会熄灭的火焰，火焰温度随心念升降", None),
    ("霜语者", "绝对零域：以自身为圆心冻结一定半径内的一切水分，包括空气中的", None),
    ("虚空旅人", "相位穿梭：身体在虚实之间切换，可短暂穿过实体与攻击", None),
    ("千面织影", "影子织造：操纵影子编织成实体傀儡，替自己行动与承受伤害", None),
    ("时间摆渡人", "定格三秒：对一个目标施加三秒的完全静止，冷却较长", None),
    ("星屑收集者", "引力牵引：将视线内的重物以引力拉扯砸向目标", "万有之眼：锁定一个目标后，其上的引力短时加倍"),
    ("影流主宰", "暗影蚀咬：潜入对方影子中，从影中发起无声的攻击", None),
    ("深渊回响", "回响复制：复刻对手上一次施展的异能效果并延迟释放", None),
]
BOT_PASSWORD = "bot123456"


def _ability_id(user_id: int, name: str, effect: str) -> str:
    """与 API 创建异能同一套 id 规则（内容哈希）。"""
    return hashlib.sha256(f"{user_id}:{name}:{effect}".encode()).hexdigest()[:16]


async def main() -> None:
    async with async_session_factory() as db:
        rng = random.Random(20260805)
        created = 0
        for name, main_ability, sub_ability in BOTS:
            uname = f"bot_{name}"
            exists = (await db.execute(select(User).where(User.username == uname))).scalar_one_or_none()
            if exists:
                print(f"跳过已存在: {uname}")
                continue

            exp = rng.randint(50, 300)
            user = User(
                username=uname,
                password_hash=bcrypt.hashpw(BOT_PASSWORD.encode(), bcrypt.gensalt()).decode(),
                rank_points=rng.randint(880, 1120),  # 名望差异化，让 Elo 有意义
                exp=exp,
            )
            db.add(user)
            await db.flush()

            # 注册不赠送默认奇人：每位 bot 显式立起一位带名奇人（名 = 昵称，解封），异能装入其下
            nickname = name.split("_", 1)[1] if "_" in name else name
            loadout = Loadout(user_id=user.id, name=nickname, enabled=True)
            db.add(loadout)
            await db.flush()

            abilities = [main_ability] + ([sub_ability] if sub_ability else [])
            for ability_txt in abilities:
                ability_name, ability_effect = ability_txt.split("：", 1)
                aid = _ability_id(user.id, ability_name, ability_effect)
                if await db.get(Ability, aid) is None:
                    db.add(Ability(id=aid, name=ability_name, effect=ability_effect))
                db.add(UserAbility(user_id=user.id, ability_id=aid))
                db.add(LoadoutAbility(loadout_id=loadout.id, ability_id=aid))

            created += 1
            print(f"创建 {uname}: 见闻{user.exp} 名望{user.rank_points} 异能{len(abilities)}")

        await db.commit()
        print(f"\n共创建 {created} 个测试用户（密码 {BOT_PASSWORD}）")


if __name__ == "__main__":
    asyncio.run(main())
