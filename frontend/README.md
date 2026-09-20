# 异闻录 · 前端

「异闻录」AI 奇术对战平台（小天下集玩法）的 React 单页应用。古镇纸墨视觉：宣纸暖白、暖炭墨、朱砂印章红；命中态克制使用墨绿。禁止 emoji 与紫蓝渐变，图标一律用 `src/components/icons.tsx` 的内联 SVG。

## 技术栈

- React 19 + TypeScript（strict，`tsc -b` 全量类型检查）
- Vite 8 构建，dev 端口 `5174`，`/api` 代理到后端 `8102`
- react-router-dom v7 路由
- oxlint 做 lint（`npm run lint`）
- 样式为单一全局 `src/index.css`（纯 CSS，无框架）

## 常用命令

```bash
npm ci            # 严格按 package-lock.json 安装（不要用 pnpm）
npm run dev       # 开发服务器
npm run build     # tsc -b && vite build，产物在 dist/
npm run lint      # oxlint
```

## 目录速览

```
src/
├── main.tsx / App.tsx      # 入口与全部路由（App.tsx 的 <Route> 表是页面清单的唯一事实）
├── api.ts                  # fetch 封装：Cookie 会话、统一错误、超时重试、GET 内存缓存
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
