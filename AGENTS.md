# AGENTS.md
Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

Tradeoff: These guidelines bias toward caution over speed. For trivial tasks, use judgment.

Think Before Coding
Don't assume. Don't hide confusion. Surface tradeoffs.
Before implementing:

•State your assumptions explicitly. If uncertain, ask.
•If multiple interpretations exist, present them - don't pick silently.
•If a simpler approach exists, say so. Push back when warranted.
•If something is unclear, stop. Name what's confusing. Ask.

Simplicity First
Minimum code that solves the problem. Nothing speculative.
•No features beyond what was asked.
•No abstractions for single-use code.
•No "flexibility" or "configurability" that wasn't requested.
•No error handling for impossible scenarios.
•If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

Surgical Changes
Touch only what you must. Clean up only your own mess.
When editing existing code:

•Don't "improve" adjacent code, comments, or formatting.
•Don't refactor things that aren't broken.
•Match existing style, even if you'd do it differently.
•If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:

•Remove imports/variables/functions that YOUR changes made unused.
•Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

Goal-Driven Execution
Define success criteria. Loop until verified.
Transform tasks into verifiable goals:

•"Add validation" → "Write tests for invalid inputs, then make them pass"
•"Fix the bug" → "Write a test that reproduces it, then make it pass"
•"Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:

[Step] → verify: [check]
[Step] → verify: [check]
[Step] → verify: [check]
Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.
These guidelines are working if: fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## 项目交接要点（已核验）

### 项目定位与技术栈

- `ynfight` 是“异闻录”AI 奇术对战平台：异闻师创建奇术，装入奇人并解封，启程后由 LLM 推演行迹；败方可以依据行迹线索猜对家实际使用的奇术，全部看破后可逆转胜负。
- 后端是 Python 3.12 + FastAPI + async SQLAlchemy 2.x + Pydantic v2 + Alembic，由 `uv` 管理依赖，代码主要在 `app/api/`、`app/models/`、`app/schemas/`、`app/services/`。
- 前端是 `frontend/` 下的 React + TypeScript + Vite，使用纯 CSS（`frontend/src/index.css`），依赖由 npm 和 `frontend/package-lock.json` 管理。
- 开发数据库默认是 Docker PostgreSQL；测试使用独立测试库。数据库结构变更必须通过 `migrations/versions/` 的 Alembic 迁移完成。

### 启动与验证

- 正常启动顺序由根目录 `dev.bat` 负责：`docker compose up -d` → `uvicorn` 后端 `8102` → Vite 前端 `5174`。API 文档为 `http://localhost:8102/api/docs`，前端为 `http://localhost:5174`。
- 启动前必须确认 Docker Desktop、`.venv` 和前端 npm 依赖可用；端口被占用时先确认旧进程归属，不要盲目杀进程。
- 前端依赖只能使用 npm：安装或恢复依赖使用 `cd frontend; npm ci`（严格按 `package-lock.json`），不要对这个项目运行 pnpm。不同包管理器混用会把现有依赖移到 `frontend/node_modules/.ignored`，导致 Vite 无法启动。
- 后端依赖使用 `uv sync`；执行 `uv sync` 或 `uv sync --reinstall` 前先停止正在运行的 Python 服务，避免 Windows 文件锁导致虚拟环境损坏。
- 小改动只运行相关 pytest 子集和必要的 lint/build；不要默认跑全量回归。报告验证时必须明确写出实际运行的命令和范围。

### 后端边界与关键链路

- `app/services/battle/deduction.py` 是推演编排入口（`run_deduction`）；`app/services/battle/lifecycle.py` 负责对战生命周期、结算、猜词状态和行迹落库。
- `app/services/guess/pipeline.py` 是真实对战和试验场共用的猜词管道：逐门点评与主动检定分开，点评结果按轮次和奇术卡片编号保存。
- `app/services/admin/test_battle.py` 是管理员试验场的隔离实现，只写 `test_*` 表，不应污染真实玩家的 `battles` / `battle_guesses` 数据。
- `app/services/llm/reliability.py` 统一处理 LLM 调用的超时、重试、退避、流式可靠性和 trace；新增 LLM 调用应沿用这层能力。
- `app/services/nodes/ability/pair_judge.py`、`nodes/battle/deducer.py`、`nodes/battle/discusser.py`、`nodes/battle/transcriber.py`、`nodes/guess/` 下的猜词节点、`nodes/battle/usage_judge.py` 等节点各自承担明确环节；修改跨节点行为前先确认数据契约和调用顺序。
- `battles.status='pending'` 是当前断点续推模型，独立的 `battle_pending` 表已不存在；不要依据旧记忆新增该表。
- LLM 配置默认来自 `.env` 的 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`，管理员 LLM profile 可覆盖默认配置。不要把密钥写入代码、测试或提交。

### 不可随意修改的内容

- `app/services/nodes/`、`app/services/battle/deduction.py`、`app/services/battle/lifecycle.py`、`app/services/ability/understanding.py` 中的推演、判定、转写、猜词和三相奇术理论提示词是用户手调内容，默认冻结；任何提示词文字、示例、约束或措辞调整必须先征得用户同意。
- 前端遵循古镇纸墨风：宣纸暖白、暖炭墨、朱砂主色，命中态克制使用墨绿；禁止 emoji、紫蓝渐变和 Tailwind/Framer Motion，图标使用 `frontend/src/components/icons.tsx`。
- 后端字段名和 API 路径保持英文稳定；用户可见术语遵循说书语系（奇术、奇人、异闻师、启程、行迹、故人、名望、见闻、摇签、看破等）。
- 不要为了“整理”删除历史字段或旧数据兼容逻辑。交接文档已记录过的删列/响应瘦身提议不代表可以执行，先核对模型、迁移和测试的实际使用情况。

### 协作与工作区

- 本仓库经常存在用户已有的暂存、未提交和未跟踪文件；开始任务先查看 `git status`，只修改与当前请求直接相关的文件，不重置、覆盖或清理用户改动。
- 修改前先确认真实入口、API 返回结构和当前测试；不要根据旧交接内容或文件名猜测架构。
- 除非用户明确同意，不执行 `git commit`、`git push`、`git reset`、大范围删除或会覆盖工作区的依赖重装。
- 详细产品设计、历史改动影响和阶段性问题见 `docs/product-design.md`、`docs/后端改动影响.md`、`docs/交接文档.md`；这些文档中的日期、提交基线和工作区状态是动态信息，使用前要重新核验。
