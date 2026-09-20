# ynfight 生产部署

Docker 部署到服务器（腾讯云 CVM）：**3 个容器**（`postgres` + `redis` + `app`），`app` 容器内的 FastAPI 同时服务 API 与前端静态文件。

```
浏览器 ──► app:8102（uvicorn）
              ├── /api/*       业务接口（含 SSE 推演流）
              └── /assets + /  前端静态文件 + SPA 回退（构建产物打进镜像）
                    ├── 数据卷 appdata:/app/data（日志、SECRET_KEY、LLM 方案密钥）
                    ├── postgres:5432  数据库（卷 pgdata）
                    └── redis:6379     事件总线/缓存/限流/锁（卷 redisdata）
```

## 关键约束（改动前先读）

- **SSE 推演流走 Redis 事件总线**（`app/services/scenario/stream.py`）：跨实例投递 + 回放流，**app 可多 worker / 多副本**（都用同一 Redis）。当前默认单进程起步（规模不需要扩），要扩容时给 uvicorn 加 `--workers N` 或加 app 副本，无需改代码。
- **Redis 必须部署**：事件总线、比对缓存、限流计数、登录失败锁定、arq 队列共用它。全部链路可降级（Redis 挂时服务不中断、退化为单进程语义），但没有它功能不完整。
- **无 nginx（当前）**：同源部署 + 无代理层。将来配 HTTPS 时在 `8102` 前叠一层 nginx/caddy 即可，后端代码不用动（`app/core/middleware.py` 注明 SSE 透传要求：代理需关闭响应缓冲，如 nginx `proxy_buffering off`）。
- **单文件镜像**：前端由 `Dockerfile` Stage 1 构建后拷入后端镜像 `static/`，`app/main.py` 挂载 `/assets` + SPA 回退。

## 首次部署

前置：服务器安装 Docker 与 Compose plugin（`docker compose version` 可用），并配置 git 拉取凭据（deploy key / PAT，能让 `git pull` 免交互通过）。

```bash
# 1. 首次部署：服务器自动从本地 origin git clone 并构建启动（本地跑，Windows Git Bash / WSL / macOS 均可）
SERVER=user@server-ip ./deploy/deploy.sh

# 2. 编辑服务器上的生产环境变量（含真实密钥，勿提交到 git）
ssh user@server-ip
nano ~/ynfight/deploy/.env.production
#    POSTGRES_PASSWORD   改为强随机值
#    LLM_API_KEY         填入 LLM Key
#    AUTH_COOKIE_SECURE  服务器无 HTTPS 必须 false；配好 HTTPS 后改 true
#    PUBLIC_FRONTEND_URL 邮件链接指向：无域名填 http://<服务器IP>:8102
#    EMAIL_* / SMTP_*    要真发邮件（找回密码）时按 .env.production.example 指引配 SMTP
#    LOG_JSON=true       生产建议开启（结构化日志，供日志采集）
#    其余新增项从 .env.production.example 拷贝补齐

# 3. 再次部署生效
SERVER=user@server-ip ./deploy/deploy.sh
```

`SECRET_KEY` 不需要填：`entrypoint.sh` 首次启动自动生成并持久化到卷 `appdata` 的 `/app/data/secret_key`，重部署不覆盖（已签发 JWT 不失效）。容器启动时自动执行 `alembic upgrade head`。

## 升级

```bash
SERVER=user@server-ip ./deploy/deploy.sh   # 服务器 git pull 最新代码 + --build 重建 + 迁移
```

## 常用运维

```bash
ssh user@server-ip
cd ~/ynfight
docker compose --env-file deploy/.env.production -f deploy/docker-compose.prod.yml ps    # 状态
docker compose --env-file deploy/.env.production -f deploy/docker-compose.prod.yml logs -f app   # 日志
docker compose --env-file deploy/.env.production -f deploy/docker-compose.prod.yml restart app   # 重启（启动时自动清理僵尸挑战）
```

## 备份 / 迁移

数据库每日自动备份（服务器 cron，7 天滚动）+ 定时拉回本机（`scripts/pull_backup.sh`，异地副本的最简形式，无需对象存储）——脚本、cron 与 Windows 任务计划程序示例见 **[docs/数据库备份与恢复.md](../docs/数据库备份与恢复.md)**。

应用数据卷（SECRET_KEY、LLM 方案密钥、日志——迁移机器必须带走密钥文件）：

```bash
docker run --rm -v ynfight_appdata:/appdata -v "$PWD":/backup alpine \
  tar czf /backup/appdata.tar.gz -C /appdata .
```

## 可观测性

- **/metrics**（Prometheus）：HTTP QPS/延迟、`ynfight_llm_calls_total`（LLM 调用成败）、`ynfight_sse_streams_active`（在途推演订阅）。**不要对公网裸奔**——在腾讯云安全组或反代层限制来源 IP。
- **日志**：`LOG_JSON=true` 输出 JSON 行；容器日志 `docker compose logs` 可直接看。腾讯云内推荐两条路：
  1. **CLS 日志服务（推荐，数据不出境、零新增容器）**：CVM 安装日志采集器 → 采集 app 容器 stdout（或 `appdata` 卷内 `data/logs/app-*.log`）→ 建日志主题 → 按 `level=ERROR` 或 5xx 比例配告警策略推到微信/邮件；
  2. **自托管 GlitchTip**（开源、兼容 Sentry 协议、异常聚合最专业）：生产编排里加一个容器，`app` 设 `SENTRY_DSN` 指向它——接入代码尚未加，启用前需先在 `app/main.py` 引入 sentry-sdk（约 5 行）。
  - 未接入前：告警靠 CLS 策略或人工看日志。

## HTTPS / 域名（待办）

拿到域名后：CVM 前叠 nginx（或腾讯云 CLB）+ 证书 → `AUTH_COOKIE_SECURE=true`、`PUBLIC_FRONTEND_URL=https://域名`、`CORS_ORIGINS` 视情况 → 重跑 deploy.sh。nginx 必须 `proxy_buffering off`（SSE）。

## 排障

| 现象 | 排查 |
|---|---|
| 登录后刷新即登出 | `AUTH_COOKIE_SECURE` 与服务器协议不匹配：无 HTTPS 必须 `false` |
| `/api/health` 返回 503 | postgres 未就绪；`docker compose logs postgres` 查看，或检查 `POSTGRES_PASSWORD` 是否已改但 `pgdata` 卷用了旧口令（重建卷：`docker compose down -v`，注意会清数据） |
| health 里 redis=fail | `docker compose logs redis`；Redis 挂不影响主流程（降级），但事件总线退化为单实例语义 |
| 找回密码收不到邮件 | `EMAIL_PROVIDER` 还是 `console`（链接在容器日志里）；或 SMTP 授权码/发件邮箱与 `SMTP_USERNAME` 不一致 |
| app 启动失败报 SECRET_KEY | 非 DEBUG 下密钥不得为开发默认值；确认 `appdata` 卷可写（entrypoint 会自动生成） |
| 首次构建慢 | 服务器拉取 python/node 基础镜像 + npm ci，属正常；后续 `--build` 走缓存 |
| 前端白屏但 API 正常 | 浏览器强刷缓存；或 `docker compose up -d --build app` 确保 `static/` 为最新构建 |