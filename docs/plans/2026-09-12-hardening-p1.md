# P1 · 运营必备

- 状态：✅ 已完成（2026-09-12；两项待定见执行记录）
- 创建：2026-09-12
- 部署前提：需先确定生产环境以落地备份外拷与日志落盘位置

## 执行记录（2026-09-12）
1. **邮箱体系** ✅ `users.email` 可空 + 部分唯一索引（迁移 `c8d9e0f1a2b3`）；`/auth/forgot-password`、`/auth/reset-password`、`/auth/me/email`、`/auth/verify-email` 四端点；itsdangerous 签名令牌 15 分钟；邮件服务 console/smtp 双实现（**DirectMail 走其 SMTP 端点，并入 smtp provider**——计划中"独立 alidm provider"简化为纯配置项）。前端：忘记口令/重置口令/邮箱验证三页面 + Settings 绑定组件 + 登录页入口。**偏离**：注册不再收邮箱字段（计划原文"注册可选填"）——未验证邮箱不入库，绑定一律走验证流程，更严谨。**待定：阿里云 DirectMail 开通 + SMTP 凭据配置后把 `EMAIL_PROVIDER` 切到 `smtp`。**
2. **可观测性** ✅ 结构化日志先行已落地：`RequestIdMiddleware`（纯 ASGI，透传/生成 X-Request-ID，contextvar 贯穿后台任务）+ `LOG_JSON` 开关的 JSON 格式化。**顺带修复**：`RequestLoggingMiddleware` 此前从未接线，流量统计实际不工作，已挂载。
   **告警平台（2026-09-15 收口）**：部署环境定为腾讯云，选型落地为两条路并写入 `deploy/README.md` 可观测性节——①腾讯云 CLS 日志服务（推荐：数据不出境、零新增容器，采集 JSON 日志 + 按 level=ERROR/5xx 配告警）；②自托管 GlitchTip（需在 `app/main.py` 引 sentry-sdk 约 5 行，启用前再做）。
3. **安全收尾** ✅ `SecurityHeadersMiddleware`（nosniff/DENY/Referrer-Policy/CSP frame-ancestors，HSTS 按 HTTPS Cookie 开关下发）；pip-audit 已入 CI。
4. **后台任务可靠性** ✅ `app/services/scenario/recovery.py`：启动扫描 preparing/resolving 超 30 分钟的挑战标 failed 并复位在途标志（阈值保证多实例滚动重启不误杀），已接线 lifespan，测试覆盖。
5. **健康检查** ✅ `/health` 返回 DB/Redis 分项，DB 不可达 503（供 LB 摘除），Redis 降级不影响判定。

## 任务明细（方案选型粒度，启动执行前再拆细）

### 1. 邮箱体系（约 1 周）
- **注册即收邮箱（2026-09-13 最新决策）**：注册表单为 邮箱+用户名+口令 三要素，邮箱必填、全库唯一，但**注册时不发验证邮件**（直接入库，作为找回口令的凭证）；换绑/更正邮箱走验证流程（`/auth/me/email` + `/verify-email`）。
- 邮件服务抽象层（应用内接口）+ 双实现：`console`（写日志，开发/测试零配置）；`smtp`（smtplib 手搓实现——**当前启用的免费备用方案**：QQ 邮箱 `smtp.qq.com:465`、163 邮箱 `smtp.163.com:465`，在邮箱设置生成"授权码"填入 `SMTP_USERNAME`/`SMTP_PASSWORD`；将来开通阿里云 DirectMail 只需把 HOST 换成 `smtpdm.aliyun.com`，代码零改动。配置示例见 `.env.example` 邮件段）。
- 密码找回：签名一次性 token（itsdangerous，15 分钟有效）+ 重置页；邮箱验证流程；通知能力预留（模板化）。
- 登录/注册页已按"严肃规整"标准重做（邮箱字段、口令可见切换、错误 alert、条款微文案）。

### 2. 可观测性（约 2 天）——结构化日志先行（已定案）
- request_id 中间件（contextvar 贯穿请求→后台任务→LLM trace）+ `app/core/logger.py` 扩展 JSON 结构化输出。
- 错误聚合/告警平台：标待定（Sentry SaaS / 自托管 GlitchTip / 暂不接入三选一，待云环境确定后决策）。

### 3. 安全加固收尾（约 1 天）
- 安全响应头中间件（CSP/HSTS/X-Frame-Options/X-Content-Type-Options）。
- `pip-audit`（或 `uv audit`）加入 CI 依赖扫描步骤。

### 4. 后台任务可靠性（约 2~3 天，可独立立项）
- 启动扫描：resolving/preparing 状态超过阈值的挑战标记 failed（用户侧可见错误可重试）。
- 与 SSE 总线改造计划（2026-09-12-sse-bus-refactor.md）协同：relay 协程同在 lifespan，注意启动顺序。

### 5. 健康检查深化（半天）
- `/health` 探 DB（SELECT 1）与 Redis（PING），返回分项状态。

## 执行记录
（执行时追加）

## 明确不做
RBAC/审计、分页补全、metrics（属 P2）。
