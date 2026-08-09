"""提权/撤销管理员。

用法：uv run python -m scripts.make_admin <用户名> [--revoke]
- 不带 --revoke：把指定异闻师设为管理员（后台可登录）
- 带 --revoke：取消其管理员权限
- 用户名不存在时打印提示并退出码 1

导出 set_admin() 供测试直接复用。
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.db.base import async_session_factory
from app.models.user import User


async def set_admin(username: str, admin: bool = True) -> bool:
    """设置/取消管理员。返回是否找到该异闻师。"""
    async with async_session_factory() as db:
        user = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
        if user is None:
            return False
        user.is_admin = admin
        await db.commit()
        return True


async def main() -> None:
    parser = argparse.ArgumentParser(description="设置或取消管理员权限")
    parser.add_argument("username", help="异闻师名号")
    parser.add_argument("--revoke", action="store_true", help="取消管理员权限")
    args = parser.parse_args()

    found = await set_admin(args.username, admin=not args.revoke)
    if not found:
        print(f"未找到异闻师: {args.username}")
        raise SystemExit(1)
    action = "撤销" if args.revoke else "设为"
    print(f"已{action}管理员: {args.username}")


if __name__ == "__main__":
    asyncio.run(main())
