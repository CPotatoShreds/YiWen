"""LLM 调用可靠性层：硬超时 + 指数退避重试 + 日志埋点。

根因背景：此前 `build_chat_model` 未设超时（langchain_openai 把 `timeout=None` 传给
httpx，等于无限等待），外部 API 请求一旦僵死会无限 `await`，后台推演任务既不完结也不
抛异常 → 战斗永久 pending → SSE 永不 done → 前端卡死。本层对所有 LLM 调用施加有界超时，
失败按指数退避重试，耗尽后抛 `ChainFailure` 交由上层降级/中断。

LLM 链路追踪：所有 LLM 调用统一收口在本层。调用方传入 `trace_context`（含 kind / trace_id）
时，每次调用的请求输入与模型输出会异步落库到 `llm_traces`（管理端可查）；不传则零开销、
不落库（保持既有调用与测试行为不变）。
"""

import asyncio
import time

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.runnables import Runnable
from pydantic import BaseModel

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger("reliability")

# 每次 LLM 请求的硬上限（秒）：超过视为失败进入重试，防无限挂起
LLM_TIMEOUT_SECONDS = 120

# 全局 LLM 并发信号量：单 worker 进程内所有 ainvoke 共享。默认取配置 LLM_MAX_CONCURRENCY，
# 防止并发对决累积的在途请求打爆服务商 RPM/TPM（429 风暴下多场同时重试耗尽）。
# 退避重试的 sleep 不占配额——信号量只包住真正的网络请求。
llm_semaphore = asyncio.Semaphore(max(1, settings.LLM_MAX_CONCURRENCY))

# 追踪落库后台任务集合：防 GC 回收未完成的任务
_trace_tasks: set[asyncio.Task] = set()


