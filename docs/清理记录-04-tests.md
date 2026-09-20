# 清理记录 · 第四站：tests/

> 2026-09-18 清理。测试套件的审计结论先说：**整体非常健康**——17 个测试文件全部指向现役代码、
> 无跨文件耦合、无僵尸断言、无调试残留。但审计挖出一个**真缺陷**（测试在偷偷调真实 LLM），
> 本站最有价值的工作就是修掉它。验证：`uv run pytest tests/ -q` → **63 passed**。

## 一、修掉的真缺陷：测试在偷偷调外部 LLM

**现象**：`test_ability_understanding.py` 里「创建/更新奇术触发后台解析」两个用例，会在后台
真实调用外部 LLM 生成因果槽位。证据：测试库 `llm_traces` 表躺着 4 条昨天测试跑出来的
`understanding` 真实调用记录（status=ok）——花真金白银、拖慢测试（曾跑到 101 秒）、
LLM 服务一抖测试就挂。

**根因**：这两个用例的 docstring 声称"conftest 已对生成链打默认空槽位桩"——但 conftest 在
UI/后端大重构时被瘦身为 29 行，那个桩丢了，docstring 与现实脱节，没人发现（因为真实 LLM
恰好能用，测试照样绿）。

**修复**：把默认桩恢复到测试文件本地（保持 conftest 瘦身方向）——autouse fixture 对
`build_understanding_chain` 打固定"零相空想"槽位，个别用例的局部 override 照常覆盖它。
修后复验：`llm_traces` 里 understanding 记录只剩两种桩内容，真实调用归零。
**教训**：测试绿不等于测试对；docstring 声称的前提要时不时对账。

## 二、其余清理

| 动作 | 内容 |
|---|---|
| 幽灵字节码 | `tests/__pycache__/` 里 15 个已删测试的 .pyc（test_battles、test_economy、test_friends、test_worlds 等） |
| 零操作占位 | conftest.py 里只有 `yield` 的空 fixture `cleanup_test_db` 及其专属 import |
| 全局污染 | `test_main_static.py` 直接改写 `app.main.INDEX_HTML` 模块全局且从不还原（会污染后续测试）→ 改用 monkeypatch 自动还原 |
| 旧域样本 | 同文件用 `/battles/123` 做"前端路由形态"样本（battle 域已删）→ 换成现役 `/scenarios/123`（回退判定只看形态，行为不变） |
| 过时措辞 | `test_llm_profiles.py` docstring 的"对战链路透传"→"推演链路透传"；`test_ability_understanding.py` 四处"conftest 桩"说法改为指向本文件桩 |

## 三、每个文件在测什么（清理后全景）

| 文件 | 测什么 |
|---|---|
| `conftest.py` | 测试地基：指向独立测试库 `ynfight_test`（每会话重建）、放开限流、注入进程内 LLM 密钥 |
| `test_abilities.py` | 用户奇术增删改查：创建、重名 409、更新、删除、越权 404 |
| `test_ability_pair_cache.py` | 奇术逐对比对的 Redis 缓存：命中免调 LLM、左右顺序无关、Redis 故障/脏数据降级 |
| `test_ability_understanding.py` | 因果槽位：落库、密钥解密失败回退默认模型、创建/更新触发后台生成（本站修复的重点文件） |
| `test_admin.py` | 管理员守卫 403、用户/奇术管理、stats/traffic/llm-traces 端点 |
| `test_auth.py` | 注册登录、refresh 旋转与重用检测（泄露撤销全令牌）、登出吊销 |
| `test_auth_email.py` | 邮箱绑定验证、密码找回/重置、未知邮箱不泄露存在性 |
| `test_creator_assets.py` | 资产私有性（他人 404）、角色绑定规则（须持有、去重保序、上限 4 门） |
| `test_health.py` | 健康检查三态 + 请求 ID 头 + 安全响应头 |
| `test_llm_profiles.py` | LLM 方案全生命周期：CRUD/激活互斥/越权/密钥掩码/RSA 传输→Fernet 落库/连通性测试/模型覆盖 |
| `test_main_static.py` | SPA 静态托管与回退白名单：正常文件、前端路由回退、穿越攻击 404、/api 保持 JSON 404、405 |
| `test_p2_p3.py` | 错误码信封、角色映射、审计留痕、注销/数据导出、保留策略清理、/metrics |
| `test_reliability.py` | LLM 可靠性层：重试后成功、耗尽抛 ChainFailure |
| `test_scenario_domain.py` | 小天下集 HTTP 全链路：发布/阵容/挑战、作者试炼不计统计、行动异步、详情按观看者裁剪、slug 防撞 |
| `test_scenario_event_scope.py` | SSE 职责：上帝视角遮挡（明文不出站）、按侧别投递、看破门控、越权 404 |
| `test_scenario_guess_assistance.py` | 猜词公开视图脱敏（缺口不出站）、原子×奇术全组合配对的流式回调 |
| `test_scenario_recovery.py` | 启动自愈：只清超龄僵尸挑战，不误杀新挑战/终态 |
| `test_scenario_stream.py` | SSE 事件总线：侧别过滤、跨实例 relay、本源不回环（依赖真实 Redis，不可达自动跳过） |

## 四、记录在案但未动的事项

1. **重复的测试辅助函数**：提权 SQL `_promote` 三份逐字相同、九个"注册+登录拿 token"变体、两份相同的建表 fixture——可下沉 conftest，但这是重构不是清理，且会加大与用户未提交改动的冲突面，留待将来。
2. **共享测试库无逐用例隔离**：各测试靠 uuid4 用户名避碰，属既定设计（每会话重建一次库）。
3. **弱真值断言**（如 `assert refresh1`）均有意图注释说明目的，非僵尸断言。
4. `test_auth.py` 里 `assert "rank_points" not in body` 这类**否定断言**是"防已删字段回魂"的有意设计，保留。

## 五、验证

`uv run pytest tests/ -q` → **63 passed**；`llm_traces` 实证 understanding 真实调用归零。
