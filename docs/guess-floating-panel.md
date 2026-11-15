# 刻印详情猜词小窗

2026-11-16。入口为 `/scenarios/:scenarioSlug/rosters/:rosterId`，仅挑战者显示；作者知道自己的奇术，不显示猜词入口。

## 实现前查阅的交互规范

- [Material Floating Action Button](https://github.com/material-components/material-components-web/tree/master/packages/mdc-fab)：悬浮按钮承载当前屏幕的高频动作，需有可访问名称，触摸命中区至少 48×48px。此处只有一个 56×56px 入口，并显示“猜测”，不依赖悬停才能理解用途。
- [WAI-ARIA Dialog Pattern](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/)：打开时设置合理初始焦点，提供可见关闭按钮，Esc 关闭并返回触发位置；非模态窗口不能错误声明 `aria-modal=true`。本组件用 Radix Dialog 的 `modal={false}`，保持背景线索可阅读和操作。桌面初始焦点在输入框，手机在标题，避免一打开就强制弹出键盘。
- [UI/UX Pro Max](skill://user/6aeb5a27c66081918f06adc1e342c3d6/ui-ux-pro-max/SKILL.md) 的定向指南：安全区域、键盘避让、明确的加载/错误反馈、非颜色单一反馈、关闭时保留输入。使用 VisualViewport 跟随可视高度及键盘偏移；判词同时展示文字和已有语义色。

以上外部规范只用于行为约束；页面继续使用仓库既有纸墨色板、字体、朱砂与卡片质感。入口固定在右下，暂不引入拖拽、吸边、自动展开或装饰动画。固定位置避免遮挡位置不可预测，也无需增加键盘拖拽交互。

## 前后端衔接

1. 取该刻印中访问者自己的非失败、非试炼对局；若累计记录存在未完成猜词，优先绑定它的 `challenge_id`。本次页面访问内固定此对局，切换刻印后重置。
2. `POST /api/scenario-challenges/{id}/guess`，请求体 `{ "text": "..." }`。只发一次，不自动重试；按钮锁住到服务端返回状态。网络失败先回读状态，保留输入。
3. `GET /api/scenario-challenges/{id}` 返回 `guess_rounds`、`guess_cards`、`guess_credits` 与两个 in-flight 标记。仅任务进行中每 1.5 秒轮询；空闲时停止。猜词没有对应 SSE 事件，继续使用后端已有查询协议。
4. 逐配对显示本轮结果，复用详情页线索样式与“是 / 否 / 部分是 / 不确定”配色；单个配对失败显示“判定失败”。关闭窗口不取消服务端任务，轮询继续到结束；重新进入详情可读取已落库结果及恢复未结束的猜词。
5. `POST /api/scenario-challenges/{id}/guess/verify` 独立执行看破检定。已有完整猜词记录时可用，不要求剩余提问次数；完成后只呈现后端公开的看破数量/卡片信息。
6. 查询结果变化时精确失效当前刻印详情，让次数、反馈和看破卡片同步。只渲染公开字段，不显示内部 `missing`、原因分析或对方未看破的机制。

草稿保留在当前组件内存中：收起再打开仍在，刷新不会保存未提交文本。已提交结果从服务端恢复，不写入 localStorage。无可用对局、次数不足、加载失败及全部看破分别显示明确状态。

## 验证范围

`frontend/tests/guess-panel.spec.ts` 使用模拟 API 检查请求路径/请求体、重复提交防护、轮询结束、收起后继续等待、线索刷新、独立检定、刷新恢复、错误保留输入、作者/无次数状态、键盘焦点及手机可视区域。模拟数据仅存在于测试中。

本次不修改后端或提示词。浏览器测试验证协议和交互，不代表真实模型输出质量；真实模型调用仍取决于本地后端的模型配置。
