# 清理记录 · 第一站：frontend/

> 2026-09-18 清理。本文用大白话讲清楚这站做了什么、为什么，以及清理后 `frontend/` 里每个文件是干什么的。
> 验证方式：`npm run lint`（0 错误）+ `npm run build`（tsc 全量类型检查 + Vite 打包通过）。

## 一、这站删了什么（为什么是垃圾）

前端在 2026-09-11 经历过一次大改版：旧的「对战、棋盘、收藏、好友、排行榜、通知、试验场」等页面全部下线，换成了现在的「小天下集」玩法。页面代码删掉了，但它们的**陪葬品**留了下来。本次清理：

| 类别 | 内容 | 为什么是垃圾 |
|---|---|---|
| 死文件 | `src/time.ts`、`src/components/StatNumber.tsx`、`src/hooks/useStatDelta.ts` | 全仓库没有任何地方 import。StatNumber（名望/见闻数值动效）是旧对战页的组件，useStatDelta 是它的专属 hook，一死死一双 |
| 死资产 | `src/assets/react.svg`、`vite.svg`、`hero.png`、`public/icons.svg` | Vite/React 官方脚手架的示例图和一张旧首页图，全项目零引用（页面图标用的是 icons.tsx 内联 SVG，网站图标是 favicon.svg） |
| 死图标 | `icons.tsx` 里 7 个：剑、锁、眼、时钟、奖杯、铃铛、主页 | 原页面删除后无人使用 |
| 死装饰 | `Ornaments.tsx` 里 2 个：`Brush`（毛笔）、`BattleBanner`（挂幡） | 服务于已删的「对决中」状态和旧首页摆场按钮 |
| 死样式 | `index.css` 从 **2473 行瘦身到 1524 行**（-949 行） | 通知铃铛、异闻榜、VS 对决签、记分牌、好友拜帖、旧版猜词卡、四步指示器、trace 调试面板、Markdown 渲染……全是已删页面的样式。每一行都经过脚本逐类名验证：在全部 tsx 里零出现 |
| 死依赖 | `react-markdown` + `remark-gfm` 两个 npm 包 | 唯一消费者（Markdown 组件）在改版中已删，全项目零 import，已 `npm uninstall` |
| 死导出 | `types.ts` 的 `Ability` 接口、icons/Ornaments 的上述符号 | 定义了但无人使用 |
| 死文案 | 管理端删用户确认框里的「行迹与故人关系」 | 「故人」（好友）域已删，文案改为「其奇术、奇人与挑战数据都会被清理」 |
| 构建产物 | `dist/` | 随时可由 `npm run build` 重新生成，不入库 |

**特意保留的**：`ui-archive/2026-09-11-pre-rework/`（改版前 UI 的完整本地备份，git 里没有历史，删了就真没了）——除非你确认不再需要，否则不动。

**清完没发现的遗憾**：无。审计方式是「符号级引用审计 + CSS 类名逐 token 全局比对」双重验证；审计还纠正了两个误判——`world-post-row`（卷册列表行）和 `world-story`（战斗页主面）看似旧命名，实际是现役页面在用，一律保留。

## 二、清理后每个文件的作用

### 根目录

| 文件 | 作用 |
|---|---|
| `index.html` | 单页应用唯一的 HTML 壳：挂载点 `#root`、网站图标、主题色 |
| `vite.config.ts` | 构建配置：dev 端口 5174、`/api` 代理到后端 8102 |
| `tsconfig*.json` 三件套 | TypeScript 配置（应用 / Node 各一份 + 总装） |
| `.oxlintrc.json` | oxlint 规则（React hooks 规则报错级） |
| `package.json` | 依赖清单与脚本；`npm run build` = 类型检查 + 打包 |

### src/ 顶层（应用骨架）

