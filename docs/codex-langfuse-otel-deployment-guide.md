# Codex LLMOps 链路追踪方案

> 版本: v1.0 | 目标: Docker Desktop 自托管 Langfuse + OpenTelemetry 标准化接入

---

## 一、Langfuse 自托管部署（Docker Desktop）

### 前置要求

- Docker Desktop 4.30+，建议分配 4C8G
- 确保端口 3000 / 4317 / 4318 / 5432 / 8123 / 9000 / 6379 未被占用
- 磁盘预留 10GB+

### 部署步骤

1. 在项目根目录创建 `infra/langfuse/`，下载官方 compose 文件
2. 创建 `.env`，配置数据库密码、Langfuse 应用密钥、OTLP 开关（`LANGFUSE_OTLP_ENABLED=true` 为核心）
3. `docker compose up -d`，等待约 60 秒（ClickHouse 初始化）
4. 验证 `curl http://localhost:3000/api/public/health`
5. 访问 `http://localhost:3000`，首次登录后修改默认密码
6. 进入 Settings → API Keys，记录 Public Key / Secret Key（后续 SDK 接入用）

### 持久化说明

Docker Desktop 重启后数据保留（命名卷）。`docker compose down` 仅停止，`docker compose down -v` 清空数据。

---

## 二、OpenTelemetry 标准化接入架构

### 核心设计

所有 LLM 服务（soup-host / soup-judge / guess-host / embedding 等）统一通过 OTLP/gRPC 协议向 Langfuse 推送 Trace。开发环境直连，生产环境建议经 OpenTelemetry Collector 网关转发。

**关键原则**：OTel 的 `gen_ai.*` 语义约定已成为事实标准，Langfuse v3 原生支持 OTLP 接收。新增服务只需按标准埋点，看板自动按 `service.name` 分组识别，无需手动注册。

### 技术选型

| 组件 | 职责 | 说明 |
|------|------|------|
| opentelemetry-sdk | Trace 生命周期管理 | 创建 Provider、Span、上下文传递 |
| opentelemetry-exporter-otlp | 数据推送 | gRPC 协议发往 Langfuse 4317 端口 |
| openlit | 自动 instrument | 拦截 OpenAI / Anthropic 标准 SDK 调用，自动记录 prompt / completion / token |

### 接入层次

**第一层：统一初始化模块**

在项目公共库（如 `codex/internal/telemetry.py`）封装 `init_tracing(service_name, game_mode)`。所有服务启动时调用一次，完成 TracerProvider、OTLP Exporter、openlit 自动 instrument 的三重初始化。资源属性中必须包含 `service.name`、`game.mode`、`deployment.environment`，供 Langfuse 检索维度使用。

**第二层：业务链路埋点**

一次完整游戏回合（如一次海龟汤问答）作为一个 Root Span（Trace），内部按阶段拆分为嵌套 Span：

- `soup.round` — Root Span，标记 session_id / user_id
  - `host.understand` — Host 理解意图
  - `judge.check` — Judge 判定
  - `host.generate` — Host 生成叙事

Span 上通过标准属性记录关键信息：`gen_ai.request.model` 记录模型名，`gen_ai.usage.*` 记录 Token，`judge.verdict` / `judge.confidence` 记录判定结果。

**第三层：环境变量驱动**

通过 `.env` 控制接入行为，无需改代码即可切换环境：

- `OTEL_EXPORTER_OTLP_ENDPOINT` — 追踪后端地址
- `ENABLE_CONTENT_TRACING` — 是否记录输入输出内容
- `OTEL_SAMPLER_RATIO` — 采样率（生产可设为 0.1 降本）

---

## 三、现有服务接入步骤（文字指导）

### 1. 安装依赖

在 requirements.txt 追加 opentelemetry 相关包及 openlit，统一安装。

### 2. 创建公共追踪模块

建议路径：`codex/internal/telemetry.py`。封装以下内容：

- `init_tracing()`：初始化 TracerProvider、OTLP Exporter、openlit instrument。接收 service_name / game_mode / service_version 参数。
- `start_game_round()`：上下文管理器，创建 Root Span，自动注入 session_id / user_id。
- `set_llm_attributes()`：在 Span 上写入模型名、Token 数等标准属性。
- `set_judge_result()`：Judge 专用，写入 verdict / confidence。
- `record_error()`：标准化异常记录，设置 Span Status 为 ERROR。

### 3. 各服务接入