def _safe_serialize(value) -> object:
    """把任意模型输出/输入序列化为可 JSON 化的对象。

    - pydantic BaseModel（结构化输出）→ model_dump()
    - 含 content/role 的消息对象 → 提取字段转 dict
    - dict / list / str → 原样
    - 其余 → repr 兜底（避免 JSON 落库抛异常）
    """
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, dict):
        return {k: _safe_serialize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_safe_serialize(v) for v in value]
    if isinstance(value, tuple):
        return [_safe_serialize(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    # langchain 消息对象（BaseMessage）：取可读字段
    content = getattr(value, "content", None)
    if content is not None:
        return _safe_serialize(content)
    try:
        return repr(value)
    except Exception:  # noqa: BLE001 - repr 兜底本身不应失败
        return "<unserializable>"


async def _write_trace(
    *,
    kind: str,
    operation: str,
    status: str,
    trace_id: str | None,
    request_json: object | None,
    response_json: object | None,
    error: str | None,
    latency_ms: int,
    tokens_input: int = 0,
    tokens_output: int = 0,
) -> None:
    """异步落库一条 LLM 追踪记录；失败静默（追踪不影响主流程）。"""
    try:
        from app.db.base import async_session_factory
        from app.models.llm_trace import LlmTrace

        async with async_session_factory() as db:
            db.add(
                LlmTrace(
                    kind=kind,
                    operation=operation,
                    status=status,
                    trace_id=trace_id,
                    request_json=request_json,
                    response_json=response_json,
                    error=error,
                    latency_ms=latency_ms,
                    tokens_input=tokens_input,
                    tokens_output=tokens_output,
                )
            )
            await db.commit()
    except Exception:  # noqa: BLE001 - 追踪失败静默，不阻塞 LLM 主流程
        logger.warning("llm_trace_write_failed op=%s status=%s", operation, status)


def _spawn_trace(**kwargs) -> None:
    """fire-and-forget 落库：独立会话 + 后台任务，跟踪集合防 GC。"""
    task = asyncio.create_task(_write_trace(**kwargs))
    _trace_tasks.add(task)
    task.add_done_callback(_trace_tasks.discard)


class ChainFailure(RuntimeError):
    """LLM 调用重试耗尽后抛出：携带操作名与尝试次数，供上层决定降级/中断。"""

    def __init__(self, operation: str, attempts: int, cause: Exception) -> None:
        self.operation = operation
        self.attempts = attempts
        super().__init__(f"LLM 调用失败（{operation}，{attempts} 次尝试均失败）")


class _UsageCaptureCallback(BaseCallbackHandler):
    """捕获单次 LLM 调用的 token 用量。

    挂在 `config={"callbacks": [...]}` 上，`on_llm_end` 同步执行：只读 usage、不 I/O、
    不抛异常（异常吞掉保持 0）。结果存进捕获器自身，由调用方在落库时读取。
    """

    def __init__(self) -> None:
        self.tokens_input: int = 0
        self.tokens_output: int = 0

    def on_llm_end(self, response, **kwargs) -> None:
        try:
            token_usage = (getattr(response, "llm_output", None) or {}).get("token_usage") or {}
            self.tokens_input = int(token_usage.get("prompt_tokens", 0) or 0)
            self.tokens_output = int(token_usage.get("completion_tokens", 0) or 0)
        except Exception:  # noqa: BLE001 - 用量捕获失败保持 0，绝不外抛
            self.tokens_input = 0
            self.tokens_output = 0


async def ainvoke_with_reliability(
    chain,
    kwargs: dict,
    *,
    operation: str,
    max_retries: int = 2,
    base_delay: float = 1.0,
    trace_context: dict | None = None,
) -> object:
    """调用 LLM 链：超时保护 + 指数退避重试 + 日志埋点；重试耗尽抛 ChainFailure。

    `chain.ainvoke(kwargs)` 每轮包 `asyncio.wait_for` 施加 `LLM_TIMEOUT_SECONDS` 硬上限；
    失败按 `base_delay * 2**attempt`（1s、2s）退避后重试。
    `trace_context`（含 kind / trace_id）非空时，请求输入与每次尝试的成败异步落库 `llm_traces`。
    """
    kind = (trace_context or {}).get("kind", "background")
    trace_id = (trace_context or {}).get("trace_id")
    request_json = _safe_serialize(kwargs)
    capture = _UsageCaptureCallback()  # 每次调用一个；重试时后一次 on_llm_end 覆盖前一次
    for attempt in range(max_retries + 1):
        start = time.monotonic()
        try:
            async with llm_semaphore:  # 在途并发超限即排队等待，不额外占配额
                if isinstance(chain, Runnable):
                    # langchain 真链：挂 callback 捕获 token 用量
                    result = await asyncio.wait_for(
                        chain.ainvoke(kwargs, config={"callbacks": [capture]}),
                        timeout=LLM_TIMEOUT_SECONDS,
                    )
                else:
                    # 测试桩等非 langchain 对象：保持原签名调用，避免破坏严格 side_effect
                    result = await asyncio.wait_for(chain.ainvoke(kwargs), timeout=LLM_TIMEOUT_SECONDS)
            latency = int((time.monotonic() - start) * 1000)
            logger.info("llm_ok op=%s attempt=%d dur=%.2fs", operation, attempt, latency / 1000)
            if trace_context:
                _spawn_trace(
                    kind=kind,
                    operation=operation,
                    status="ok",
                    trace_id=trace_id,
                    request_json=request_json,
                    response_json=_safe_serialize(result),
                    error=None,
                    latency_ms=latency,
                    tokens_input=capture.tokens_input,
                    tokens_output=capture.tokens_output,
                )
            return result
        except Exception as e:
            latency = int((time.monotonic() - start) * 1000)
            logger.warning(
                "llm_fail op=%s attempt=%d dur=%.2fs type=%s err=%.200s",
                operation,
                attempt,
                latency / 1000,
                type(e).__name__,
                str(e),
            )
            if trace_context:
                _spawn_trace(
                    kind=kind,
                    operation=operation,
                    status="fail",
                    trace_id=trace_id,
                    request_json=request_json,
                    response_json=None,
                    error=str(e)[:500],
                    latency_ms=latency,
                )
            if attempt < max_retries:
                delay = base_delay * (2**attempt)
                logger.info("llm_retry op=%s attempt=%d wait=%.1fs", operation, attempt, delay)
                await asyncio.sleep(delay)
                continue
            raise ChainFailure(operation, attempt + 1, e) from e
