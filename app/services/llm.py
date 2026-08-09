"""LLM 适配层：langchain ChatOpenAI（OpenAI 兼容协议，默认 DeepSeek）。

结构化输出统一用 `ChatOpenAI.with_structured_output(pydantic_model, method="function_calling")`：
pydantic 字段的 description 即为对模型的字段解释，schema 注入与输出解析交给 langchain。
注意：DeepSeek 对 `method="json_schema"` 返回 400「response_format type unavailable」，
因此必须显式用 function_calling（自动选择也会落到 json_schema，同样失败）。
"""

from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.services.reliability import LLM_TIMEOUT_SECONDS


def build_chat_model(thinking: bool = True, max_tokens: int | None = None) -> ChatOpenAI:
    """构造配置好的 ChatOpenAI。

    - thinking=False 时通过 extra_body 禁用 DeepSeek 思考模式（提速降本，质量略降）。
    - `max_tokens`：输出上限（None 时用模型默认）。一次性推演完整对战这类长输出场景需显式调大，
      否则输出被截断会导致结尾句缺失。
    - 结构化调用：`await build_chat_model().with_structured_output(Model).ainvoke(messages)`。
    - `timeout`：httpx 层请求超时（可靠性层另有 `wait_for` 硬上限，双保险防无限挂起）。
    """
    s = get_settings()
    kwargs: dict = {
        "api_key": s.LLM_API_KEY,
        "base_url": s.LLM_BASE_URL or None,
        "model": s.LLM_MODEL,
        "timeout": LLM_TIMEOUT_SECONDS,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if not thinking:
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    return ChatOpenAI(**kwargs)
