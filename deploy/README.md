# ynfight 生产部署

Docker 部署到服务器：**2 个容器**（`postgres` + `app`），`app` 容器内的 FastAPI 同时服务 API 与前端静态文件。

```
浏览器 ──► app:8102（uvicorn 单进程）
              ├── /api/*       业务接口（含 SSE 战斗流）
              └── /assets + /  前端静态文件 + SPA 回退（构建产物打进镜像）
                    └── 数据卷 appdata:/app/data（行迹 md、日志、SECRET_KEY）
              └── postgres:5432  数据库（卷 pgdata）
```

## 关键约束（改动前先读）

- **app 必须单副本、uvicorn 单进程**：SSE 战斗流是进程内 asyncio 总线（`app/services/battle_stream.py`），`recover_pending_battles` 也是进程内任务。多 worker / 多副本会导致订阅连到错误进程。**不要** `--scale app=2`，`Dockerfile` 里也没加 `--workers`。
- **无 nginx**：同源部署 + 无代理层，天然规避 SSE 被缓冲的坑（`app/core/middleware.py` 注明必须纯 ASGI 透传）。将来要 HTTPS 终止时，在 `8102` 前再叠一层 nginx/caddy 即可，后端代码不用动。
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
#    LLM_API_KEY         填入 DeepSeek Key
#    AUTH_COOKIE_SECURE  服务器无 HTTPS 必须 false；配好 HTTPS 后改 true

# 3. 再次部署生效
SERVER=user@server-ip ./deploy/deploy.sh
```

`SECRET_KEY` 不需要填：`entrypoint.sh` 首次启动自动生成并持久化到卷 `appdata` 的 `/app/data/secret_key`，重部署不覆盖（已签发 JWT 不失效）。

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
docker compose --env-file deploy/.env.production -f deploy/docker-compose.prod.yml restart app   # 重启（自动补推 pending 战斗）
```

## 备份 / 迁移

```bash
# 数据库
docker run --rm -v ynfight_pgdata:/pgdata -v "$PWD":/backup alpine \
  tar czf /backup/pgdata.tar.gz -C /pgdata .
# 应用数据（行迹 md、日志、SECRET_KEY）
docker run --rm -v ynfight_appdata:/appdata -v "$PWD":/backup alpine \
  tar czf /backup/appdata.tar.gz -C /appdata .
```

## 排障

| 现象 | 排查 |
|---|---|
| 登录后刷新即登出 | `AUTH_COOKIE_SECURE` 与服务器协议不匹配：无 HTTPS 必须 `false` |
| `/api/health` 返回 503 | postgres 未就绪；`docker compose logs postgres` 查看，或检查 `POSTGRES_PASSWORD` 是否已改但 `pgdata` 卷用了旧口令（重建卷：`docker compose down -v`，注意会清数据） |
| 首次构建慢 | 服务器拉取 python/node 基础镜像 + npm ci，属正常；后续 `--build` 走缓存 |
| 前端白屏但 API 正常 | 浏览器强刷缓存；或 `docker compose up -d --build app` 确保 `static/` 为最新构建 |
