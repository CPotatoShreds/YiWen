#!/usr/bin/env bash
# ynfight 一键部署（git 拉取式）：服务器 pull 最新代码 → 构建启动
#
# 用法：
#   SERVER=user@server-ip ./deploy/deploy.sh
#
# 前置（仅首次，见 deploy/README.md）：
#   1. 服务器安装 Docker + Docker Compose plugin，并配置 git 拉取凭据（deploy key / PAT）
#   2. 首次运行自动从本地 origin 克隆到 ~/ynfight；若该目录是旧 tar 部署残留会整体备份并迁移 .env.production
#   3. 首次部署后编辑服务器上的 ~/ynfight/deploy/.env.production（改 POSTGRES_PASSWORD / LLM_API_KEY 等）
set -euo pipefail

SERVER="${SERVER:?用法: SERVER=user@host ./deploy/deploy.sh}"

# 远端仓库地址（首次自动克隆用）：取本地 origin
REMOTE_URL="$(git remote get-url origin)"

ssh "$SERVER" '
set -euo pipefail

# 首次部署：~/ynfight 不是 git 仓库时克隆
if [ ! -d ~/ynfight/.git ]; then
  if [ -e ~/ynfight ] && [ -n "$(ls -A ~/ynfight 2>/dev/null)" ]; then
    # 旧 tar 部署残留：整体备份，clone 新代码，再把服务器密钥迁回
    echo "[deploy] 检测到旧部署残留，备份为 ~/ynfight.tar-backup 后克隆新代码"
    mv ~/ynfight ~/ynfight.tar-backup
    git clone -q '"$REMOTE_URL"' ~/ynfight
    if [ -f ~/ynfight.tar-backup/deploy/.env.production ]; then
      mv ~/ynfight.tar-backup/deploy/.env.production ~/ynfight/deploy/
      echo "[deploy] 已迁移 .env.production（旧目录保留在 ~/ynfight.tar-backup）"
    fi
  else
    git clone -q '"$REMOTE_URL"' ~/ynfight
  fi
fi

cd ~/ynfight
git pull -q

# 首次部署：服务器上还没有 .env.production 时从模板复制（之后请自行编辑密匙）
if [ ! -f deploy/.env.production ]; then
  cp deploy/.env.production.example deploy/.env.production
  echo "[deploy] 已生成 deploy/.env.production，请编辑其中的口令与 LLM Key 后再跑一次"
fi

# 远端构建并启动（app 保持单副本，勿 --scale）
docker compose --env-file deploy/.env.production -f deploy/docker-compose.prod.yml up -d --build
'

echo "[deploy] 完成。站点 http://$SERVER:8102 （health: http://$SERVER:8102/api/health）"
