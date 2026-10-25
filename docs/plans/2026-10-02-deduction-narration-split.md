# 推演/叙述解耦与全面重命名：三段独立任务 + 术语体系更替

- 状态：✅ 已完成（2026-10-02，pytest 66/66 + tsc 通过 + 提示词冻结逐字节比对零差异 + 迁移往返验证）
- 创建：2026-10-02
- 来源：grilling 会话定案（多轮提问全部收敛）；执行顺序上前置于本计划的还有 [2026-10-02-sse-view-resume.md](2026-10-02-sse-view-resume.md)（view_snapshot 断线续传，先落地，本计划落地时把其 view_* 命名一并迁移）

## 背景与设计意图

现状 `resolve_scenario_action`（flows.py:96-228）把推演（原"上帝视角"）、双方转写、胜负检定、结算落库编排在**一个后台任务**里。两个问题：

1. **单点失败浪费最贵资产**：推演是全链路唯一创造性 LLM 采样（不可复算、14s 级全文输出），转写/检定失败会连累整场 failed，重新挑战时推演重生成一遍。
2. **术语体系名实分离**："上帝视角/转写视角"是历史叫法，与目标心智模型（推演=事实生成，叙述=面向读者的转述）不符，且代码符号（god/view）与术语混着旧词。

定案方向：**推演、叙述、检定三段独立任务，段间只有数据依赖（经 DB 列/derived 传递），彻底根除"一根链"的编排内嵌**；同时全链路（代码/事件/文档/玩家文案）把术语更换为「推演」「叙述」。奇术比对与推演的关系（独立任务 scenario_prepare → derived.comparison_report → 推演读取）已是目标形态，零代码改动，仅文档统一表述。

## 定案决策（grilling 全程）

1. **三段独立**：`scenario_deduction`（推演）/ `scenario_narration`（叙述，双侧转写在同一任务内 gather）/ `scenario_judgement`（检定，独立任务）。检定输入只依赖推演全文（judge_kwargs 无转写内容，flows.py:155-162），与叙述互不依赖，并发派发。
2. **链式扇出**：推演任务落库后 dispatch 叙述 + 检定两任务。
3. **后到者结算**：叙述/检定各自完成后行锁 CAS 置 `derived` 完成标志（`narration_done`/`judgement_done`），后完成者在同一事务检测双齐 → 写 turn、定 won/lost、发 done。复用既有 FOR UPDATE 模式，无额外结算任务。
4. **落库载体**：新增 DB 列 `deduction_text`（TEXT、可空）——显式数据契约，一次 Alembic 迁移；终局后保留作审计（turn.omniscient 照旧写入，双存可接受）。
5. **status 零扩展**：resolving 贯穿到终局，阶段由 `deduction_text` 是否非空推断。前端 stageFromStatus、轮询条件、路由校验、recovery 的 status 分支全部零改动。
6. **失败语义**：任何一段失败即 status=failed 并发 SSE error，保留 deduction_text；不做链路级自动重试（调用级超时+2 次重试、recovery 续跑已两层兜底）。
7. **recovery**（recovery.py:22-36 改造）：resolving 且 `deduction_text` 为空（30 分钟阈值不变）→ 标 failed（推演未完成）；非空 → re-dispatch 叙述 + 检定（输入完备，无损续跑）。
8. **重命名边界**：SPEC id 改（traces/metrics 统计断代可接受）；SSE 事件名改（前后端同仓同版本，无存量问题）；持久化字段 `omniscient` **保留不动**（存量 messages JSON 兼容红线，代码符号/文案照换新）；提示词常量文本**逐字节不动**（冻结区），文件/函数/常量名可改，迁移后脚本比对验证。
9. **玩家文案全面替换**，显示词就叫「推演」。
10. **搁置备忘（长远计议）**：会话中还推演过更激进的「编排大于任务队列」形态——单一可重入编排协程（gather 直接写在编排代码里）+ 仅推演设 checkpoint + LLM 请求池化资源定位（NodeSpec=SQL、reliability=连接池、业务代码调 LLM 如调 DB）。本轮明确不做；待三段方案运行一段后复盘，若 join 协调成本显现再议。

