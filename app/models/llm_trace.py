"""LLM 调用追踪：记录每次 LLM 生成的请求输入与模型输出（仅管理端可见）。

独立表、不挂外键：保留历史数据、软关联 trace_id（battle/test_battle/ability/loadout id）。
所有 LLM 调用统一收口在 reliability.ainvoke_with_reliability，传入 trace_context 即落库。
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LlmTrace(Base):
    __tablename__ = "llm_traces"
    __table_args__ = (
        Index("ix_llm_traces_created_at", "created_at"),
        Index("ix_llm_traces_trace_id", "trace_id"),
        Index("ix_llm_traces_operation", "operation"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(20), default="background")  # battle / test_battle / guess / test_guess / background
    operation: Mapped[str] = mapped_column(String(30))  # deduce / transcribe / validate / repair / guess_* / usage / understanding / loadout_interpretation
    status: Mapped[str] = mapped_column(String(10), default="ok")  # ok / fail
    trace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # 业务流关联 id（字符串化）
    request_json: Mapped[object | None] = mapped_column(JSON, nullable=True)  # prompt 消息（list[dict] 或 dict）
    response_json: Mapped[object | None] = mapped_column(JSON, nullable=True)  # 模型输出（BaseModel→dump / str / dict）
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)  # 失败异常摘要（截断）
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    tokens_input: Mapped[int] = mapped_column(Integer, default=0)
    tokens_output: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
