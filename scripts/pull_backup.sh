#!/usr/bin/env bash
# 定时导出：把服务器上最新的数据库备份拉回本机（异地副本的最简形式，无需对象存储）。
#
# 在【本机】运行（不是服务器上）：
#   SERVER=user@server-ip ./scripts/pull_backup.sh [本地目录]
#   环境变量：SERVER（必填）、REMOTE_DIR（默认 ~/ynfight/backups）、LOCAL_KEEP（默认 30，本地保留份数）
#
# 定时：Windows 任务计划程序每日调用一次（示例见 docs/数据库备份与恢复.md）。
set -euo pipefail

SERVER="${SERVER:?用法: SERVER=user@host ./scripts/pull_backup.sh [本地目录]}"
LOCAL_DIR="${1:-backups}"
REMOTE_DIR="${REMOTE_DIR:-~/ynfight/backups}"
LOCAL_KEEP="${LOCAL_KEEP:-30}"

mkdir -p "$LOCAL_DIR"
LATEST="$(ssh "$SERVER" "ls -t $REMOTE_DIR/*.dump 2>/dev/null | head -1")"
[ -n "$LATEST" ] || { echo "服务器上还没有备份文件（$REMOTE_DIR）"; exit 1; }

FILE="$(basename "$LATEST")"
if [ -f "$LOCAL_DIR/$FILE" ]; then
  echo "$(date '+%F %T') 本地已存在，跳过：$FILE"
else
  scp -q "$SERVER:$LATEST" "$LOCAL_DIR/$FILE"
  echo "$(date '+%F %T') 已拉取：$FILE → $LOCAL_DIR（$(du -h "$LOCAL_DIR/$FILE" | cut -f1)）"
fi

# 本地滚动清理：只保留最近 LOCAL_KEEP 份
ls -t "$LOCAL_DIR"/*.dump 2>/dev/null | tail -n +$((LOCAL_KEEP + 1)) | while read -r old; do
  rm -f "$old" && echo "$(date '+%F %T') 清理旧备份：$(basename "$old")"
done