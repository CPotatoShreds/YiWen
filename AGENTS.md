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

## 项目交接要点（已核验，2026-09-18 随结构重构更新）

### 项目定位与技术栈

- `ynfight` 是“异闻录”AI 奇术对战平台（现役玩法为「小天下集」）：异闻师创建奇术、装配奇人，向公开阵容发起挑战；LLM 依据双方奇术与策略一次性推演对决并检定胜利条件，挑战者可依据推演与逐轮点评猜守方实际奇术，全部看破后解锁上帝视角。
- 后端是 Python 3.12 + FastAPI + async SQLAlchemy 2.x + Pydantic v2 + Alembic，由 `uv` 管理依赖，代码主要在 `app/api/`、`app/models/`、`app/schemas/`、`app/services/`。
- 前端是 `frontend/` 下的 React + TypeScript + Vite，使用纯 CSS（`frontend/src/index.css`），依赖由 npm 和 `frontend/package-lock.json` 管理。
- 开发数据库默认是 Docker PostgreSQL；测试使用独立测试库。数据库结构变更必须通过 `migrations/versions/` 的 Alembic 迁移完成。

### 启动与验证

- 正常启动顺序由根目录 `dev.bat` 负责：`docker compose up -d` → `uvicorn` 后端 `8102` → Vite 前端 `5174`。API 文档为 `http://localhost:8102/api/docs`，前端为 `http://localhost:5174`。
- 启动前必须确认 Docker Desktop、`.venv` 和前端 npm 依赖可用；端口被占用时先确认旧进程归属，不要盲目杀进程。
- 前端依赖只能使用 npm：安装或恢复依赖使用 `cd frontend; npm ci`（严格按 `package-lock.json`），不要对这个项目运行 pnpm。
- 后端依赖使用 `uv sync`；执行前先停止正在运行的 Python 服务，避免 Windows 文件锁导致虚拟环境损坏。
- 小改动只运行相关 pytest 子集和必要的 lint/build；大范围结构重构后跑全量 `uv run pytest tests/ -q`。报告验证时必须明确写出实际运行的命令和范围。

### 后端分层规矩（2026-09-18 确立）

- **同名成对**：`app/services/nodes/<域>/` = 该域的 LLM 节点声明（NodeSpec/提示词/schema/`build_*`）；`app/services/<域>/` = 该域的服务（编排/缓存/运行时）。现役三对：`ability`（比对缓存/槽位编排）、`guess`（猜词管道）、`scenario`（挑战流程）。
- **编排属 services，路由只做 HTTP 壳**：后台编排协程在 `app/services/scenario/flows.py`；对外脱敏纯函数在 `app/services/scenario/views.py`；`api/routes/scenario_domain.py` 只做参数校验与响应组装。依赖方向永远是 api → services，绝不反向。
- **单件根级、多件成包**：横切单文件工具放 services 根（如 `mail.py`）；内容多文件才立包（如 `llm/`）。域不再使用单文件包。
- **已删除域不要复活**：battle、loadout、board、collection（旧收藏集对战）、friend、leaderboard、notification、anecdote、prompt_debug、管理员试验场（test_battle/test_* 表）均已移除；遇到旧文档或 `__pycache__` 提及它们，以代码现状为准。
- 后台任务：业务代码 `dispatch("任务名", ...)` 派发，inline 与 arq 双模式共用 `services/scenario/tasks_registry.py` 注册表；新增后台任务在 `flows.py` 实现协程并在注册表登记。
- `app/services/guess/pipeline.py` 是猜词管道：切分（纯正则）→ 原子×奇术并发配对 → 玩家主动检定三环节，回调式逐结果落库。
- `app/services/llm/reliability.py` 统一收口所有 LLM 调用（硬超时、退避重试、并发闸、llm_traces 追踪）；新增 LLM 调用必须沿用这层。
- LLM 配置默认来自 `.env` 的 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`（OpenAI 兼容协议，不区分 provider）；用户自配方案（llm_profiles，api_key 经 Fernet 加密落库）可覆盖默认。不要把密钥写入代码、测试或提交。

### 不可随意修改的内容

- `app/services/nodes/`（含 `nodes/ability/understanding.py`）中的推演、判定、转写、猜词与三相奇术理论提示词是用户手调内容，默认冻结；任何提示词文字、示例、约束或措辞调整必须先征得用户同意。移动文件、修正 docstring 中的模块指引不受此限，但提示词常量必须逐字节保持（迁移后用脚本比对验证）。
- 前端遵循古镇纸墨风：宣纸暖白、暖炭墨、朱砂主色，命中态克制使用墨绿；禁止 emoji、紫蓝渐变和 Tailwind/Framer Motion，图标使用 `frontend/src/components/icons.tsx`。
- 后端字段名和 API 路径保持英文稳定；用户可见术语遵循说书语系（奇术、奇人、异闻师、卷、阵容、挑战、看破、道出猜测等），以现行前端文案为准。
- 不要为了“整理”删除历史字段或旧数据兼容逻辑（如存量 JSON 的“半对”判定、`snippet` 字段回退）。删列/删表类改动必须先核对模型、迁移和数据实况，并征得用户同意。

### 协作与工作区

- 本仓库经常存在用户已有的暂存、未提交和未跟踪文件；开始任务先查看 `git status`，只修改与当前请求直接相关的文件，不重置、覆盖或清理用户改动。
- 修改前先确认真实入口、API 返回结构和当前测试；不要根据旧交接内容或文件名猜测架构。
- 除非用户明确同意，不执行 `git commit`、`git push`、`git reset`、大范围删除或会覆盖工作区的依赖重装。
- 现役文档：产品设计见 `docs/product-design.md`（小天下集现役版）、数据模型与接口见 `docs/current-model-api.md`、数据库运维见 `docs/数据库备份与恢复.md`、历史计划见 `docs/plans/`（带日期档案）、各站清理过程见 `docs/清理记录-*.md`。文档中的日期与验证状态是时点信息，使用前重新核验。