| 文件 | 作用 |
|---|---|
| `main.tsx` | 入口：挂载 React、引入全局样式 |
| `App.tsx` | **路由总表**——全站有哪些页面，看这里的 `<Route>` 清单就是唯一事实 |
| `api.ts` | fetch 封装：Cookie 会话、统一错误对象 `ApiError`、连接超时、GET 失败重试、GET 内存缓存（写操作按前缀失效缓存） |
| `auth.tsx` | 登录态 Context：谁登录了、登录/登出动作，全站通过 `useAuth()` 取用 |
| `types.ts` | 跨页面共享的 API 数据类型 + `parseUnderstanding`（把奇术因果槽位 JSON 安全解析成对象） |
| `sse.ts` | SSE 流式订阅：挑战推演的实时事件（上帝进度、逐字转写）就靠它 |
| `scenarioChallenge.ts` | 「开始挑战」的客户端流程封装 |
| `scenarioModel.ts` | 挑战阶段模型：五个阶段的文案与步骤条数据、进行中状态判定 |

### src/components/（复用组件）

| 文件 | 作用 |
|---|---|
| `icons.tsx` | 全站图标库：内联 SVG 线性图标（禁止 emoji 的规矩就靠它落实） |
| `Ornaments.tsx` | 水墨装饰：灯笼、远山、印章、云纹、空卷、奇术卡背、认证页侠客剪影 |
| `AdminLayout.tsx` | 管理后台的框架布局（侧导航 + 子页出口） |
| `BarChart.tsx` | 纯 SVG 柱状图（管理端流量/统计用） |
| `DangerZone.tsx` | 设置页的「危险区」：账号注销 |
| `EmailBinding.tsx` | 设置页的邮箱绑定/换绑流程 |
| `ModelProfiles.tsx` | 用户自配 LLM 方案：列表、编辑（api_key 经 jsencrypt RSA 加密传输）、激活、连通性测试 |
| `ScenarioHistory.tsx` | 挑战记录列表（阵容页与战斗界面共用） |
| `ScenarioNarrative.tsx` | 推演正文的"墨迹条目"渲染（逐字流式视图） |
| `UserMenu.tsx` | 右上角悬浮用户菜单（头像、登出） |

### src/pages/（路由页面，23 个全部在册）

| 分组 | 文件 | 作用 |
|---|---|---|
| 认证 | `Login` `Register` `ForgotPassword` `ResetPassword` `VerifyEmail` | 登录 / 注册（邮箱+验证） / 找回密码 / 重置密码 / 邮箱验证 |
| 条款 | `Terms` `Privacy` | 用户协议、隐私政策 |
| 浏览 | `Scenarios` `ScenarioDetail` `Home` `Me` | 卷册列表、卷详情、登录后首页、个人资料页 |
| 创作 | `CreatorStudio` `ScenarioComposer` | 奇人奇术工作室（双路由复用）、新卷编排器 |
| 挑战 | `ScenarioRosterDetail` `ScenarioBattle` `ScenarioRecords` `ChallengeRedirect` | 阵容详情（奇术轮盘）、单轮战斗界面（推演+猜词）、挑战记录账册、旧挑战链接兼容跳转 |
| 设置 | `Settings` | 账号设置（装配上面三个组件） |
| 管理后台 | `admin/Dashboard` `AdminUsers` `AdminAbilities` `AdminTraffic` `AdminScenarios` + `admin/types.ts` | 后台总览、用户管理、奇术管理与因果槽位、流量统计、卷册管理；types.ts 是后台共用类型 |

### 样式

| 文件 | 作用 |
|---|---|
| `src/index.css` | 唯一全局样式表（1524 行）：主题 tokens（色板/字体/动效）、基础布局、按钮表单、以及按页面分段的样式。清理时删掉的全部是已删页面的段落，现役页面的类名逐一保留 |

## 三、给后来者的话

- 判断页面存废，看 `App.tsx` 的路由表；判断样式类是否还在用，拿类名去 src 里全局搜。
- 本站验证命令与结果：`npm run lint`（0 错误，2 个警告为 AdminUsers 既有的 useEffect 依赖写法，非本次引入）、`npm run build`（通过）。
- 下一站预告：`migrations/`。