## 术语映射表

| 层 | 旧 | 新 |
|---|---|---|
| 中文术语 | 上帝视角 | 推演 |
| 中文术语 | 转写视角（挑战者/守方视角转写） | 叙述（挑战者侧/守方侧） |
| 中文术语 | 胜负检定 | 检定（不变） |
| SPEC id | `scenario_god_reply` | `scenario_deduction` |
| SPEC id | `scenario_challenger_view` | `scenario_narration_challenger` |
| SPEC id | `scenario_guardian_view` | `scenario_narration_guardian` |
| SPEC id | `scenario_goal_judgement` | 不变（名实相符） |
| SSE 事件 | `god_progress` | `deduction_progress` |
| SSE 事件 | `view_chunk` | `narration_chunk` |
| SSE 事件 | `view_snapshot`（前置计划落地后） | `narration_snapshot` |
| 节点文件 | `nodes/scenario/god.py` | `deduction.py` |
| 节点文件 | `nodes/scenario/challenger_view.py` | `narration_challenger.py` |
| 节点文件 | `nodes/scenario/guardian_view.py` | `narration_guardian.py` |
| 常量/函数 | `GOD_TEMPLATE`/`build_scenario_god_llm` | `DEDUCTION_TEMPLATE`/`build_scenario_deduction_llm` |
| 常量/函数 | `CHALLENGER_VIEW_TEMPLATE`/`build_scenario_challenger_view(_stream)_llm` | `NARRATION_CHALLENGER_TEMPLATE`/`build_scenario_narration_challenger(_stream)_llm` |
| 常量/函数 | `GUARDIAN_VIEW_TEMPLATE`/`build_scenario_guardian_view(_stream)_llm` | `NARRATION_GUARDIAN_TEMPLATE`/`build_scenario_narration_guardian(_stream)_llm` |
| flows 函数 | `resolve_scenario_action` | `run_scenario_deduction` / `run_scenario_narration` / `run_scenario_judgement` |
| 注册表任务名 | `scenario_resolve` | `scenario_deduction` / `scenario_narration` / `scenario_judgement` |
| DB 列 | —（新增） | `deduction_text` |
| DB JSON 字段 | `omniscient` | **保留不动** |
| 前端符号 | `liveGod` | `liveDeduction` |
| operation 名 | `scenario_god_reply`/`scenario_challenger_view`/`scenario_guardian_view` | 随 SPEC id（`scenario_deduction`/`scenario_narration_challenger`/`scenario_narration_guardian`） |

### 玩家文案映射（前端用户可见处）

| 旧文案 | 新文案 | 位置 |
|---|---|---|
| 上帝视角 · 推演中 | 推演中 | ScenarioNarrative.tsx:81 |
| 上帝视角 · 看破已全 | 推演 · 看破已全 | ScenarioNarrative.tsx:52 |
| 上帝视角推演中 | 推演中 | scenarioModel.ts:17 |
| 待你看破这套阵容的全部奇术，上帝视角会在书页上开启。 | 待你看破这套阵容的全部奇术，推演全文会在书页上开启。 | ScenarioBattle.tsx:443 |
| 注释中「上帝遮挡/上帝门控/上帝全文」等 | 推演遮挡/推演门控/推演全文 | 各处注释（非玩家可见，一并换） |

## 改动明细

### 1. 迁移（migrations/versions/ 新文件）
- `scenario_challenge_runs` 加列 `deduction_text TEXT NULL`；down 为 drop column。

### 2. app/models/scenario_domain.py
- `ScenarioChallengeRun` 加 `deduction_text: Mapped[str | None]`。

