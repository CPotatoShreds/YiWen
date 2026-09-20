"""后台管理 API schemas。"""
from datetime import datetime

from pydantic import BaseModel, Field


class AdminUserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=20)
    password: str = Field(min_length=6, max_length=64)
    is_admin: bool = False

class AdminUserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=2, max_length=20)
    password: str | None = Field(default=None, min_length=6, max_length=64)
    is_admin: bool | None = None

class AdminUserOut(BaseModel):
    id: int
    username: str
    is_admin: bool
    created_at: datetime
    ability_count: int = 0

class AbilityAdminIn(BaseModel):
    name: str = Field(max_length=10)
    effect: str = Field(max_length=50)
    detail: str | None = Field(default=None, max_length=500)
    owner_id: int | None = None

class RequestLogOut(BaseModel):
    id: int
    method: str
    path: str
    status_code: int
    duration_ms: int
    user_id: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

class DailyPoint(BaseModel):
    date: str
    count: int

class EndpointStat(BaseModel):
    path: str
    count: int
    avg_ms: float

class TrafficOut(BaseModel):
    total_requests: int
    last_24h: int
    avg_ms: float
    daily: list[DailyPoint]
    endpoints: list[EndpointStat]
    recent: list[RequestLogOut]

class StatsOut(BaseModel):
    total_users: int
    total_abilities: int

class LlmTraceOut(BaseModel):
    id: int
    kind: str
    operation: str
    status: str
    trace_id: str | None = None
    error: str | None = None
    latency_ms: int
    tokens_input: int
    tokens_output: int
    created_at: datetime

    model_config = {"from_attributes": True}

class LlmTraceDetailOut(LlmTraceOut):
    request_json: object | None = None
    response_json: object | None = None

class LlmTraceOpStat(BaseModel):
    operation: str
    count: int
    fail_count: int
    avg_ms: float

class LlmTraceStatsOut(BaseModel):
    total: int
    fail_total: int
    by_operation: list[LlmTraceOpStat]
