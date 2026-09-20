#!/usr/bin/env bash
# Postgres 定时备份：pg_dump -Fc 自定义格式，按天滚动保留。
#
# 用法：
#   ./scripts/backup_db.sh [备份目录]
#   环境变量：PG_CONTAINER（默认 ynfight-postgres）、PG_DATABASE（默认 ynfight）、
#             PG_USER（默认 ynfight）、PG_KEEP_DAYS（默认 7）
#
# cron 示例（宿主机每天 03:30）：
#   30 3 * * * /path/to/ynfight/scripts/backup_db.sh /var/backups/ynfight >> /var/log/ynfight_backup.log 2>&1
set -euo pipefail

BACKUP_DIR="${1:-backups}"
CONTAINER="${PG_CONTAINER:-ynfight-postgres}"
DATABASE="${PG_DATABASE:-ynfight}"
PGUSER="${PG_USER:-ynfight}"
KEEP_DAYS="${PG_KEEP_DAYS:-7}"

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
TARGET="$BACKUP_DIR/${DATABASE}_${STAMP}.dump"

docker exec "$CONTAINER" pg_dump -U "$PGUSER" -Fc "$DATABASE" > "$TARGET"
SIZE="$(du -h "$TARGET" | cut -f1)"
echo "$(date '+%F %T') 备份完成：$TARGET（$SIZE）"

# 滚动清理：只删本脚本命名规则的旧备份
find "$BACKUP_DIR" -name "${DATABASE}_*.dump" -type f -mtime +"$KEEP_DAYS" -delete
echo "$(date '+%F %T') 已清理 ${KEEP_DAYS} 天前的旧备份"
