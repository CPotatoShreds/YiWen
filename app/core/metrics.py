"""Prometheus 业务指标：LLM 调用与在途 SSE 订阅。HTTP 指标由 instrumentator 托管。

所有埋点必须吞异常——指标绝不能影响业务主流程。
"""

from prometheus_client import Counter, Gauge

LLM_CALLS_TOTAL = Counter("ynfight_llm_calls_total", "LLM 调用计数", ["operation", "outcome"])
SSE_STREAMS_ACTIVE = Gauge("ynfight_sse_streams_active", "在途 SSE 事件订阅数")


def record_llm_call(operation: str, outcome: str = "ok") -> None:
    try:
        LLM_CALLS_TOTAL.labels(operation=operation, outcome=outcome).inc()
    except Exception:  # noqa: BLE001, S110 - 指标失败绝不影响业务
        pass
