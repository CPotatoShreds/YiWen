#!/usr/bin/env bash
# 从 pg_dump -Fc 备份恢复数据库。
#
# 用法：
#   ./scripts/restore_db.sh <备份文件.dump> [目标数据库]
#   目标库不存在时自动创建。恢复演练：恢复到 ynfight_restore 临时库并抽查行数。
set -euo pipefail

BACKUP_FILE="${1:?用法: restore_db.sh <备份文件.dump> [目标数据库]}"
DATABASE="${2:-ynfight}"
CONTAINER="${PG_CONTAINER:-ynfight-postgres}"
PGUSER="${PG_USER:-ynfight}"

[ -f "$BACKUP_FILE" ] || { echo "备份文件不存在：$BACKUP_FILE"; exit 1; }

# 库不存在则建（经 postgres 管理库）
docker exec "$CONTAINER" psql -U "$PGUSER" -d postgres -tAc \
  "SELECT 1 FROM pg_database WHERE datname='$DATABASE'" | grep -q 1 || \
  docker exec "$CONTAINER" psql -U "$PGUSER" -d postgres -c "CREATE DATABASE \"$DATABASE\""

docker exec -i "$CONTAINER" pg_restore -U "$PGUSER" -d "$DATABASE" --no-owner --role="$PGUSER" < "$BACKUP_FILE"
echo "$(date '+%F %T') 恢复完成：$BACKUP_FILE → $DATABASE"
