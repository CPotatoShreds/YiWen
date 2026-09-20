# 异闻录 (ynfight)

LLM 驱动的小天下集平台：异闻师创作奇术与情景，发布后由挑战者进入小天下集，LLM 推演行迹并通过猜词管道推进挑战。

- **后端**：FastAPI（Python 3.12，uv 管理依赖）
- **前端**：React
- **现役玩法**：小天下集。传统对战、名望、见闻、好友和通知等历史玩法已下线。
- **用户资产**：用户直接拥有奇人和奇术；奇人可按顺序绑定最多 4 门自有奇术，所有字段均可随时修改，无发布或版本控制。

## 项目结构

```
ynfight/
├── app/
│   ├── api/          # API 路由
│   ├── core/         # 配置、安全
│   ├── db/           # 数据库引擎与会话
│   ├── models/       # ORM 模型（用户、奇术、奇人、行迹…）
│   ├── schemas/      # Pydantic 校验模型
│   └── services/     # 业务逻辑（奇术管理、奇人抽选、摇签、LLM 铺陈与猜奇术…）
├── tests/            # pytest 测试
├── frontend/         # React 前端（古镇纸墨风格）
├── pyproject.toml    # uv 项目配置与依赖
└── .python-version   # Python 3.12
```

## 开发

```bash
# 安装依赖
uv sync
cd frontend && npm install

# 启动数据库（Docker PostgreSQL，见 docker-compose.yml；首次会拉镜像）
docker compose up -d

# 一键启动前后端（同一终端；后端 8102，前端 5174）
# 安全退出：输入 q 后回车 —— 同时关闭前后端，不残留进程
dev.bat

# 运行测试（自动重建独立测试库 ynfight_test）
uv run pytest

# 代码检查
uv run ruff check .

# 数据库迁移（首次启动/升级前执行）
uv run alembic upgrade head
```

数据库为本地 Docker PostgreSQL（`postgres:16-alpine`，用户/库均为 `ynfight`，端口 5432），连接串在 `.env` 的 `DATABASE_URL`（默认 `postgresql+asyncpg://ynfight:ynfight@localhost:5432/ynfight`）。测试会重建独立的 `ynfight_test` 库，不碰开发数据。

> 备选：如需单文件 SQLite 本地调试，把 `.env` 的 `DATABASE_URL` 改为 `sqlite+aiosqlite:///./ynfight.db` 即可。

- API 文档：http://localhost:8102/api/docs
