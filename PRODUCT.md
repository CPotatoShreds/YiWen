# Product

<!-- impeccable:product-schema 1 -->
<!-- 本文件由 impeccable init 流程生成：产品事实依据本会话三轮设计问答、AGENTS.md 与 docs/product-design.md、
     docs/current-model-api.md 推断；确认问题轮未获答复（推断模式），未逐条复核的事实均以"（推断）"标注。 -->

## Platform

web

## Users

- **个人异闻师玩家（核心，推断）**：在自己的电脑上创作奇术与奇人、挑战他人阵容、起笔观看 LLM 推演、复盘行迹并逐门看破对家奇术；使用场景是专注的单次游玩会话（起笔到成卷可能持续数分钟）。
- **阵容作者（次要，推断）**：编写卷、配置阵容，围观自己的阵容被挑战的过程与结果，维护自己的阵容页。

## Product Purpose

异闻录是 AI 奇术对战平台：异闻师创建奇术、装入奇人并解封，启程后由 LLM 推演行迹；败方可以依据行迹线索猜对家实际使用的奇术，全部看破后解锁上帝视角。成功 = 玩家能顺畅走完"创作 → 挑战 → 观演 → 复盘 → 看破"闭环，且推演等待期始终有可信的进度反馈。

## Positioning

双 LLM 推演（全知上帝正文 + 双方视角逐字转写）叠加看破机制（逐门猜对家奇术，全部看破才解锁上帝全文）——相邻产品无法不经重写而照搬这套"秘密有边界"的观演结构。

## Operating Context

- 现役玩法为小天下集：管理员建卷并发布 → 作者配阵容（锁修订）→ 玩家以自家奇人挑战 → 结算后获得提问次数（猜词链路）；
- 推演是长耗时流式 LLM 调用：延迟敏感，直播采用 SSE（上帝遮挡流 + 己方视角转写），阶段进度由状态轮询驱动（推断：本会话既定方案）；
- 对战页是"擂台常驻地址"（按阵容维度），单局记录阅读独立成页（本会话既定）；
- 技术栈（既有代码库）：React + TS + Vite / 纯 CSS；FastAPI + async SQLAlchemy + PostgreSQL + Redis。

## Capabilities and Constraints

- 账号三要素（邮箱 + 用户名 + 口令）、双 token 会话、限流、注销与数据导出；
- 单局状态机：preparing → active → resolving → won/lost/failed；
- 猜词（点评 + 检定）后端与数据全量保留；**前端入口本轮起搁置**，后续重启（本会话既定）；
- 看破判定为逐阵容的累积进度（本会话既定）：全部奇术看破后永久解锁上帝全文；
- 后端字段名与 API 路径保持英文稳定；面向玩家的术语用说书语系（奇术/奇人/异闻师/启程/行迹/看破/摇签/名望/见闻）；
- 单副本 FastAPI 托管前端静态文件（deploy/ 现状），多副本已由 Redis 总线支持。

## Brand Commitments

- **古镇纸墨风视觉系统**（AGENTS.md 钉死）：宣纸暖白、暖炭墨、朱砂主色、命中态克制的墨绿；禁止 emoji、紫蓝渐变与 Tailwind/Framer Motion；图标统一取 `frontend/src/components/icons.tsx`；
- 术语即世界观：一切面向玩家的文案使用说书语系（上表）。

## Evidence on Hand

- 仓库文档：`docs/product-design.md`（产品设计）、`docs/current-model-api.md`（数据模型与接口）、`AGENTS.md`（约束与冻结区）；
- 设计系统的现行实现：`frontend/src/index.css`（token 与组件类）、`frontend/src/components/Ornaments.tsx`、`icons.tsx`；
- 无对外营销物料、无客户证言、无价格页——未来工作不得虚构此类内容。

## Product Principles

1. **推演是主角**：页面为一篇"行迹"服务，界面元素退后；书页区域是唯一的视觉重心。
2. **秘密有边界**：未全破只看自己的视角；上帝全文经看破解锁；守方永远只见自己的视角。
3. **等待必须有形**：任何 LLM 等待都要有可见、可信、无信息泄露的进度表达（遮挡流、状态胶囊）。
4. **术语即世界观**：面向玩家的每一个词都属于说书语系，不混入系统腔。