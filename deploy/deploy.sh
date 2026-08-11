#!/usr/bin/env bash
# ynfight 一键部署：同步代码 → 服务器构建并启动
#
# 用法：
#   SERVER=user@server-ip ./deploy/deploy.sh
#
# 前置（仅首次，见 deploy/README.md）：
#   1. 服务器安装 Docker + Docker Compose plugin
#   2. 首次同步后编辑服务器上的 ~/ynfight/deploy/.env.production（改 POSTGRES_PASSWORD / LLM_API_KEY 等）
set -euo pipefail

SERVER="${SERVER:?用法: SERVER=user@host ./deploy/deploy.sh}"

# 同步代码（tar-over-ssh，免 rsync 依赖，Windows Git Bash 可用）
# 排除：构建产物、数据卷、测试、环境变量（.env.production 只在服务器上编辑，防覆盖）
tar czf - \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='frontend/node_modules' \
  --exclude='frontend/dist' \
  --exclude='data' \
  --exclude='tests' \
  --exclude='.env' \
  --exclude='deploy/.env.production' \
  --exclude='*.tar' \
  -C "$(cd "$(dirname "$0")/.." && pwd)" . \
  | ssh "$SERVER" 'mkdir -p ~/ynfight && tar xzf - -C ~/ynfight'

# 首次部署：服务器上还没有 .env.production 时从模板复制（之后请自行编辑密匙）
ssh "$SERVER" 'cd ~/ynfight && if [ ! -f deploy/.env.production ]; then cp deploy/.env.production.example deploy/.env.production && echo "[deploy] 已生成 deploy/.env.production，请编辑其中的口令与 LLM Key 后再跑一次"; fi'

# 远端构建并启动（app 保持单副本，勿 --scale）
ssh "$SERVER" 'cd ~/ynfight && docker compose --env-file deploy/.env.production -f deploy/docker-compose.prod.yml up -d --build'

echo "[deploy] 完成。站点 http://$SERVER:8102 （health: http://$SERVER:8102/api/health）"
