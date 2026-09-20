"""arq worker：运行小天下集后台任务（TASK_QUEUE_MODE=arq 时使用）。

启动：uv run arq app.worker.WorkerSettings
生产以独立进程常驻；任务失败自动重试（max_tries），进程崩溃的任务随 Redis 队列恢复。
"""

from typing import ClassVar

from arq import func
from arq.connections import RedisSettings

from app.core.config import get_settings


async def run_scenario_task(ctx, task_name: str, *args) -> None:
    from app.services.scenario.tasks_registry import resolve

    await resolve(task_name, *args)


class WorkerSettings:
    functions: ClassVar[list] = [func(run_scenario_task, name="run_scenario_task")]
    redis_settings = RedisSettings.from_dsn(get_settings().REDIS_URL)
    max_tries = 3
    job_timeout = 1800  # 秒：LLM 推演链可能较慢
    keep_result = 0
    max_jobs = 8
