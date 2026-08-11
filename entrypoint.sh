#!/bin/sh
set -e

# ── 1. SECRET_KEY ────────────────────────────────────────────────────────
# 首次启动生成并持久化到数据卷；重部署不覆盖，避免已签发 JWT 失效
KEY_FILE=/app/data/secret_key
if [ ! -f "$KEY_FILE" ]; then
    echo "[entrypoint] Generating new SECRET_KEY…"
    mkdir -p /app/data
    python -c "import secrets; print(secrets.token_hex(32))" > "$KEY_FILE"
fi
export SECRET_KEY=$(cat "$KEY_FILE")
echo "[entrypoint] SECRET_KEY loaded"

# ── 2. Database migration ────────────────────────────────────────────────
echo "[entrypoint] Running database migrations…"
alembic upgrade head
echo "[entrypoint] Migrations complete"

# ── 3. Start app（单进程：SSE 为进程内 asyncio 总线，勿加 --workers）─────────
echo "[entrypoint] Starting uvicorn on ${HOST:-0.0.0.0}:${PORT:-8102}"
exec uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8102}"
