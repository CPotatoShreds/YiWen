# 对战页合并 + 单主视角 + 猜词搁置（含上帝门控）

- 状态：✅ 已完成（2026-09-15）
- 创建：2026-09-15
- 定案方式：grilling 三轮（用户逐题定案），设计工序 per impeccable（PRODUCT.md 推断模式）

## 背景与设计意图（用户原话归纳）
- 起笔前后的 `/battle` 是同一路由的两种外观（起笔前简洁版 → 起笔后"原来版本"：五步阶段条 + 三视角 tab + 右侧猜词栏），用户要求两态合一并重做；
- 三视角（己方/对方/上帝）改为**唯一主视角**（挑战者视角，不显示视角名）；同一书页区域内"先吐上帝遮挡块、再吐挑战者正文"；
- 右侧猜词面板撤下（猜词先搁置，后面再做）。

## 定案决策（grilling 三轮）
1. **合并形态**：重新设计一个结合项目的统一对战页；`/battle` 为唯一对战页；旧单局归档路由 `/scenario-challenges/:id` 废弃（保留兼容跳转）；记录入口改为"翻阅往期"按钮 → 专门的**记录阅读页**（只要新页，旧路由废弃）。
2. **终局与回看的可见性（新产品规则）**：**未看破全部奇术前只能看自己视角**；**看破全部后开放上帝视角——只加上帝全文**（守方正文始终不给）；守方永远只见自己的正文、无解锁路径。判定口径＝该挑战者对该阵容的**累积看破进度**（解锁后永久开放；猜词 UI 撤下期间新看破暂无法产生，门扉阶段性冻结，既有看破数据仍生效）。
3. **遮挡块**：未看破也照常显示（纯进度、零泄露）。
4. **记录阅读页**：右侧不保留；**单栏全宽**书页；记录不直接显示，用一个按钮跳转到专门的记录阅读页。
5. **猜词移除范围**：仅摘对战页面板；后端猜词管线与测试、阵容详情"行迹线索/当前卡"区全部保留。

## 改动明细
### 后端（上帝门控）
- `scenario_domain.py` 新增 `_god_unlocked(progress, abilities)`（全部奇术卡均 cracked）与 `_visible_turn(message, unlocked)`（恒剥离 `guardian_text`；`omniscient` 仅解锁携带）；
- `challenge_detail` 挑战者分支：消息按门控过滤（preview 试炼为作者自看，保持全量），响应新增 `god_unlocked`；
- `_resolve_scenario_action`：SSE turn 发布前独立会话计算解锁（对象过期安全），挑战者侧 turn 用 `_visible_turn` 过滤；守方 turn 形状不变。

### 前端
- `ScenarioBattle.tsx` 重写：单栏统一框架（阶段条起笔前后常驻）、无三视角 tab、无猜词面板与逻辑、无记录面板；`liveOwn`（己方逐字）+ `liveGod`（遮挡块）；页头"翻阅往期"按钮；结果面板"回看本局"指向记录页、未解锁时提示"待你看破这套阵容的全部奇术，上帝视角会在书页上开启"。
- `ScenarioNarrative.tsx` 重写：`ScenarioManuscript` 单主视角（`own`/`ownLabel`/`title`），上帝条目（`--god`）与遮挡条目（`--veil`）内置；删除 `ScenarioViewTabs`。
- `ScenarioRecords.tsx` 新建（账册行阅，concept-seed 摇选 index 4）：逐局一行（第 N 次推演 · 胜/负/未成卷 · 守方视角下附挑战者），选中局就地展开书页 + 判词条；`?run=` 深链。
- `ChallengeRedirect.tsx` 新建：旧路由解析归属后跳记录页。
- `scenarioModel.ts`：删除 `View`/`viewText`/`viewLabel`（视角分类退场）。
- `App.tsx` / `ScenarioRosterDetail.tsx`：路由与历史条目改指记录页；删除 `ScenarioChallenge.tsx`。
- `index.css`：追加改版样式（页头操作簇/上帝条目/遮挡块/账册），删除已死的三视角 tab 规则。
- 设计工序：新建 `PRODUCT.md`（推断模式，逐条标注）与 `DESIGN.md`（记录既有纸墨世界与新增结构）。

## 验证
- 后端：pytest 64/64（新增门控三用例：详情加锁→解锁→守方恒定；SSE turn 解锁携带）；ruff/mypy 全绿；前端 tsc + `vite build` 通过；impeccable 检测器对改动文件零发现。
- 视觉核验（本地双服务 + 种子脚本 `scripts/dev_seed_visual.py`）：对战页（单栏书页、阶段条、无 tab、无猜词、往期入口）与记录页（3 局账册、胜印、选中局展开、未破无上帝条目）截图确认。

## 偏差与披露
- PRODUCT.md 的确认问题轮未获答复 → 按规程转推断模式，文件内逐条标注；
- 设计工序中 concept-seed 的世界挑战者卡属"替换视觉世界"流程，与钉死的纸墨风 brief 冲突，未呈现（brief 优先）；
- 完成评审为**线程内降级 pass**（无 impeccable-finish-reviewer 子代理可用），以截图自查 + 检测器替代；
- 发现并修复开发环境 Vite 转换缓存楔死（编辑中间态被缓存 → 页面白屏）：touch 文件失效缓存；若本地仍见旧界面，重启一次 `npm run dev`。

## 明确不做
猜词链路重做（后续）；上帝解锁在猜词恢复前的进度推进；旧 `/scenario-challenges/:id` 恢复为独立页；`docs/current-model-api.md` 的刷新（文档债，另行）。