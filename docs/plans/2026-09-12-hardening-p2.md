# P2 · 规模化前

- 状态：✅ 已完成（2026-09-13；第 4 项 arq 为 opt-in 交付，默认 inline）
- 创建：2026-09-12
- 粒度：原为概要，2026-09-13 经用户指示直接实现

## 执行记录（2026-09-13）

1. **RBAC + 管理审计** ✅ `users.role`（user/admin）替换 `is_admin` 列——模型保留 `is_admin` 属性做兼容，管理 API 字段名不变（前端零改动）；迁移 `d2e3f4a5b6c7` 自动回填存量管理员。`admin_audit_logs` 表 + `app/core/audit.py` 埋点：admin 域用户/奇术全部写操作、scenario 管理端建卷/改卷/发布/删除全部留痕；新增 `GET /admin/audit-logs` 查询。
2. **分页 + 错误码信封** ✅ admin users/abilities/llm-traces 补 `limit/offset`（默认保持旧行为不破坏前端）；`AppError`（`app/core/errors.py`）→ 响应 `{detail, code}` + `X-Error-Code` 头，认证域全量接入，前端 `detailMessage` 兼容信封。其余域按此模式渐进迁移。
3. **/metrics** ✅ prometheus-fastapi-instrumentator（HTTP QPS/延迟）+ 业务埋点：`ynfight_llm_calls_total{operation,outcome}`（reliability 层收口处计数）、`ynfight_sse_streams_active` 在途订阅 gauge。`METRICS_ENABLED` 开关。
4. **任务队列化** ✅ `app/core/tasks.py` 派发层 + `app/worker.py` arq worker + `tasks_registry.py` 注册表；4 个任务启动点（比对/推演/猜词轮/检定）全部改走 `dispatch()`。**交付为 opt-in**：`TASK_QUEUE_MODE=inline`（默认）行为与旧版一致（测试/dev 零依赖）；`arq` 模式获得重试（max_tries=3）与崩溃恢复，需另起 `uv run arq app.worker.WorkerSettings`。与 P1.4 僵尸清理互补：arq 模式下队列自恢复，inline 模式靠启动扫描兜底。
5. **数据保留** ✅ `app/core/retention.py`：每日清理循环随 lifespan 常驻——llm_traces 90 天、request_logs 30 天（`LLM_TRACE_RETENTION_DAYS`/`REQUEST_LOG_RETENTION_DAYS`，0=永久）、过期/吊销超 7 天的 refresh_tokens。
6. **类型检查** ✅ `[tool.mypy]` 配置（files=app/core，12 文件 0 错误）+ CI 非阻塞步骤；后续按域逐步扩 `files`。

## 验证
pytest 全量 60/60（新增 test_p2_p3.py：审计留痕/角色映射/信封/注销/导出/保留清理/metrics）；ruff 全绿；mypy（app/core）0 错误；前端 tsc 通过。

## 明确不做（遗留）
错误码信封全域铺开（模式已立，随迭代迁移）；mypy 扩到 routes/tests。
