# SSE 事件总线外置 + 猜词轮次锁 DB 化

- 状态：✅ 已完成（2026-09-12）
- 创建：2026-09-12
- 定案方式：grilling 七问，全部按推荐定案

## 执行记录（2026-09-12）
- 全部改动按计划落地：stream.py 重写（全局频道 + per-challenge 回放流 + relay + 降级 + 终态清理）、main.py lifespan 接线、scenario_domain.py 行锁替换、tests/test_scenario_stream.py（6 用例）、scripts/dual_instance_check.py。
- 验证：test_scenario_stream.py 6/6；test_scenario_domain.py + test_scenario_guess_assistance.py 回归通过；全量 56/56；双实例实测（8102/8103）脚本 PASS——实例 B 经回放流收到实例 A 的 stage 事件。
- 超出计划的小增补：①`start_scenario_event_relay` 暴露 `_relay_ready` 订阅就绪事件（测试确定性需要，numsub 会被僵尸订阅连接污染）；②顺带修复 `_registry` 永不清理的内存泄漏（计划内注明）；③`app/core/redis.py` 单例改为按事件循环缓存——asyncio 连接绑定 loop，原全局单例在多 loop（TestClient / 多 worker）下必挂，属本次改造暴露的既有缺陷。
- 偏离：无。
- **后续演进（2026-09-15）**：本计划的回放流（XRANGE/XADD/合成快照）已在 `2026-09-13-sse-scope-refactor.md` 中随 stage 退场一并移除（终态由端点查库短路、阶段由前端轮询驱动，回放无服务对象）；总线核心（pub/sub 跨实例中转、降级、终态清理、侧别过滤）保留。

## 背景与问题
`app/services/scenario/stream.py` 的事件总线（`_subscribers` 集合 + `_emitted` 回放 + `_registry` 模块字典）与 `scenario_domain.py` 的 `_guess_round_locks`（64-68 行定义，744/763 行使用）全部是进程内状态。单进程正常；多实例/多 worker 下：观众 SSE 连到实例 B 而推演在实例 A 时，B 查不到挑战的 stream 对象会新建空流，观众永远收不到事件；猜词轮次的 JSON 列读改写跨进程无锁保护。

## 定案决策
1. 范围＝事件总线 + 猜词轮次锁（不含 LLM 信号量 Redis 化、僵尸任务清理）
2. 拓扑＝单一全局 pub/sub 频道广播全部事件（信封带 origin 实例 ID + challenge_id，实例本地过滤）+ per-challenge Redis Stream 只存 replay=True 结构性事件（每挑战约 5~10 条）做重连回放
3. view_chunk/god/turn 严格保持现状语义：不补历史逐字，权威全文靠详情接口落库回合，前端零改动
4. Redis 淘汰：接受 compose 的 allkeys-lru 256mb 不动；事件流 key TTL=2h；快照可从 DB challenge.status 重建兜底
5. Redis 故障：静默降级单进程模式（本地投递照旧）+ warning 日志（状态翻转时打一次防刷屏）
6. 验收＝pytest 集成测试（真实 Redis 可达才跑，沿用 test_ability_pair_cache.py 先例）+ 本地双 uvicorn 验收脚本
7. 不改 docker-compose/nginx 部署拓扑

## 改动明细

### 1. app/services/scenario/stream.py（重写，核心）
公开接口不变（get_scenario_stream / subscribe / unsubscribe / publish），内部：
- publish()：①本地 _subscribers 立即投递；②PUBLISH 全局频道（信封 {origin, challenge_id, event}）；replay=True 事件 XADD 到 scenario:challenge-replay:{challenge_id}（TTL 2h）
- subscribe() 改 async（唯一调用点在 SSE 端点协程内）：快照优先 XRANGE；Redis 空/不可用回退本地 _emitted；再兜底按 DB status 合成 stage 快照（preparing→[compare]、active→+ready、resolving→+thinking；终态由端点 DB 短路）
- 新增后台 relay 协程 start_scenario_event_relay()：订阅全局频道；origin==自身跳过（防回环双投）；按 challenge_id 只查不建本地对象（_peek）；有本地订阅者才投递（不重复写回放）
- 降级：所有 Redis 调用 try/except RedisError/OSError → warning（翻转时一次）
- 顺带修内存泄漏：publish 到 done/error 后从 _registry 移除（终态后端点靠 DB 短路）
- 模块级 instance_id = uuid4().hex；复用 app/core/redis.py 单例（1s 超时）

### 2. app/main.py（+3 行）
现有 lifespan（24 行）内 create_task 启动 relay，退出时 cancel。

### 3. app/api/routes/scenario_domain.py
- SSE 端点（约 701-740 行）stream.subscribe() 前加 await
- 删除 _guess_round_locks/_guess_round_lock（64-68 行）
- _save_guess_split / _save_guess_match（744、763 行）：asyncio 锁改单事务 SELECT...FOR UPDATE 锁定 challenge+progress 两行，固定先 challenge 后 progress 顺序防死锁，读改写逻辑不变

### 4. tests/test_scenario_stream.py（新增）
用例：①replay 事件跨实例回放（绕过 _registry 直接实例化第二个 stream 模拟实例 B，经 relay 收到）；②view_chunk 即发即弃、不进回放；③自身 origin 不双投；④done/error 后 _registry 清理

### 5. scripts/dual_instance_check.py（新增）
假定 8102/8103 双 uvicorn 共享 DB+Redis：经 API 在 A 创建挑战（比对失败也发布 stage:compare+error，无需 LLM key），向 B 开 SSE，断言收到 A 的事件则 PASS

## 实施顺序与验证
1. stream.py + main.py → docker compose up -d redis && uv run pytest tests/test_scenario_stream.py
2. scenario_domain.py → uv run pytest tests/test_scenario_domain.py tests/test_scenario_guess_assistance.py
3. 双实例：起 8102/8103 → 跑 scripts/dual_instance_check.py → PASS
4. 回归：uv run pytest tests/test_ability_pair_cache.py tests/test_reliability.py

## 关键代码事实（执行前复核行号）
- stream.py：_emitted 只存 replay=True；发布点全在 scenario_domain.py（118/133/140/154/173/195/196/263/264/265/272 行），发布方为 3 个 asyncio.create_task 后台任务；猜词链路不发流事件
- SSE 端点：15s keepalive；status 为 failed/won/lost 时直接短路不发订阅
- Redis：REDIS_URL=redis://localhost:6380/0；compose 命令 --maxmemory 256mb --maxmemory-policy allkeys-lru
- 前端：frontend/src/sse.ts 自研 fetch+ReadableStream（非 EventSource），无 Last-Event-ID，重连=全量快照
- lifespan 已存在于 app/main.py:24

## 明确不做
LLM 信号量 Redis 化、僵尸挑战清理、compose/nginx 部署、前端改动、逐字补发、DB schema 变更、nodes/提示词改动。