### 3. app/services/nodes/scenario/（重命名，提示词文本逐字节不动）
- `god.py` → `deduction.py`：SPEC id→`scenario_deduction`，常量/函数按映射表改名；**GOD_TEMPLATE 的消息文本一字不改**（改名仅限变量名）。
- `challenger_view.py` → `narration_challenger.py`、`guardian_view.py` → `narration_guardian.py` 同理。
- `nodes/scenario/__init__.py` 与 `nodes/catalog.py` 的 NODES 键同步（`node_fingerprint` 只被比对节点消费，指纹无影响）。
- **验证脚本**：迁移前后提取三个 TEMPLATE 的消息文本做逐字节 diff（参照清理记录-06 的比对方法），任何差异即失败。

### 4. app/services/scenario/flows.py（核心重构）
- 删 `resolve_scenario_action`，新增：
  - `run_scenario_deduction(cid)`：CAS(status==resolving 且 deduction_text 为空) → 流式生成（事件名 `deduction_progress`，只发累计字数不变）→ 行锁落 `deduction_text` → `dispatch("scenario_narration", cid)` + `dispatch("scenario_judgement", cid)`。失败：failed + SSE error（保留已生成的 deduction_text 不可能——失败即未落库，天然保留空）。
  - `run_scenario_narration(cid)`：CAS(status==resolving 且 deduction_text 非空) → 读 deduction_text 与快照 → gather(双侧叙述流式，事件 `narration_chunk` 带 side) → 行锁 FOR UPDATE 落双方文本至 derived 临时区（或直接结算时取内存值，见下）+ 置 `derived.narration_done` → 检测 `judgement_done` 双齐则执行**结算**。
  - `run_scenario_judgement(cid)`：CAS 同上 → 读 deduction_text + 卷规则 → 结构化检定 → 行锁落 `derived.judgement_done={achieved, reason}` → 检测 `narration_done` 双齐则结算。
  - **结算函数 `_settle_if_ready(cid, narration_text_pair | None, judgement | None)`**：后到者调用；行锁重读双标志，双齐则一次事务写 turn（challenger_text/guardian_text/omniscient=deduction_text/achieved/reason）、won/lost、猜测点、首胜统计（迁移 flows.py:175-211 现有逻辑）→ 发 turn×2（visible_turn 门控不变）+ done。**叙述文本需要先落**：叙述任务在置 narration_done 前把双侧文本写入 `derived.narration_texts={challenger,guardian}`，结算时从 derived 取——保证后到者（检定先完成时）能读到叙述结果，不依赖进程内存。
  - 失败路径统一：except → failed + SSE error（叙述/检定失败时 deduction_text 已在库，保留审计）。
- `stream_scenario_view` 助手改名 `stream_narration`，事件/operation 随映射表。
- 比对链（prepare）**不动**。

### 5. app/services/scenario/tasks_registry.py
- `_TASK_ATTRS`：`scenario_deduction`→`run_scenario_deduction`、`scenario_narration`→`run_scenario_narration`、`scenario_judgement`→`run_scenario_judgement`；删 `scenario_resolve`；`scenario_prepare`/`guess_round`/`guess_verify` 不变。

### 6. app/services/scenario/recovery.py
- 现状：resolving 超 30 分钟批量置 failed。改为二分：`deduction_text` 为空 → 置 failed（现状行为）；非空 → 复位后 re-dispatch `scenario_narration` + `scenario_judgement`（CAS 保证幂等，任务重入安全——叙述/检定各自置标志前有行锁与状态检查）。

### 7. app/api/routes/scenario_domain.py
- `POST /actions`（:649-）：dispatch 名改 `scenario_deduction`；状态校验（resolving 才派）不变。
- detail 端点 derived 白名单（:563-566 owner 视角同）确认**不返回** `narration_done`/`judgement_done`/`narration_texts`/`deduction_text`——结算前推演全文不可出站（上帝门控语义不变）。
- SSE 端点零改动。

