# 清理记录 · 第五站：tmp/

> 2026-09-18 清理。本站定性：`tmp/` 是 9 月 11 日 UI 改版验收时的**一次性实验阵地**，
> 不是项目的一部分。处置原则：工具与截图按你的决定保留，626MB 的浏览器会话残留经确认后删除。
> 验证方式：`git status` 对 tmp/ 静默（不再污染版本控制视野）。

## 一、这里原来是什么

9 月 11 日改版验收时的自动化工具链，各部分如下（清理后状态）：

| 内容 | 是什么 | 处置 |
|---|---|---|
| `shot.mjs` | CDP 截图助手：通过调试端口 9222 指挥浏览器逐页截图（先登录再截） | **保留**——下次改版验收可复用 |
| `probe.mjs` `sweep.mjs` `lookimg*.mjs` `grabimg.mjs` | 同族探针/巡检/取图脚本 | **保留** |
| `fishlab.mjs` + `fish-lab.html` | 动画实验页（offset-path 循游与摆尾的证明材料） | **保留** |
| `shots/`（3.6MB） | 当时各页面的验收截图（admin/creator/roster/detail/fish-lab） | **保留** |
| `ref/last.png` | 参考截图 | **保留** |
| `edge-profile/`（626MB） | 那次启动的独立 Edge 浏览器的**用户资料目录**：含登录会话（cookies）、历史、组件缓存 | **已确认删除**——纯会话残留，无复用价值，且含敏感数据 |

**防误提交**：`tmp/` 原先不在 .gitignore 里，一直以未跟踪状态污染 `git status`；最危险的是
`edge-profile/` 里的登录会话——一次 `git add -A` 就会把 cookies 提交进仓库历史。现已将
`tmp/` 加入 `.gitignore`，从此对版本控制彻底静默。

## 二、edge-profile 删除实录（已了结）

`edge-profile/` 的删除一度被**还活着的浏览器进程**锁住（Cookies/History/lockfile 报
"Device or resource busy"），第一天只删掉了 626MB 中的大部分。原因与收尾：Edge 的
"启动加速"特性让浏览器在窗口全关后仍驻留 43 个后台进程，正是它们握着文件句柄；
结束这些后台进程后删除一次成功。最终状态：**目录已不存在，tmp/ 体积 630MB → 3.8MB**。

**防误提交**：`tmp/` 原先不在 .gitignore 里，一直以未跟踪状态污染 `git status`；最危险的
是 `edge-profile/` 里的登录会话——一次 `git add -A` 就会把 cookies 提交进仓库历史。现已将
`tmp/` 加入 `.gitignore`，从此对版本控制彻底静默。

## 三、验证

- `git check-ignore -v tmp/` → 命中 `.gitignore:71` 的 `tmp/` 规则
- `git status` 对 tmp/ 零输出
- 保留物清点：7 个脚本 + fish-lab.html + shots/ + ref/ 全部在位

## 四、追记（2026-09-20）：根目录 data/ 的最终处置

后续排查中确认根 `data/` 整体属于历史遗留，已一并处理：

- `data/llm_profile_keys.json`（8/14 的死钥匙，现行代码从不读取）→ 删除；现行密钥已迁入 `.env`（`LLM_PROFILE_PRIVATE_KEY` / `LLM_PROFILE_STORAGE_KEY`，私钥以裸 base64 单行存储，`profile_crypto` 自动还原 PEM）。
- `data/battles/`（旧对战行迹 md，域已删）→ 删除。
- `data/logs/` → **日志独立到根目录 `logs/`**（`logger.py` 落盘路径同步修改）；运行中的旧后端进程锁着文件，经停服清理后按 dev.bat 原命令重启，现役后端已按新路径写日志（`logs/app-77292.log`），`data/` 目录不复存在。
- `.gitignore` 的 `data/` 规则替换为 `logs/` + `/app/data/`（后者兜底：无 `.env` 密钥时的自动落盘场景）。
