"""后台任务派发：把"启动一个后台任务"与执行介质解耦（P2.4）。

- inline（默认）：进程内 create_task，行为与历史版本一致，开发/测试零依赖；
- arq：入队到独立 worker 进程（重试 + 崩溃恢复），TASK_QUEUE_MODE=arq 时启用，
  需另起 `uv run arq app.worker.WorkerSettings`。

切换只改配置，任务函数本身不动——名字到协程工厂的映射见
app/services/scenario/tasks_registry.py。
"""

import asyncio
from typing import TYPE_CHECKING

from app.core.config import settings
from app.core.logger import get_logger

if TYPE_CHECKING:
    from arq.redis import ArqRedis

logger = get_logger("tasks")

_pools: dict[int, "ArqRedis"] = {}  # arq pool 按事件循环缓存（连接绑定 loop）


async def dispatch(task_name: str, *args) -> None:
    if settings.TASK_QUEUE_MODE != "arq":
        from app.services.scenario.tasks_registry import resolve

        asyncio.create_task(resolve(task_name, *args))
        return

    from arq import create_pool
    from arq.connections import RedisSettings

    loop = asyncio.get_running_loop()
    pool = _pools.get(id(loop))
    if pool is None:
        pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
        _pools[id(loop)] = pool
    await pool.enqueue_job("run_scenario_task", task_name, *args)
    logger.info("task_enqueued name=%s", task_name)