### 8. 前端 frontend/src/
- `ScenarioBattle.tsx`：事件分支 `god_progress`→`deduction_progress`、`view_chunk`→`narration_chunk`（+前置计划落地的 `view_snapshot`→`narration_snapshot`）；`liveGod`→`liveDeduction`；注释与 :443 文案按映射表。
- `ScenarioNarrative.tsx`：:49-82 omniscient 渲染分支文案与注释（字段名 omniscient 不动）；「上帝视角」标签按映射表。
- `scenarioModel.ts`：:17 stage 文案；类型字段 omniscient 不动。
- `ScenarioRecords.tsx`：注释术语。
- `sse.ts` 零改动（事件名透传）。

### 9. 测试
- `test_scenario_event_scope.py`：既有用例从「单任务产出全部事件」改为「推演任务产出 deduction_progress、叙述任务产出 narration_chunk×2、结算在双齐后发生」；新增：检定先完成叙述后完成的结算时序用例（验证后到者结算）；derived 白名单无泄露断言。
- `test_scenario_stream.py`：god_progress 透传用例改名（侧别过滤/广播用例本就事件名无关）。
- `test_scenario_domain.py` / `test_scenario_recovery.py`：recovery 二分行为（空→failed、非空→续跑派发）；actions 派发名。
- 新增提示词冻结验证：三个 TEMPLATE 文本与 git 基线逐字节比对（可作为独立测试或执行期脚本）。

### 10. 文档
- `docs/product-design.md`：推演/叙述术语、三段任务描述、deduction_text 列、数据依赖表述（比对→推演→叙述/检定）。
- `docs/current-model-api.md`：scenario_challenge_runs 表加 deduction_text；任务名与事件名；术语替换（含「上帝视角」全部改为「推演」，`Ability.understanding` 那段不涉及）。
- `AGENTS.md`：项目交接要点的术语基准（「上帝门控」→「推演门控」等）、任务注册表描述更新。
- `DESIGN.md`：若提及「上帝视角」组件文案则同步。
- `docs/plans/2026-10-02-sse-view-resume.md`：执行时若 view_* 已落地，按 narration_* 更新该计划的状态注记。

## 验证

1. 提示词冻结：三个节点 TEMPLATE 消息文本与重构前基线逐字节 diff = 零差异；
2. 全量 `uv run pytest tests/ -q`（重点 test_scenario_event_scope/stream/domain/recovery）；
3. `cd frontend && npm run build`（tsc）；
4. Alembic 迁移 upgrade/downgrade 各一次；
5. dev 手动验收：完整推演（事件名与文案更替后全链路正常）；推演中途 kill 后端重启 → deduction_text 非空的挑战自动续跑叙述/检定而非标失败；叙述先完成/检定先完成两种时序结算各验一次；断线重连 narration_snapshot 替换语义正常；结算前 detail/网络面板无推演明文出站。

## 关键代码事实（执行前复核）

- resolve 现状单任务全链：flows.py:96-228（god 流式 :134-145 → 三路 gather :163-172 → 结算落库 :175-211 → turn×2+done :216-221）；
- judge 输入无转写内容（flows.py:155-162 judge_kwargs），独立成立的事实依据；
- derived 白名单读取点：scenario_domain.py:563-566（挑战者视角）与 :603-606（owner 视角），仅 achieved/reason 出站；
- 行锁顺序纪律：先 challenge 后 progress（flows.py:233 注释），结算与标志写入沿用；
- recovery 现状：recovery.py:22-36（30 分钟阈值、多实例安全的说明见 :4-7 docstring）；
- 事件契约冻结区外：nodes/ 提示词是冻结的，flows/路由/前端的事件名不在冻结区；
- 前置计划：2026-10-02-sse-view-resume.md 若已执行，stream.py 将含 `_view_buffers`/`view_snapshot`，本计划统一迁 narration_snapshot 并更新其计划文档状态。
