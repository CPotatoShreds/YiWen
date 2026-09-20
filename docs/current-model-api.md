# 当前数据模型与接口

本文以 `app/models`、`app/schemas` 和 `app/api/routes` 的当前实现为准。

## 领域边界

现役玩法是小天下集。用户资产只有自己拥有的奇人和奇术，直接编辑生效，不经过发布、审核或版本控制。小天下集的卷、阵容修订和挑战快照属于玩法内容域，仍保留独立的发布/修订模型。情景在产品语义上统一称为“卷”，只有管理员可以创建和发布卷。

传统对战、loadout、好友、排行榜、通知、提示词调试和试验场域已移除。

## 数据模型

| 表 | 关键字段与关系 |
|---|---|
| `users` | `id`, `username`, `password_hash`, `email`（可空，非空唯一）, `role`（`user`/`admin`）, `deleted_at`（注销软删）, `active_profile_id -> llm_profiles.id`, `created_at` |
| `abilities` | `id`, `owner_id -> users.id`, `name`, `effect`, `detail`, `understanding`, `created_at`, `updated_at` |
| `characters` | `id`, `owner_id -> users.id`, `name`, `bio`, `created_at`, `updated_at` |
| `character_abilities` | `(character_id, ability_id)` 联合主键，`position` 保证绑定顺序；接口限制最多 4 门 |
| `scenarios` | 小天下集卷本体：`name` 卷名、`subtitle` 副名、`introduction` 介绍、`background` 背景、`rules` 最高优先级规则列表、`victory_condition` 胜利条件、`judgement_rules` 判定规则列表，状态为 `draft/published/deleted` |
| `scenario_rosters` | 卷阵容，引用 `character_id`，并保存名称、介绍和奇术快照；不区分官方/玩家 |
| `scenario_roster_revisions` | 阵容修订快照（`revision_number` 唯一递增）；仅属于小天下集内容域 |
| `scenario_roster_abilities` / `scenario_roster_revision_abilities` | 阵容当前/修订的奇术快照，不随用户资产修改而变化 |
| `scenario_challenge_runs` | 单次挑战的卷、守方、挑战者快照，以及消息、猜词和派生结果 JSON |
| `scenario_roster_progress` | `(roster_id, challenger_id)` 维度的挑战进度和看破卡片 |
| `llm_profiles` | 用户自配模型方案，api_key 经 Fernet 加密落库 |
| `refresh_tokens` | 刷新令牌 sha256 哈希，支持旋转与吊销 |
| `admin_audit_logs` | 管理操作审计（操作者/动作/对象/详情） |
| `llm_traces` / `request_logs` | LLM 与 HTTP 审计记录 |

`Ability.understanding` 是由可靠性层异步生成的三相因果槽位 JSON；编辑奇术后会重新调度生成，比对节点（`pair_judge._render_pair_ability`）会把它作为因果槽位附入逐对对比输入。奇人介绍 `bio` 沿用旧版奇人风格字段的语义；`style`/`tactic` 已从当前模型删除。

删除奇术会先解除所有奇人绑定；删除奇人会使已发布阵容的 `character_id` 置空，但阵容和挑战快照继续保留。

## 用户接口（`/api/creator`）

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/creator/abilities` | 当前用户的奇术 |
| `POST` | `/creator/abilities` | 创建奇术 |
| `GET` | `/creator/abilities/{id}` | 查看自己的奇术 |
| `PUT` | `/creator/abilities/{id}` | 直接修改名称、效果、详述 |
| `DELETE` | `/creator/abilities/{id}` | 删除奇术并解除绑定 |
| `GET` | `/creator/characters` | 当前用户的奇人 |
| `POST` | `/creator/characters` | 创建奇人并绑定 `ability_ids` |
| `GET` | `/creator/characters/{id}` | 查看奇人与完整奇术 |
| `PUT` | `/creator/characters/{id}` | 修改字段并以 `ability_ids` 原子替换绑定顺序 |
| `DELETE` | `/creator/characters/{id}` | 删除自己的奇人 |

创建/更新奇人时，所有 `ability_ids` 必须属于当前用户，重复 ID 会去重，最多 4 门。其他用户的资产统一返回 404。

## 小天下集接口

公开读取：`GET /scenarios`、`GET /scenarios/{id}`、`GET /scenarios/{id}/rosters`、`GET /scenarios/{id}/rosters/{roster_id}`。

用户阵容：`GET/POST /creator/scenarios/{scenario_id}/rosters`、`GET /creator/scenarios/rosters/{roster_id}`、复制和软删除阵容；请求体使用 `character_id`。

管理员卷：`/admin/scenarios/**`，只有管理员可创建、编辑、发布或下线卷。

挑战：`POST /scenario-rosters/{roster_id}/challenges`（请求体使用 `character_id`）、`GET /scenario-challenges/{id}`、`GET /scenario-challenges/{id}/stream`、以及 `actions`、`guess`、`guess/verify`、`derive`。

## 认证接口

`POST /auth/register`、`POST /auth/login`、`POST /auth/refresh`（旋转，重用即吊销全令牌）、`POST /auth/logout`、`GET /auth/me`、`DELETE /auth/me`（注销，口令确认）、`GET /auth/me/export`（数据导出）、`POST /auth/me/email` + `GET /auth/verify-email`（邮箱绑定）、`POST /auth/forgot-password` + `POST /auth/reset-password`。

## 管理与模型方案

管理员保留 `/admin/stats`、`/admin/users`、`/admin/abilities`（含 `backfill`）、`/admin/audit-logs`、`/admin/traffic` 和 `/admin/llm-traces`。

用户模型方案保留 `/llm-profiles/public-key`、`GET/POST/PUT/DELETE /llm-profiles`、`activate` 和 `test`。

所有非公开接口需要登录；`/admin/**` 需要管理员权限。

## 迁移

当前 Alembic head 为 `6102d944c525`（模型与库结构零漂移）。全链 35 个迁移的编年史见 [清理记录-02-migrations.md](清理记录-02-migrations.md)。
