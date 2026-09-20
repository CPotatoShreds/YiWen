# SSE 职责收缩：上帝遮挡流 + stage 退场 + 侧别过滤

- 状态：✅ 已完成（2026-09-15）
- 创建：2026-09-13
- 定案方式：grilling 四问，全部按推荐定案

## 执行记录（2026-09-15）
- **stream.py**：`_subscribers` 改 `dict[Queue, str|None]`（队列→侧别），`subscribe(side=...)`；`_fanout` 按侧过滤（带 side 事件只投同侧，无 side 事件全员广播）；回放机制全套移除（`_replay_key`/`_replay_snapshot`/`_STATUS_STAGES`/XADD/XRANGE/TTL），快照退化为本地 `_emitted`（仅 done/error 终局事件）；gauge/relay/降级/终态清理保留。
- **scenario_domain.py**：god 改 `astream_with_reliability` 逐块流式，**只发 `god_progress{chars}`**、真实文本不出站；`stage` 全部退场（compare/ready/thinking/views/result），保留 done/error；turn 按侧拆分（挑战者收完整回合含 omniscient，守方收 `{role:"guardian", text, created_at}` 与详情同构）；SSE 端点按角色传侧别（challenger/guardian）。
- **前端**：`ScenarioBattle` 删 stage/god 分支，新增 god_progress（liveGod 追加"❖"遮挡符 + 推进 thinking）、view_chunk 推进 views；新增状态轮询（preparing/resolving 期每 2s 刷新详情 → `stageFromStatus` 推导阶段、终态自动停）；`stageFromStatus` 抽为初载/轮询共用。`scenarioModel.viewText` 的 guardian 分支补 `role==="guardian" → text` 回退（与 challenger 分支对称）——修复了守方消息形状在 guardian 视角下渲染为空的历史缺口（本计划 "与详情同构" 的 turn 依赖此回退可渲染）。
- **测试**：`test_scenario_stream` 重构（删回放/合成快照用例，新增侧别过滤、无 side 广播、快照用例）；新增 `test_scenario_event_scope`（不经过 HTTP 缓冲层，直接驱动真实后台任务与端点生成器：god 遮挡契约、无上帝明文出站、vchunk 侧别、turn 双形状、端点侧别传递、无关用户 404）。**顺带修复**：`tasks_registry` 的导入期快照使既有测试对 `_prepare/_resolve` 的桩失效（P2.4 引入），改为调用时 `getattr` 取模块属性，桩恢复生效。
- **验证**：pytest 62/62；ruff 全绿；mypy（app/core）0 错误；tsc 通过。
- 未走 HTTP 层验证的说明：SSE 需要真实流式传输，TestClient 会缓冲整包（实测挂起），故验收改为直接驱动后台任务 + 端点生成器，事件契约与侧别判定等价覆盖；浏览器端手动验收项（遮挡符增长、网络面板无明文）建议部署前在 dev 跑一次真实 LLM 推演确认。

## 背景与设计意图（用户原话归纳）
本项目 SSE 只有一个目的：在满足条件的 LLM 节点输出时使用，缩短用户等待时间。条件：①文本有一定长度；②用户可以看；③延迟敏感。逐项审计结论：
- 比对阶段：并发执行实际等待不长，且用户不能看内容 → 不需要流式（维持现状）；
- 猜词链路轮询：正确的既有技术决策 → 维持；
- 上帝视角 + 双方视角转写：为可视化进度与缩短 TTFT 而生。上帝视角对玩家等同"晦涩符号"，流式期间相当于另类进度条（文字换成遮挡物），**真实文本不送前端**；转写保持现有 SSE 推送；
- 阶段标记唯一作用是显示链路进度，改由节点流转状态驱动（轮询或前端自证），**不走 SSE**。

## 定案决策（四问）
1. 上帝遮挡形态：后端只发累计字数（{"chars": N}），前端按字数合成遮挡符号——零文本泄露、真实进度、前端控样式；
2. stage 移除后的进度驱动：混合——粗状态轮询详情（比对期 preparing→active 触发自动提策略；提策略后 resolving→终态），细阶段由事件到达自证（god 遮挡帧=thinking，转写 chunk=views）；轮询只在无事件窗口激活；
3. done/error 保留在 SSE 上（流生命周期控制：终局停重连、异常带文案），不属于进度标记；
4. 顺带修传输层侧别泄露：订阅按角色过滤（挑战者连接只收挑战者流，守方连接只收守方流）。现状泄露：守方直播时收到挑战者视角实时正文（UI tab 藏了但数据进浏览器，事后详情却对守方隐藏该正文）。