**soup-host**：启动时调用 `init_tracing("soup-host", game_mode="turtle-soup")`。请求入口处用 `start_game_round()` 包裹整个回合，内部三个阶段分别创建 Span。Host 理解阶段记录 intent.type 和 proposition；Judge 判定阶段调用 `set_judge_result()`；生成阶段记录输出 Token。

**soup-judge**：启动时调用 `init_tracing("soup-judge", game_mode="turtle-soup")`。判定逻辑用 Span 包裹，记录输入 proposition 和输出 verdict。

**guess-host**：启动时调用 `init_tracing("guess-host", game_mode="guess")`。每轮猜词作为一个 Root Span，记录 guess.word 和 is_correct。

**embedding**：启动时调用 `init_tracing("soup-embedding", game_mode="soup")`。embedding 调用创建 Span，记录 input.length 和 usage token。

### 4. SSE 场景特殊处理

SSE 每轮独立 HTTP 连接，但多轮共享 session_id。实现要点：

- SSE handler 内创建 Root Span，生命周期覆盖整个连接
- 使用 `set_span_in_context()` 保持上下文，确保内部 Host / Judge Span 都挂在同一 Trace 下
- 流式生成阶段，Span 在流结束后统一记录总 Token，避免过早关闭
- 前端收到 `event: result` 或 `event: error` 后关闭连接，Span 随连接结束而结束

---

## 四、新增服务标准化流程

新增服务（如 future battle-host）时，执行以下步骤即可在看板自动出现：

1. 安装项目统一依赖（已含 telemetry）
2. 启动时调用 `init_tracing("battle-host", game_mode="battle")`
3. 核心链路用 `tracer.start_as_current_span()` 包裹
4. LLM 调用点使用 `set_llm_attributes()` 记录模型和 Token
5. 确保环境变量 `OTEL_EXPORTER_OTLP_ENDPOINT` 指向 Langfuse
6. 发起一次测试请求，在 Langfuse Traces 页面按 `service.name = battle-host` 检索验证

**无需操作**：改 Langfuse 配置、在看板手动注册、改 Collector 规则、通知运维。

---

## 五、看板使用指南

访问 `http://localhost:3000`，核心功能：

- **Traces 列表**：按时间倒序，顶部筛选 `service.name` / `game.mode`
- **Session 聚合**：点击 `session.id` 查看同一玩家的多轮完整对话
- **延迟瀑布图**：点击单个 Trace，查看 host.understand → judge.check → host.generate 各阶段耗时
- **Prompt 检索**：顶部搜索框直接输入关键词，全文检索历史提问和回答
- **Token 与成本**：Observations 面板自动展示 `gen_ai.usage.*` 及成本估算
- **错误追踪**：筛选 Status=Error，快速定位异常链路

常用筛选语法示例：`service.name = soup-host AND judge.verdict = yes AND latency > 3000`

---

## 六、生产环境迁移路径

开发环境采用服务直连 Langfuse。生产环境建议引入 OpenTelemetry Collector 作为网关：

```
service -> OTLP -> Collector -> Langfuse (Trace 分析)
                          -> Prometheus (Metrics 监控)
                          -> S3 (长期归档)
```

Collector 承担职责：批量聚合、敏感信息脱敏（如 hash 掉汤底关键词）、采样降级、多后端分发。Langfuse 侧无需任何改动。

---

## 七、故障排查

| 现象 | 排查步骤 |
|------|---------|
| Trace 未出现在看板 | 检查 Langfuse 健康接口；检查 4317 端口监听；确认 `OTEL_EXPORTER_OTLP_ENDPOINT` 配置；开启 `OTEL_LOG_LEVEL=debug` |
| Token 消耗显示为 0 | 确认 openlit 版本 >= 1.25；确认使用标准 SDK 调用而非裸 HTTP；流式输出 Token 可能延迟上报 |
| Docker Desktop 内存不足 | ClickHouse 默认占 2-4G，可在 compose 中给 clickhouse 服务加 `mem_limit: 2g` |
| 敏感信息泄露 | 生产环境在 Collector 层加 `attributes/redact` processor，对 `gen_ai.prompt` 做 hash 或过滤 |

---

## 附录：推荐目录结构

```
codex/
├── codex/internal/telemetry.py      # 统一追踪初始化模块
├── services/
│   ├── soup_host/
│   ├── soup_judge/
│   ├── guess_host/
│   └── embedding/
├── infra/langfuse/
│   ├── docker-compose.yml
│   └── .env
├── .env.example
└── requirements.txt
```

> 维护者: Codex AI Team | 最后更新: 2026-08-21
