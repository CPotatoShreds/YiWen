# Design

<!-- impeccable:design-schema 1 -->
<!-- 由 impeccable document 流程（降级为线程内 pass，无子代理）从已构建的代码与页面记录：
     frontend/src/index.css 的 token 与组件类、frontend/src/components/、2026-09-15 的对战页/记录页改版截图核验。
     2026-10-22 对战页改为两段式（信息＋操作台 → 行迹书页），书页分 page / book 两形态。 -->

## Visual World

古镇纸墨风：宣纸铺底、暖炭墨书写、朱砂作唯一主色（印章红），墨绿只用于命中/成功态。气质是"旧书店里的手抄本"——所有界面元素都为"一页行迹"服务，装饰只用纸纹、墨线、云纹分隔与印章。

## Palette

| Token | 值 | 用途 |
|---|---|---|
| `--ground` | `#f4efe3` | 页面底（宣纸暖白） |
| `--ground-2` | `#ebe3d0` | 凹槽/条带/悬停底 |
| `--surface` | `#faf6ec` | 卡片纸面 |
| `--ink` | `#2f2b26` | 正文墨色（暖炭黑，非纯黑） |
| `--muted` | `#6f675c` | 次要文字（淡墨灰） |
| `--line` / `--line-strong` | `#dcd2bb` / `#c3b699` | 淡/深墨线 |
| `--accent` / `--accent-strong` / `--accent-soft` | `#b03a2e` / `#8f2a1f` / `#f4e0d4` | 朱砂主色/深朱砂/淡晕 |
| `--success` / `--success-soft` | `#467a53` / `#e4eee2` | 墨绿：命中、胜局（克制） |

约束：不使用 emoji、紫蓝渐变、Tailwind/Framer Motion；图标一律取 `frontend/src/components/icons.tsx`。

## Type

- 显示字 `--font-display`（Outfit + 中文回退）；正文 `--font-body`（系统栈）；书页正文 `--font-seal`（楷体）；元信息 `--font-mono`（11px 小字标签）。
- 书页正文两档：记录页（默认形态）16px / 行高 1.95 / 约 72ch；对战书页（`--book`）17px / 行高 38px 网格 / 62ch，段落间距、页上下留白与纸纹同取整行（留白非整行时行盒会整体偏离格线，正文与纸就对不上了）。
- 叙述正文**按段渲染**：模型输出的换行（一个或连续多个）一律切成独立 `<p>`，段首缩进两格（`text-indent: 2em`），段间不留空行（书页为 0，记录页约一行）。不要把整段塞进一个 `<p>` 靠 `pre-wrap` 保留 `\n\n`——那样只有块内第一行缩进，段间还会凭空多一行。
- 小标签（条目注记）为 11px 等宽、淡墨色。

## Components & Structures

- **书页（`.scenario-manuscript`）**：单主视角，两种形态。默认（记录页）带「行迹 / 第 N 次推演」标题头，条目带注记与竖脊；`--book`（对战页）是**只呈推演正文**的素页——策略、条目注记、状态提示一律不出，只剩书眉（卷名 / 第 N 次推演）、页脚（小天下集 / 页码）与正文，正文按 38px 行网格排。`--veil`（直播遮挡块，正文为放大的 ❖ 字符墙）与逐字正文互斥：第一个字到达即撤方块，正文从开头起长，不再出现「叙述排在方块下方、方块消失后上移」。`--god` 为看破解锁后的推演全文（类名为既有 CSS 契约保留）。
- **卷首双栏（`.scenario-info`）**：一条竖线分幅。左半立挑战目标（楷体大字）、本场对手（`.scenario-opponent`：姓名、简介两行截断、门数与胜率）与卷末 meta；右半并置卷规则（`cjk-ideographic` 序号）与补充判定。
- **操作台（`.scenario-console`）**：左 300px 人物榜（`.scenario-picker`，一人一行，选中整行亮朱脊），右一张无框横线信笺（`.scenario-sheet`，正文落在线里）。人数超过四位时榜内滚动。
- **书页布局（`.scenario-book` / `.scenario-rail`）**：两栏。左轨竖排五段进度（圆点串成一条线，已过段落转朱砂实心、当前段加朱砂光圈）与终局面板（`.scenario-result`：印章在上、判词其次、再战/回看/返回竖排按钮）——结果与操作在侧栏，不在页脚。右栏纸页**高度固定**（`clamp(460px, 68vh, 780px)`），正文在纸内滚动，纸本身不随字数变长；落墨**不跟随滚动**——滚动位置只由读者控制，新字落在视口外也不把人往下拽。窄屏下侧栏拆平：进度压成一行序号、终局落到纸下。
- **账册（`.records-ledger` / `.records-row`）**：记录阅读页骨架（账册行阅）。行以淡墨线分隔，选中行底色转 `--ground-2` 且箭头旋转 90°；展开部位（`.records-row__folio`）内嵌书页与判词条（`.records-verdict`，胜=墨绿、负=朱砂）。
- **印章**：`SealStamp` 用于胜负与落款；胜/负同时以文字色（墨绿/深朱砂）强化。
- **页头**：`.scenario-challenge__masthead` + 右侧操作簇（`.scenario-challenge__actions`：翻阅往期按钮 + 状态胶囊）。

## Surfaces

