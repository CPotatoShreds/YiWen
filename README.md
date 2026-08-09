# 异闻录 (ynfight)

LLM 驱动的奇术对战平台：异闻师自创奇术（想写什么就写什么）→ 装入奇人（角色）并解封 → 启程（随机摇签对家）→ LLM 铺陈一段江湖故事 → 败方可凭行迹线索猜对家奇术，猜中则逆转胜负。

- **后端**：FastAPI（Python 3.12，uv 管理依赖）
- **前端**：React
- **对战**：非实时联机，由后台摇签对家后调用 LLM 铺陈战局与胜负；奇术表在对战与猜奇术期间保密
- **奇人**：每位异闻师初始 3 个奇人槽位（每 50 见闻 +1、上限 8），奇术可入任意位（同一奇术可入多位）；每位一个 `enabled`（已解封）开关，已解封 = 可主动启程且进入匹配池（台下听客）

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

# 一键启动前后端（同一终端；后端 8102，前端 5174）
# 安全退出：输入 q 后回车 —— 同时关闭前后端，不残留进程
dev.bat

# 运行测试
uv run pytest

# 代码检查
uv run ruff check .

# 数据库迁移（首次启动/升级前执行）
uv run alembic upgrade head
```

SQLite 默认使用根目录的 `ynfight.db`；`ynfight.db-wal` 和 `ynfight.db-shm` 是同一数据库的运行时临时文件，不是额外数据库。不要手动删除正在运行实例的这两个文件。

- API 文档：http://localhost:8102/api/docs
