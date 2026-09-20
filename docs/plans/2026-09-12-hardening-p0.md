# P0 · 上线底线

- 状态：✅ 已完成（2026-09-12；CI 待推送后 Actions 首跑验证）
- 创建：2026-09-12
- 定案方式：grilling 两轮，本批 5 项为公网开放前的安全与运维底线
- 前置说明：生产部署形态为云环境（具体待定），本批各项均设计为环境无关

## 执行记录（2026-09-12）
1. **SECRET_KEY 校验** ✅ `DEV_DEFAULT_SECRET` 哨兵常量 + lifespan 断言，非 DEBUG 拒绝启动。
2. **限流** ✅ 有偏离：slowapi 的 `SlowAPIMiddleware` 是 BaseHTTPMiddleware（本项目因 SSE 明令禁用），其纯 ASGI 变体又会扣押 `http.response.start` 到首个 body（SSE 空窗恰撞前端 15s 连接超时）——故放弃"全局默认限流"，改**纯装饰器模式**：登录 5/min、注册 10/min、创建挑战 30/min（阈值进 config，测试环境经 conftest 放开）。登录失败锁定按计划（Redis 计数 5 次/15 分钟，Redis 挂则放行 + IP 限流兜底）。
3. **双 token** ✅ `refresh_tokens` 表（迁移 `c7d8e9f0a1b2`，sha256 哈希落库）+ `/auth/refresh` 旋转 + 复用检测全量吊销 + 登出吊销；access 24h→2h；refresh cookie 限路径 `/api/auth`；前端 `api.ts` 统一 401 → refresh → 重放。测试覆盖旋转/复用检测/登出吊销。
4. **CI** ✅ `.github/workflows/ci.yml`：postgres+redis services、ruff、pytest、pip-audit（continue-on-error 观察）。**未验证项：需推送后看 Actions 首跑**。
5. **备份** ✅ `scripts/backup_db.sh`（pg_dump -Fc，7 天滚动）+ `restore_db.sh` + `docs/数据库备份与恢复.md`；**演练已做**：备份 33M → 恢复到临时库 → users/challenges 行数与主库一致 → 清理。
   **异地副本（2026-09-15 收口）**：部署环境定为腾讯云 CVM + docker compose（见 `deploy/`）。按用户决策**不做云端异地（COS）**，改为定时导出到本机：新增 `scripts/pull_backup.sh`（服务器拉最新 dump → 本机滚动保留 30 份）；服务器 cron（每日备份、每周自动恢复演练）与 Windows 任务计划程序示例已写入 `docs/数据库备份与恢复.md`。

## 背景
全站当前无任何限流（登录可暴力试密码）；`SECRET_KEY` 默认值 `dev-secret-change-me` 且无启动校验（`app/core/config.py:34`），生产漏配即可伪造任意用户 token；登录凭证为 24h 无状态 JWT，登出仅删 Cookie、到期前始终有效；无 CI（`.github/workflows` 不存在，测试靠手动）；Postgres 无备份策略。

## 任务明细

### 1. SECRET_KEY 启动校验（约 10 分钟）
`app/main.py` lifespan 中断言：非 DEBUG 模式下 `settings.SECRET_KEY` 等于默认值时抛异常拒绝启动。
验证：`DEBUG=false SECRET_KEY=dev-secret-change-me uv run uvicorn app.main:app` 应启动失败。

### 2. 限流（约 1 天）——选型：slowapi（已定案）
- `uv add slowapi`；`Limiter(storage_uri=settings.REDIS_URL)` 使多实例共享计数（依赖 limits 库的 Redis 存储）。
- 策略：`POST /auth/login` 严格限（建议 5 次/分钟/IP+用户名双键）；注册、创建挑战宽松限；全局默认限（建议 120 次/分钟/IP）。挂 `SlowAPIMiddleware` 于 `app/main.py`。
- 注意：slowapi 在 Redis 不可用时抛异常而非静默放行，与项目"可降级"哲学有出入——实现时二选一：包装异常放行+warning，或明确接受 Redis 为硬依赖（多实例本就需要 Redis），结论写进代码注释。
- 登录失败锁定并入本项：同一用户名连续失败 5 次锁 15 分钟（Redis 计数，可降级为仅限流）。
验证：pytest 触发 429 用例 + 手动循环 curl 登录观察 429。

### 3. access + refresh 双 token（约 2~3 天）——选型：标准双 token（已定案）
- 新表 `refresh_tokens`：id, user_id(FK), token_hash(sha256), expires_at, revoked_at, created_at（Alembic 迁移；明文不落库）。
- access 24h→2h（config.py:36）；refresh 30 天，`/auth/refresh` 旋转（旧 token 置 revoked、签发新对）；检测到已撤销 token 被复用即撤销该用户全部 refresh（防盗用）。
- `POST /auth/logout` 撤销当前 refresh；`get_current_user` 不变。
- 前端：api 层统一 401 拦截 → refresh → 重放原请求 → 失败才跳登录；sse.ts 的 Cookie 会话自动获益。
验证：pytest（登录→旋转→旧 refresh 复用触发全撤销→logout 吊销）+ 前端手测跨 2h 续签。

### 4. CI：GitHub Actions（约 1 天）
仓库已在 GitHub（CPotatoShreds/YiWen）。`.github/workflows/ci.yml`：ubuntu-latest + services 起 postgres:16 与 redis:7（带 allkeys-lru 参数与 compose 一致）；步骤 setup-uv → `uv sync` → `uv run ruff check .` → `uv run pytest`。
注意：conftest 需要的 Postgres 由 services 满足；LLM 相关 key 走 GitHub Secrets 注入。
验证：推送分支观察 Actions 绿。

### 5. 数据库备份（约半天 + 演练）
环境无关：`pg_dump -Fc` 定时，保留 7 天滚动 + 每日外拷（对象存储/另一台机，具体目标随部署形态定，标注待定）。落地形态二选一：宿主机 cron 或 compose 侧 cron 容器。附恢复演练文档：空库 `pg_restore` 全流程跑通一次才算完成。
验证：演练记录追加到本文件执行记录区。

## 执行记录
（执行时追加：日期、实际改动、偏离决策的原因）

## 明确不做
安全响应头、邮件体系、结构化日志、告警平台（属 P1）；部署拓扑变更。
