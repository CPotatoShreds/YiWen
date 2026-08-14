# ── Stage 1: Frontend build ──────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
# output → /src/frontend/dist

# ── Stage 2: Backend runtime ──────────────────────────────────────────────
FROM python:3.12-slim AS backend
WORKDIR /app

# Python deps（asyncpg/psycopg[binary]/bcrypt 均有 manylinux 轮子，无需编译工具）
COPY pyproject.toml README.md ./
# 轮子缓存挂载在 buildkit builder 缓存（不占镜像）：版本号/依赖变更触发本层重跑时不再从 PyPI 重下载。
# 直连 files.pythonhosted.org 在腾讯云等国内服务器常读超时，默认走腾讯云镜像，可 --build-arg PIP_INDEX_URL 覆盖。
ARG PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple
RUN --mount=type=cache,target=/root/.cache/pip pip install -e . -i "${PIP_INDEX_URL}"

# Source
COPY app/ ./app/
COPY alembic.ini ./
COPY migrations/ ./migrations/
COPY scripts/ ./scripts/
COPY entrypoint.sh ./
RUN chmod +x entrypoint.sh

# Frontend build output from stage 1
COPY --from=frontend-builder /src/frontend/dist ./static/

# Persistent state（SECRET_KEY、行迹 md、日志，挂卷 /app/data）
RUN mkdir -p /app/data

# Runtime（SSE 为进程内总线，必须单 worker，勿加 --workers）
EXPOSE 8102
ENV HOST=0.0.0.0
ENV PORT=8102

ENTRYPOINT ["./entrypoint.sh"]
