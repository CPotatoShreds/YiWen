# Design

<!-- impeccable:design-schema 1 -->
<!-- 由 impeccable document 流程（降级为线程内 pass，无子代理）从已构建的代码与页面记录：
     frontend/src/index.css 的 token 与组件类、frontend/src/components/、2026-09-15 的对战页/记录页改版截图核验。 -->

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
- 书页正文行高 ≈1.95、每行约 72ch；小标签（条目注记）为 11px 等宽、淡墨色。

## Components & Structures

- **书页（`.scenario-manuscript`）**：单主视角。条目（`.ink-entry`）以 1px 墨线竖脊 + 朱砂圆点标记；`--guide`（策略，虚线脊）、`--god`（看破解锁后的上帝全文，朱砂淡晕底）、`--veil`（直播遮挡块，点状脊，正文为放大的 ❖ 字符墙）。空态用 `EmptyScroll`。
- **遮挡流**：上帝推演期间只呈现合成遮挡符号（1 符/20 字、上限 240），零文本泄露；上帝写完即收起，己方正文接替同一区域。
- **阶段条（`.scenario-stagebar`）**：五步进度（比对→等待指导→上帝推演→转写→成卷），起笔前后同一框架存在。
- **账册（`.records-ledger` / `.records-row`）**：记录阅读页骨架（账册行阅）。行以淡墨线分隔，选中行底色转 `--ground-2` 且箭头旋转 90°；展开部位（`.records-row__folio`）内嵌书页与判词条（`.records-verdict`，胜=墨绿、负=朱砂）。
- **印章**：`SealStamp` 用于胜负与落款；胜/负同时以文字色（墨绿/深朱砂）强化。
- **页头**：`.scenario-challenge__masthead` + 右侧操作簇（`.scenario-challenge__actions`：翻阅往期按钮 + 状态胶囊）。

## Surfaces

- **对战页（`/scenarios/:slug/rosters/:id/battle`）**：唯一对战页。单栏全宽；起笔前与起笔后统一框架；书页是视觉重心，操作区（选人/策略/起笔）落在书页下方；结果面板带胜印与再战/回看/返回。
- **记录阅读页（`/scenarios/:slug/rosters/:id/records`）**：账册行阅——逐局一行，选中局就地展开为书页阅读（`?run=` 可深链）；未看破全部奇术时无上帝条目。
- 旧单局归档路由（`/scenario-challenges/:id`）仅作兼容跳转。

## Motion

唯一受控动效语言：`--ease` 的指数缓出（`cubic-bezier(0.16,1,0.3,1)`），用于悬停底色、箭头旋转、入场 `rise`；不引入分散效果。

## Principles in the Build

1. 推演是主角：书页占满主栏，其余元素退后；
2. 秘密有边界：未全破只看己方正文，上帝全文经看破解锁；守方永远只见自己；
3. 等待必须有形：遮挡流与状态胶囊让 LLM 等待可视且零泄露；
4. 术语即世界观：所有面向玩家的文案使用说书语系。