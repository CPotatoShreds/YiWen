# 刻印详情猜词小窗

2026-11-16。详情 `/scenarios/:scenarioSlug/rosters/:rosterId` 及其 `/battle`、`/records` 子页共享同一个悬浮球。仅挑战者显示；作者不显示猜词入口。

## 实现前查阅的交互规范

- [Material Floating Action Button](https://github.com/material-components/material-components-web/tree/master/packages/mdc-fab)：悬浮按钮承载当前屏幕的高频动作，需有可访问名称，触摸命中区至少 48×48px。此处只有一个 56×56px 入口，并显示“猜测”，不依赖悬停才能理解用途。
- [WAI-ARIA Dialog Pattern](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/)：打开时设置合理初始焦点，提供可见关闭按钮，Esc 关闭并返回触发位置；非模态窗口不能错误声明 `aria-modal=true`。本组件用 Radix Dialog 的 `modal={false}`，保持背景线索可阅读和操作。桌面初始焦点在输入框，手机在标题，避免一打开就强制弹出键盘。
- [UI/UX Pro Max](skill://user/6aeb5a27c66081918f06adc1e342c3d6/ui-ux-pro-max/SKILL.md) 的定向指南：安全区域、键盘避让、明确的加载/错误反馈、非颜色单一反馈、关闭时保留输入。使用 VisualViewport 跟随可视高度及键盘偏移；判词同时展示文字和已有语义色。

以上外部规范只用于行为约束；页面继续使用仓库既有纸墨色板、字体、朱砂与卡片质感。悬浮球默认在右下，可用鼠标或触摸拖动，松手后贴近左右边缘，限制在可视区域内；拖动超过 6px 不触发展开。方向键可移位，Enter / Space 展开，Esc 收起。窗口跟随球的位置并限制在可视区域，手机键盘出现时重新布局。

## 前后端衔接

1. 取该刻印中访问者自己的非失败、非试炼对局；若累计记录存在未完成猜词，优先绑定它的 `challenge_id`。提交时绑定当前对局；同一刻印的详情、对战与记录共用会话，切换刻印后重置。
2. `POST /api/scenario-challenges/{id}/guess`，请求体 `{ "text": "..." }`。只发一次，不自动重试；按钮锁住到服务端返回状态。网络失败先回读状态，保留输入。
3. `GET /api/scenario-challenges/{id}` 返回 `guess_rounds`、`guess_cards`、`guess_credits` 与两个 in-flight 标记。仅任务进行中每 1.5 秒轮询；空闲时停止。猜词没有对应 SSE 事件，继续使用后端已有查询协议。
4. 轮次保持最新在上；每轮以 `atoms[].index` 排列分词，配对结果以 `atom_index + card_index` 落入固定单元格，不依赖请求完成顺序。每条原子猜测只显示一次，下面按奇术编号放一排答案气泡；正在等待显示“待判定”，单个配对失败显示“失败”，不伪造“不确定”。详情线索复用这份有序数据；仅在没有轮次数据时回退到 feedback，避免叠加同源数据。
5. 关闭窗口或在同一刻印的子页间切换不取消任务，保留输入与历史；后台轮询继续到结束。直接进入对战或记录页也加载同一刻印的猜词上下文。
6. `POST /api/scenario-challenges/{id}/guess/verify` 独立执行检定，不额外扣次数。返回 `verification_id`；同次检定的逐卡结果写入现有 JSON 存档，使用相同 ID、猜测轮次和时间。`guess_cards[].verifies` 只公开 `id / round / created_at / cracked`，不公开 missing 或内部分析。小窗以“进行了看破检定”一行加逐卡“看破 / 未看破”气泡显示，并在刷新后恢复；没有返回的结果仍标为进行中或无结果。已看破的卡片在后续检定中保留已知状态。
7. 查询结果变化时精确失效当前刻印详情，让次数、反馈和看破卡片同步。只渲染公开字段，不显示内部 `missing`、原因分析或对方未看破的机制。

草稿和悬浮球位置保留在当前刻印的共享组件内存中：详情、对战、记录之间切换及收起再打开仍在，刷新不会保存未提交文本或拖动位置。已提交结果从服务端恢复，不写入 localStorage。无可用对局、次数不足、加载失败及全部看破分别显示明确状态。

## 验证范围

`frontend/tests/guess-panel.spec.ts` 使用模拟 API 检查请求协议、重复提交防护、跨页保留、鼠标与触摸拖动贴边、拖动后轻触开关、直接进入子页、轮询恢复、线索刷新、检定历史与手机布局。`guess-model.spec.ts` 验证乱序配对、旧数据去重、稳定气泡位置与检定顺序。`tests/test_scenario_guess_assistance.py` 检查检定元数据一致性及公开字段过滤。模拟数据仅存在于测试中。

新增检定公开元数据使用现有 JSON 存档，无数据库迁移；提示词和判定规则不变。浏览器测试验证协议和交互，真实模型调用仍取决于本地后端的模型配置。