## 推论（随决策产生的清理）
stage 事件退场后，回放流（原为 stage 重连补发而生）失去服务对象 → 一并移除：终态由端点查库短路、阶段由轮询驱动，回放无服务对象。bus 核心保留：pub/sub 跨实例中转 + Redis 故障降级 + 终态清理。
假设（不改动）：回合结束后挑战者在详情接口仍可见 god 全文与守方正文（现状产品行为，仅直播期间遮挡）。

## 改动明细

### 1. app/services/scenario/stream.py
- `_subscribers: set[Queue]` → `dict[Queue, str | None]`（订阅者→侧别）；`subscribe(side=None)`；
- `_fanout` 按 side 过滤：事件带 side 且与订阅者不符则跳过；无 side 事件（done/error/god_progress/turn 拆分后的各侧版本）按规则广播；
- 移除回放机制全套：_replay_key / _replay_snapshot / _STATUS_STAGES / subscribe 的 db_status 参数 / XADD+EXPIRE+XRANGE 与 Redis 回放流；subscribe 快照退化为本地 _emitted（done/error 等无侧别事件）；
- god_progress 无需专门支持（无 side 自然广播）。

### 2. app/api/routes/scenario_domain.py
- god 改流式：ainvoke_with_reliability → astream_with_reliability(build_collection_god_llm(), ...)，逐 chunk 累加并 publish({"type": "god_progress", "chars": 累计长度}, replay=False)；拼接结果作为 god 全文（落库/turn 用，不出站）；
- 删除全部 stage 发布：_prepare 的 compare/ready、_resolve 的 thinking/views、result；保留 done 与 error；
- turn 事件按侧别拆分：挑战者侧发完整 turn（含 omniscient，同详情现状）；守方侧发 {"role": "guardian", "text": guardian_view, "created_at": ...}（与详情守方消息同构）；
- SSE 端点：判定订阅侧别（challenger_id == current.id → "challenger"，否则 "guardian"）传入 subscribe(side=...)；db_status 参数删除。

### 3. 前端 frontend/src/pages/ScenarioBattle.tsx
- onEvent：删除 stage 分支；新增 god_progress（liveGod 追加遮挡符号"❖"，并 setStage("thinking")）；view_chunk 分支追加 setStage("views")；done/error/turn 行为不变（turn 已按侧别收到对应形状）；
- 新增状态轮询（复用猜词轮询的 signature + setTimeout 模式）：challenge.status ∈ {preparing, resolving} 时每 2s GET 详情 → setChallenge(data) + 走既有"status 推导 stage"逻辑（253-261 行）；终态自动停；比对期推导出 ready 触发现有自动提策略 effect；
- stage 从"SSE 驱动"变为"轮询推导 + 事件到达推进"，既有 UI 消费点（进度条/按钮/pending/结果面板）零改动。

### 4. 测试
- tests/test_scenario_stream.py：删除回放/合成快照用例；新增侧别过滤用例（挑战者订阅收不到 guardian chunk、无 side 事件广播）、god_progress 透传用例；调整 view_chunk 用例；
- tests/test_scenario_domain.py：如有对 stage 事件的断言改为状态断言（实现时跑了看）。

### 5. 回归与验收
全量 pytest + ruff + mypy + tsc；手动验收：比对期无 SSE 但页面经轮询自动进入可提策略态；推演期间 god tab 呈遮挡符号增长且网络面板无任何 god 明文出站；守方直播网络面板无挑战者正文；终局面板与归档页行为不变。

## 关键代码事实（执行前复核）
- 前端 SSE 唯一消费方：ScenarioBattle.tsx:271-338（onEvent :284-328；stage 驱动进度条 :518-531、按钮 :575-635、结果面板 :697-722）；ScenarioChallenge.tsx 不消费 SSE；
- 既有可复用轮询：猜词 500ms 轮询（:340-373），api.ts:39 对 /scenario-challenges/ 前缀免缓存；
- god 节点：nodes/collection/god.py，纯文本输出无 schema（SPEC 无 schema，max_tokens=8192），可直接 astream；
- 重连：固定 1.5s retry + sse.ts 15s 连接超时；detail 初始化已有 status→stage 推导（ScenarioBattle:253-261）。

## 明确不做
比对阶段流式/进度事件；猜词流式（维持轮询）；god 事后可见性变更（详情现状保留）；Last-Event-ID 续传；引入 BaseHTTPMiddleware。
