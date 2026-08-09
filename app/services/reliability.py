"""LLM 调用可靠性层：硬超时 + 指数退避重试 + 日志埋点。

根因背景：此前 `build_chat_model` 未设超时（langchain_openai 把 `timeout=None` 传给
httpx，等于无限等待），外部 API 请求一旦僵死会无限 `await`，后台推演任务既不完结也不
抛异常 → 战斗永久 pending → SSE 永不 done → 前端卡死。本层对所有 LLM 调用施加有界超时，
失败按指数退避重试，耗尽后抛 `ChainFailure` 交由上层降级/中断。
"""

import asyncio
import time

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger("reliability")

# 每次 LLM 请求的硬上限（秒）：超过视为失败进入重试，防无限挂起
LLM_TIMEOUT_SECONDS = 120

# 全局 LLM 并发信号量：单 worker 进程内所有 ainvoke 共享。默认取配置 LLM_MAX_CONCURRENCY，
# 防止并发对决累积的在途请求打爆服务商 RPM/TPM（429 风暴下多场同时重试耗尽）。
# 退避重试的 sleep 不占配额——信号量只包住真正的网络请求。
llm_semaphore = asyncio.Semaphore(max(1, settings.LLM_MAX_CONCURRENCY))


class ChainFailure(RuntimeError):
    """LLM 调用重试耗尽后抛出：携带操作名与尝试次数，供上层决定降级/中断。"""

    def __init__(self, operation: str, attempts: int, cause: Exception) -> None:
        self.operation = operation
        self.attempts = attempts
        super().__init__(f"LLM 调用失败（{operation}，{attempts} 次尝试均失败）")


async def ainvoke_with_reliability(
    chain,
    kwargs: dict,
    *,
    operation: str,
    max_retries: int = 2,
    base_delay: float = 1.0,
) -> object:
    """调用 LLM 链：超时保护 + 指数退避重试 + 日志埋点；重试耗尽抛 ChainFailure。

    `chain.ainvoke(kwargs)` 每轮包 `asyncio.wait_for` 施加 `LLM_TIMEOUT_SECONDS` 硬上限；
    失败按 `base_delay * 2**attempt`（1s、2s）退避后重试。
    """
    for attempt in range(max_retries + 1):
        start = time.monotonic()
        try:
            async with llm_semaphore:  # 在途并发超限即排队等待，不额外占配额
                result = await asyncio.wait_for(chain.ainvoke(kwargs), timeout=LLM_TIMEOUT_SECONDS)
            logger.info("llm_ok op=%s attempt=%d dur=%.2fs", operation, attempt, time.monotonic() - start)
            return result
        except Exception as e:
            logger.warning(
                "llm_fail op=%s attempt=%d dur=%.2fs type=%s err=%.200s",
                operation,
                attempt,
                time.monotonic() - start,
                type(e).__name__,
                str(e),
            )
            if attempt < max_retries:
                delay = base_delay * (2**attempt)
                logger.info("llm_retry op=%s attempt=%d wait=%.1fs", operation, attempt, delay)
                await asyncio.sleep(delay)
                continue
            raise ChainFailure(operation, attempt + 1, e) from e
