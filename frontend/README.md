# 异闻录 · 前端

「异闻录」AI 奇术对战平台（小天下集玩法）的 React 单页应用。古镇纸墨视觉：宣纸暖白、暖炭墨、朱砂印章红；命中态克制使用墨绿。禁止 emoji 与紫蓝渐变，图标一律用 `src/components/icons.tsx` 的内联 SVG。

## 技术栈

- React 19 + TypeScript 5.9（`tsc -b` 全量类型检查；版本与 openapi-typescript 7 的 peer 范围一致）
- Vite 8 构建，dev 端口 `5174`，`/api` 代理到后端 `8102`
- react-router-dom v7 路由
- oxlint 做 lint（`npm run lint`）
- TanStack Query 统一服务端缓存、请求取消与修改后失效；实时推演继续使用 SSE
- Radix UI 提供菜单、弹层与页签的键盘/焦点行为，纸墨样式由项目控制
- `src/index.css` 保存唯一主题 Token 与既有页面结构，`src/design-system.css` 管公共布局和交互（纯 CSS）
- openapi-typescript 从 FastAPI 导出接口类型；Playwright 检查交互与响应式页面

## 常用命令

```bash
npm ci            # 严格按 package-lock.json 安装（不要用 pnpm）
npm run dev       # 开发服务器
npm run build     # tsc -b && vite build，产物在 dist/
npm run lint      # oxlint
npm run nav:check # 路由图，无死链/孤岛
npm run api:generate # 由后端路由/Pydantic 模型生成 src/generated/api.d.ts
npm run api:check # 类型与后端是否一致
npm run test:e2e  # 浏览器交互与三个视口（API 样本，不调用 LLM）
```

## 目录速览

```
src/
├── main.tsx / App.tsx      # 入口与全部路由（App.tsx 的 <Route> 表是页面清单的唯一事实）
├── api.ts                  # fetch：Cookie 会话、统一错误、超时重试与 Query 兼容入口
├── queryClient.ts / useApiQuery.ts # 服务端查询的唯一缓存与订阅
├── generated/api.d.ts     # 自动生成，勿手改
├── auth.tsx                # 登录态 Context（AuthProvider / useAuth）
├── types.ts                # 跨页面共享的 API 类型与 parseUnderstanding 解析
├── sse.ts                  # SSE 流式订阅（挑战推演实时流）
├── scenarioChallenge.ts    # 发起挑战的客户端流程
├── scenarioModel.ts        # 挑战阶段模型（阶段文案、步骤、进行中判定）
├── components/             # 复用组件（图标、水墨装饰、管理布局、用户菜单、模型方案等）
└── pages/                  # 路由页面；admin/ 为管理后台子页
```

## 后端联调

后端见仓库根 `app/`（FastAPI）。开发时先 `docker compose up -d` 起数据库，再启动后端与本前端；接口文档在 `http://localhost:8102/api/docs`。

类型生成使用仓库根 `.venv/bin/python`，先按根目录指引装好 Python 依赖；也可通过 `PYTHON` 指定解释器。生成只导入应用并读取 OpenAPI，不启动 lifespan、不访问数据库。当前跨页类型已接入生成文件，部分旧页局部视图类型尚保留。

浏览器首次使用可运行 `npx playwright install chromium`。云环境已有 Chromium 时：

```bash
CHROMIUM_PATH=/usr/bin/chromium npm run test:e2e
```

`tests/live-api.spec.ts` 默认跳过。需要将本地后端的 `DATABASE_URL` 指向**隔离开发库**，再执行 `CHROMIUM_PATH=/usr/bin/chromium E2E_LIVE_API=1 npm run test:e2e -- live-api.spec.ts`。测试注册临时账号，只操作自己的奇人，结束时注销；不调用模型。不要指向生产库。截图在 `test-results/`，失败保留 trace，该目录不提交。

视觉与交互规范见 [DESIGN.md](../DESIGN.md)，推演工作流建议见 [deduction-quality-review.md](../docs/deduction-quality-review.md)。
