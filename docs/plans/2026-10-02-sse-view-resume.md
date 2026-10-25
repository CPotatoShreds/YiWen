# SSE 转写内容断线续传：view_snapshot 补发

- 状态：✅ 已完成（2026-10-02，随推演/叙述解耦一并落地；事件名落地为 narration_snapshot/narration_chunk）
- 创建：2026-10-02
- 来源：全仓审查后的架构讨论（对标 Kimi 网页端「切走再回来流式接得上」体验），方案已在对话中逐点定案

## 背景与设计意图

现状 SSE 骨架与主流聊天产品的「生成绑定会话、连接只是视图」模型已同构：生成绑在挑战状态机上（后台协程），`/stream` 只是订阅口，终态查库短路，`god_progress` 为累计字数（幂等，重连自然接续）。唯一缺口：

- `view_chunk` 是 `replay=False` 的瞬态事件，**不落库、不进快照**——断线重连后已流出的转写文本丢失；
- 前端 `liveOwn` 对 `view_chunk` 是**追加**语义（`ScenarioBattle.tsx:164`），重连后在旧半截文本上继续拼接，中间缺一段；要等 `turn` 落库才由详情接口补全。

2026-09-13 SSE scope 重构砍掉回放/快照是当时的取舍（逐字动画是观感糖、数据真相由落库 turn 保证）。本计划以最小成本补回「进行中内容的服务端缓冲」，不恢复整套回放机制。

## 定案决策

1. **缓冲位置**：`ScenarioChallengeStream` 进程内 `_view_buffers: dict[side, str]`。记录入口放在 `_fanout`（`stream.py:59`）——publish 本地路径与 relay 跨实例转发路径（`stream.py:129` 调 `stream._fanout`）共用该入口，单点覆盖两条路径，任意实例上的通道对象都持有完整 buffer。**不引入 Redis 持久缓冲**：当前 inline 模式下生成实例即流对象所在实例，多实例场景 relay 已把事件送达各实例的通道对象，进程内字典即够。
2. **补发形态**：`subscribe(side=...)` 返回的快照**前置**一帧 `{"type":"view_snapshot","side":..., "text":累计全文}`（在 `_emitted` 的 done/error 终局帧之前）。`/stream` 端点直接遍历快照（`scenario_domain.py:634-635`），**端点零改动**。
3. **前端语义为替换**：`view_snapshot` 分支 `setLiveOwn(String(event.text))` 整体替换——同时天然修复「重连后中间缺段」缺陷。`god_progress` 不动：前端每次按字数全量重算遮挡符（`ScenarioBattle.tsx:160`），天然幂等，无需快照。
4. **内存不设上限保护**：单侧转写为有限文本（千~万字符级），`turn` 落库后通道从 registry 退场（`publish` 对 done/error 的清理，`stream.py:82-84`），buffer 随对象 GC，与 `_emitted` 同等待遇。

### 明确不做

- 不恢复 Redis 回放流（XADD/XRANGE/TTL 那套）；
- 不给 buffer 加 TTL / 截断上限；
- 不做 `god_progress` 快照（幂等数字无需求）；
- 不改 SSE 端点、不改事件契约中既有事件类型。

## 改动明细

### 1. app/services/scenario/stream.py
- `__init__`（:54-57）：新增 `self._view_buffers: dict[str, str] = {}`；
- `_fanout`（:59-64）：入口处对 `event.type == "view_chunk"` 且 `event.side` 非空时执行 `self._view_buffers[side] = self._view_buffers.get(side, "") + str(event.get("text", ""))`，再走原侧别投递逻辑；
- `subscribe`（:66-71）：构造快照时若 `side` 非空且 `self._view_buffers.get(side)` 非空，返回 `[{"type":"view_snapshot","side":side,"text":buffer}, *list(self._emitted)]`，否则维持现状；
- 模块 docstring「设计边界」段（:3-6）补一句：view_chunk 进程内缓冲为重连补发服务（view_snapshot 前置帧），终态随通道退场，非持久回放。

### 2. frontend/src/pages/ScenarioBattle.tsx
- `onEvent`（:155-182）新增分支：`event.type === "view_snapshot"` 且 `event.side === ownSideRef.current` 时 `setLiveOwn(String(event.text ?? ""))`（替换）；其余行为不变。

### 3. tests/test_scenario_stream.py
沿用本文件既有风格（真实 Redis 可达才跑、直接驱动 `ScenarioChallengeStream`、跨实例用 `patch.object(stream_module, "INSTANCE_ID", ...)` 模拟），新增三个用例：
- **中途订阅补发**：发布若干 `view_chunk`（replay=False）后新 `subscribe(side)`，断言快照首帧为 `view_snapshot` 且文本为累计全文；
- **侧别隔离**：两侧各发若干 chunk，断言 challenger 订阅快照只含 challenger 侧累计文本、不含 guardian 内容；
- **跨实例 buffer**：复用 `test_cross_instance_live_delivery_via_relay` 的双实例模式，A 实例发布后经 relay 到 B 实例通道，断言 B 通道 `subscribe` 快照含 A 的累计文本（验证 `_fanout` 单入口覆盖 relay 路径）。

### 4. tests/test_scenario_event_scope.py
执行时跑一遍看：若有断言订阅快照形状/事件序列的用例，按新快照帧同步调整；无则不动。

## 验证

1. `uv run pytest tests/test_scenario_stream.py tests/test_scenario_event_scope.py -q`，通过后全量 `uv run pytest tests/ -q`；
2. `cd frontend && npm run build`（tsc 通过）；
3. 手动验收（dev 环境真实推演）：推演转写进行中刷新战斗页 / 断网重连，己方转写从**完整当前进度**接续而非中间缺段；守方视角同理；`god_progress` 遮挡符增长不回退；终态后详情与结果面板与现状一致。

## 关键代码事实（执行前复核）

- `stream.py`：`_emitted` 仅收无侧别终局事件（:57）；`publish` 的 replay 参数控制是否入快照（:77-81）；done/error 后 `_registry.pop` 通道退场（:82-84）；relay 收他人实例事件调 `stream._fanout(envelope["event"])`（:129）——这是 buffer 记录必须落在 `_fanout` 的原因；
- 前端唯一 SSE 消费方 `ScenarioBattle.tsx`：`view_chunk` 追加语义（:162-165）、`turn` 到达清空 live 文本（:175-176）、断线经 `onClose: reconnect` 1.5s 后 `streamRetry+1` 重触发订阅 effect（:148-151, :183-186）、`liveOwn` state 跨重连保留（正是缺段缺陷的来源，也是 snapshot 替换语义能修复它的原因）；
- SSE 端点 `scenario_domain.py:610-646`：查库短路（failed→error 帧、won/lost→done 帧）在订阅之前，快照遍历（:634-635）自动携带新帧；
- 事件契约：`view_chunk` 由 `flows.stream_scenario_view` 逐 chunk 发布（`flows.py:92`，replay=False）；`turn` 双侧发布在落库之后（`flows.py:216-221`）。
