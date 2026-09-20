# 清理记录 · 第六站：docs/

> 2026-09-20 清理。文档站的难点在于：文档既是档案又是说明书——删错了丢历史，留着不动
> 就是误导源。本站的处理原则：**冒充"现状"的过时文档坚决重写或删除，自带日期的历史档案原样保留**。
> 验证方式：全库 grep 过时引用归零；被保留文档逐一核对事实基础。

## 一、删除的 4 份废弃文档（均经你确认）

| 文件 | 是什么 | 为什么废弃 |
|---|---|---|
| `交接文档.md`（8/20，83 行） | 写给"8 月 20 日接手者"的时间胶囊：描述的整个 services 架构（battle/loadouts/economy/matchmaking/support、nodes/battle、试验场）已不存在；协作红线已被新版 AGENTS.md 吸收；git 状态快照全部过期 | 误导率极高——按它找文件全部扑空 |
| `后端改动影响.md`（8/9，119 行） | 「说书语系改版」实施清单，全部改动点（loadouts 加列、battles 路由等）已被后续重构推翻 | 历史实施记录，其实施对象已不存在 |
| `codex-langfuse-otel-deployment-guide.md`（8/22，182 行） | 自托管 Langfuse + OpenTelemetry 的 LLMOps 部署方案 | **从未采用**：代码零引用，现役可观测是 Prometheus `/metrics` + llm_traces 表；已定决策表中明确记为"后续迭代再议" |
| `collection-chain-stability-report.md`（8/26，84K/1116 行） | 8 月 26 日对小天下集推演链路的 TTFT 性能实测（逐场景耗时、断言通过率） | 测量对象（节点形态）已重构，数据全部失效；本质是带时间戳的一次性测量输出 |

> 删除的风险控制：git 历史永久可查，真要考古随时 `git show`。已在 `product-design.md` 的已定决策表里为 langfuse 方案留了"未采用"记录，防止将来重复调研。

## 二、重写：product-design.md（v3.4 → v4.0）

原文件**自相矛盾**：头部声明"现役玩法为小天下集"，正文却 80% 在描述已删除的旧对战世界
（摇签匹配、Elo 名望、见闻养成、故人系统、传阅页、reveal_on_miss、guess_state 状态机、
旧前端页面表），按它理解产品会完全跑偏。

重写后的 v4.0：
- **保留了手调内容**：说书语系术语字典（仅保留现役条目，已删域词条随域退场）、设计哲学（纯机制对抗、无数值、奇术保密）、已定决策表。
- **正文按现役代码提炼**：核心循环改为「建卷 → 发布阵容 → 挑战 → 比对 → 上帝推演 → 转写 → 猜词 → 看破」；功能设计对齐 3.2-3.6 节的实际行为；架构节反映 services 重组后的分层规矩；修正了旧文"BYOK 尚未接入"的说法（llm_profiles 即 BYOK，已实现）。
- 旧版全文在 git 历史里，随时 `git show HEAD~N:docs/product-design.md` 考古。

## 三、就地修正：current-model-api.md 的 5 处滞后

现役接口文档，但内容停在 9 月 6 日，本会话的改动让它过期：

1. `users` 表：`is_admin` → 实为 `role`（user/admin），并补上 `email`（可空非空唯一）与 `deleted_at`（注销软删）。
2. `scenario_roster_revisions`："锁版本"字样 → `lock_version` 已随旧审核流删除。
3. `understanding` 的说明"当前不进入小天下集快照或提示词" → 实际比对节点已把它作为因果槽位附入对比输入。
4. "Alembic head 为 `fc2d3e4f5a6b`" → 现 head `6102d944c525`，并链接到全链编年史。
5. 补缺失的表与接口：`refresh_tokens`、`admin_audit_logs` 两张表，认证接口一节，`/admin/audit-logs` 端点。

## 四、保留原样的部分（及理由）

| 内容 | 理由 |
|---|---|
| `plans/`（7 份带日期计划 + README） | 带日期的历史计划档案是惯例格式：文件名即免责声明，记录设计决策的来龙去脉 |
| `数据库备份与恢复.md` | 现役运维文档；引用的三个脚本（backup/pull/restore）均已核实存在；含演练记录表 |
| `清理记录-01~05` | 本会话各站台账 |
| `current-model-api.md` | 现役接口文档（本站已修正滞后点） |

## 五、同步与验证

- `AGENTS.md` 的文档指引行同步更新（不再指向已删文档，改为逐份点名现役文档）。
- 全库 grep：`后端改动影响 / 交接文档 / collection-chain-stability / langfuse / 锁版本 / fc2d3e4f5a6b` 零残留。
- `docs/` 最终结构（17 个文件）：现役文档 3 份（product-design / current-model-api / 数据库备份与恢复）+ plans 历史计划 8 份 + 清理记录 6 份。
- 遗留提醒：`scripts/compare_collection_reply_chains.py` 的输出目标正是已删的稳定性报告——该脚本本身是坏脚本（引用已删节点），留给 scripts 站处置。