- **对战页（`/scenarios/:slug/rosters/:id/battle`）**：唯一对战页，两段式。起笔前是「对决信息 + 操作台」——目标、对手与卷规则全部展开，不折叠；点「发起推演」后整页换成「左轨 + 行迹书页」，进度条与书页同时出现。纸内只呈推演正文，比对期是一张未落墨的素页；终局后判词与再战/回看/返回落在左轨。奇术比对报告不在对战页呈现，只在记录页可读。
- **记录阅读页（`/scenarios/:slug/rosters/:id/records`）**：账册行阅——逐局一行，选中局就地展开为书页阅读（`?run=` 可深链）；未看破全部奇术时无推演条目。
- 旧单局归档路由（`/scenario-challenges/:id`）仅作兼容跳转。

## Navigation

跳转不是随手写一个 `<Link>`，而是**图上的有向边**。全站只有三种边，各有唯一写法，写法统一收在 `frontend/src/components/PageShell.tsx`。

| 边 | 语义 | 组件 | 长得像 |
|---|---|---|---|
| 向上 | 退回上一层 | `BackLink` | 左向箭头 + 文字，独占标题上方一行 |
| 平级 | 横向去另一个主分支 | `EntryLink` | 文字 + 右向箭头 |
| 向下 | 进入具体对象 | 不封装，由内容自身的卡片 / 行承载 | 整行可点 |

- **返回位恒定**：`BackLink` 单独占一行、位于标题上方，位置不受主操作数量影响。禁止把它塞进标题行右侧或做成图标钮——`ScenarioBattle` / `ScenarioRecords` 的圆形返回钮是沉浸式页面的例外，不适用于文档页。
- **需要拦截的返回**（例如「有未保存改动」）用 `BackLink as="button"`，不要为了拦截而把链接换成裸 `<button className="nav-back">`。
- **`/home` 是根**：文档页的上一层要么是 `/home`，要么是它真正所属的对象页，不要跳过层级直接回首页。`/yiwenlu` 是 L2，没有上一层，因此 `back={false}`。
- 不设常驻侧边导航；层级靠「`/home` + 逐层返回」表达。

### 路由约定

- **读用 slug，写用 id**：`/scenarios/:slug/**` 一律以卷的 slug 出现在 URL 里；但提交创建时后端只接受 UUID（`scenario_domain.py:310`），必须传 `scenario.id`。两者不可混用，混用即 422。
- **同一资源只有一个地址**：不要出现 `/scenarios/<uuid>` 与 `/scenarios/<slug>` 并存——后端两者都收，但这会让同一页面有两个 URL。站内跳转一律拼 slug。
- **静态段优先于动态段**：`/scenarios/:slug/rosters/new` 与 `:rosterId` 同枝，v7 的路由评分保证 `new` 不会被当成 id，无需额外判断。
- **深链**：受保护的页面被直接访问时，`RequireAuth` 跳 `/login` 并带上 `state.from`，登录后由 `returnTo()`（`frontend/src/nav.ts`）回到原目标。
- **不设 `path="*"` 兜底**：未知地址得到空白主区，这是有意为之——静默重定向会掩盖坏链。

### 版心

宽度只由 `PageShell` 的 `width` 参数决定，页面里不再写 `max-width`：

| 档位 | 值 | 用于 |
|---|---|---|
| `page`（默认） | 1080 | 常规文档页：列表、详情、设置 |
| `wide` | 1180 | 信息密度高的双栏工作台：异闻录、后台 |
| `read` | 760 | 表单与长文 |

沉浸式页面（`.scenario-challenge`、`.roster-page`）不套壳，自带 `--width-page` 作为版心。`<main class="container">` 只负责居中与留白，不设宽度。

### 校验

`npm run nav:check` 把上面这些约定变成可执行断言（`frontend/scripts/nav-graph.mjs`，AST 解路由 + 扫跳转，带 `--self-test`）：

1. **无死链**——每条静态跳转都落在一条已注册路由上；
2. **无孤岛**——每条路由都至少有一条站内入边（入口、外部链接、以及由 `pathOf()` 动态拼出的深链在脚本里显式豁免）；
3. 打印每页的入边数，看看有没有哪个页面变成了单行道。

改路由、加页面之后跑一次；`--strict` 下孤岛也算失败。

## Motion

唯一受控动效语言：`--ease` 的指数缓出（`cubic-bezier(0.16,1,0.3,1)`），用于悬停底色、箭头旋转、入场 `rise`；不引入分散效果。对战页两段互斥切换时整块 `rise` 入场，进度条按 60ms 阶梯点亮；`prefers-reduced-motion` 下全部关闭。

时长只有三档，按**变了什么**选，不按改在哪选：`--dur-fast` 0.14s（颜色 / 边框 / 阴影等微反馈）、`--dur-base` 0.18s（位移 / 缩放 / 尺寸）、`--dur-slow` 0.22s（抽屉 / 模态 / 大区块）。

例外是 `animation` 的节奏：循环动效（`pulse` `shimmer` `lanternSway`）与对战页入场的 60ms 阶梯（`.06s → .12s → .18s → .24s`）各是个别编排，保持字面量。把这串阶梯并进 `--dur-*` 就等于打断节奏。

## Principles in the Build

1. 推演是主角：书页占满主栏，其余元素退后；
2. 秘密有边界：未全破只看己方叙述，推演全文经看破解锁；守方永远只见自己；
3. 等待必须有形：遮挡流与状态胶囊让 LLM 等待可视且零泄露；
4. 术语即世界观：所有面向玩家的文案使用说书语系。