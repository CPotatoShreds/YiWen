"""用当前生产提示词全量重生成所有奇术因果槽位（复用 ensure_ability_understanding 生产路径）。

失败静默（LlmTrace 记录），可重复执行；执行后核对 llm_traces 失败计数与非 JSON 存量。
用法：uv run python scripts/regenerate_understanding.py
"""

import asyncio

from sqlalchemy import select

from app.db.base import async_session_factory
from app.models.ability import Ability
from app.services.ability_understanding import ensure_ability_understanding

SEM = asyncio.Semaphore(8)


async def main() -> None:
    async with async_session_factory() as db:
        ids = (await db.execute(select(Ability.id))).scalars().all()
    total = len(ids)
    done = 0

    async def runner(aid: str) -> None:
        nonlocal done
        async with SEM:
            await ensure_ability_understanding(aid)
        done += 1
        if done % 20 == 0 or done == total:
            print(f"progress: {done}/{total}", flush=True)

    await asyncio.gather(*(runner(aid) for aid in ids))
    print(f"regenerated: {done}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
