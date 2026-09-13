# 交接 · 收官交付包 + 仓库清理（下一对话执行）

> 本文件是**给下一个对话的交接说明**，由 2026-09-13 的会话写出。
> 使用者给的指令是：**先修完所有未决项 → 打一个新包作为交付 → 做一次项目文件夹与冗余代码清理
> （前提：功能与使用不受损）**，并且**在动手之前必须先用选择题与使用者对齐需求**。
>
> 阅读顺序建议：本文 §1（现状）→ §7（对齐问题，**先问**）→ §2–§4（任务）→ §5（门禁）→ §6（坑）。

---

## 1. 现状（2026-09-13 收盘）

- **仓库**：`/Users/yifengstudio/Documents/GitHub/SummitWorkbench`（私有 `SummitYifeng/SummitWorkbench`），
  `main` 与 `origin/main` 同步、工作树干净。写这份文档时 HEAD = `3ec491b`（请以 `git log -1` 为准）。
- **技术栈**：Python 3.12 + FastAPI 后端；原生 macOS Swift 外壳；Vite + 原生 TypeScript 前端；
  产物为 arm64 `INTERNAL-DEV` DMG。
- **当前交付包**：**build 33**（`0.4.7` / arm64 / `INTERNAL-DEV`，源码 `989ce9c`，
  `frontend_build = v2026.09.13-989ce9c-9517f794`，DMG SHA-256
  `29e3ae3d8b5aeb952200144432bb313e83e11b72be8036f7c9f82afc4cd32a6a`），已装在 Studio。
- **两台机器（真实使用中）**：
  | | Studio（本机） | Air |
  |---|---|---|
  | 工作台 | `bf22c8d2-ef62-4bd3-9917-e76fdd3f7f0f`（`_vault`） | 同一个 |
  | vault 路径 | `~/Documents/Work/_vault` | `~/Documents/Work/_vault` |
  | 角色 | `automation-primary`（device `51885d3d-…`） | `secondary`（device `e1b8b735-…`） |
  | 远端 | `https://github.com/yifeng93/YifengWorkKnowledge.git` | 同 |
  | 状态 | `ready` / ahead-behind `0/0` / 11 项 preflight 全 PASS | `ready` / `0/0` |
  | 包 | build 33 | build 33 |
  - 两台已在真实 vault 上跑通一次**双机往返冒烟**（Air 捕捉「测试」→ Studio 点「⇅ 立即同步」拉到），
    证据见 `docs/acceptance/OPEN-VERIFICATION-ITEMS.md` §Q.6。
- **证据与文档**：
  - `docs/acceptance/OPEN-VERIFICATION-ITEMS.md`：§N（A6/A7 双机现场）、§O（build 29 逐条复核）、
    §P（build 30/31 真机复验 + D9 发现）、§Q（Phase 6 复原 + D10/D11 + 双机冒烟）。**新证据请续 §R。**
  - `docs/acceptance/DUAL-DEVICE-REHEARSAL.md`：双机复跑 runbook；文末「附」逐个记录 D1–D9。
  - `CHANGELOG.md`：`## [Unreleased]` 下按日期分块，记录到 D11 与 Phase 6 收尾。
  - `docs/implementation/LEGACY-MAIN-SPLIT-PLAN.md`：前端拆分计划（已完成，附录 C 有逐步骤提交）。
- **凭据位置（重要）**：内置飞书凭据的**原始出处**是
  `dist/releases-local-v0.4.7-b25/0.4.7/arm64/SummitWorkbench.app/Contents/Resources/feishu-defaults.json`
  （`app_id` / `app_secret` / `redirect_uri`）。该文件**永不入库**（`.gitignore` 有
  `**/feishu-defaults.json`）。日常真实 vault 的 workspace Keychain（`bf22c8d2`）里有
  `llm:shared:shared` 与 `feishu:cli_aa1e751a357b9bd4:refresh_token`。
- **两个演练仓库仍存在**（使用者要求暂留）：`SummitYifeng/summitworkbench-rehearsal`、
  `SummitYifeng/summitworkbench-rehearsal-2`。删：`gh repo delete <repo> --yes`。

---

## 2. 任务 A · 修完未决项（D9 / D10 / G1 / G2 / G3）

> 每条都写清：症状、根因、修法方向、必须的测试与变异验证。**设计与范围要先跟使用者对齐（§7）。**

### A1 · D9：恢复提交后的 push 被误判为非快进（真实缺陷，跨机时钟偏差会踩）

- **位置**：`src/summit_workbench/repositories/dulwich_git.py::DulwichGitBackend.push`（约 650 行）。
- **症状**：冲突恢复成功（`recovery.status = committed`），同一次响应的 `push` 却是
  `diverged-protected` + 「远端已有新提交，需要处理分叉（non-fast-forward）」；而 `git merge-base
  --is-ancestor <remote> HEAD` = YES、系统 git 同一推送**成功**。
- **根因**：dulwich 的 `graph.can_fast_forward()` 用 **commit_time 剪枝**找公共祖先，不是图可达性。
  当远端父提交的 committer time **晚于**本地提交（两台机器时钟偏差；或任何把提交时间写晚的来源），
  从 tip 出发的遍历把整条路径剪掉 ⇒ LCA 找不到 ⇒ `porcelain.DivergedBranches` ⇒ App 归类
  `GitNonFastForward`。注意「恢复提交 + 审计提交」这个两跳组合正好落在坏区（直接子提交不触发）。
- **证据**：`OPEN-VERIFICATION-ITEMS.md` §P.3（含 `can_fast_forward=False` /
  `merge-base=YES` / `DivergedBranches(b'09aebd7…', b'f0a51bc…')` / 系统 git 推送成功的逐条记录）；
  `DUAL-DEVICE-REHEARSAL.md` 附 D9。
- **修法方向**：在 `push()` 捕获 `porcelain.DivergedBranches` 后，用**不依赖时间戳的图可达性**复核
  （从本地 head 沿 parents 走到远端 ref：`Repo.get_walker` / `object_store` 迭代，或自己写 BFS）；
  **只有确认真快进**时，才对该 ref 显式强推一次（注意 `porcelain.push(force=True)` 会作用于所有
  refspec —— 请显式传 `refspecs=["refs/heads/<branch>:refs/heads/<branch>"]`，或直接用低层
  `client.send_pack`），并把「图复核通过」写进状态原因/日志。**绝不无条件 force。**
- **测试**：构造一个 committer time「晚于子提交」的远端父（可直接构造 `Commit` 对象或用
  `do_commit` 的显式时间参数），断言 push 成功且远端 ref 前进；再构造**真分叉**，断言仍是
  `GitNonFastForward`（变异验证：去掉图复核必须让前者失败、后者保持）。

### A2 · D10：「连接已有工作台」把设备角色一律写成 secondary（且无处可改）

- **位置**：`src/summit_workbench/workflows/onboarding.py::connect_workspace()`（约 608 行，
  **没有** `device_role` 形参 ⇒ 落 `_ensure_profile(..., DeviceRole.SECONDARY)`）；
  `src/summit_workbench/repositories/remote_onboarding.py:254`（克隆流程同样写 secondary）。
  对照：`create_workspace()`（onboarding.py 约 451 行）与 `upgrade_workspace()`（约 529 行）
  都收 `device_role`，且为 primary 时会顺带 `claim_automation_primary()`。
- **后果不是显示问题**：`workflows/sync_coordinator.py::automation_gate()`（约 465 行）只在
  `profile.device_role is DeviceRole.AUTOMATION_PRIMARY` 且 claim 设备匹配时返回 `PRIMARY_OK`
  ⇒ **定时自动化在 marker 指定的主设备上不会跑**，而界面又没有改角色的入口。
- **本次绕行**：用 App 自己的写入器改 profile（`load_profile` → `model_copy` → `save_profile`），
  重启后 `automation_gate = primary-ok`（§Q.1）。
- **修法方向**：connect / clone 流程读 vault 里的 `.summit-workbench/automation-primary.json`：
  `marker.device_id == 本机 device_id` ⇒ 建为 `AUTOMATION_PRIMARY`（并按需 claim），否则
  `SECONDARY`。**并且**提供"改角色"的正规入口——见 A3（claim 入口应同时把 profile 的
  `device_role` 更新掉；另需一个降级为 secondary 的路径，否则角色只能升不能降）。
- **测试**：marker 指本机 ⇒ primary；marker 指别的设备 ⇒ secondary；无 marker ⇒ 默认（按现有语义）。
  变异验证：把 marker 判断去掉，两个用例必须分别失败。

### A3 · G1：界面没有 `automation-primary` 的接管入口

- **后端已存在**：`POST /api/sync/primary/claim`（`src/summit_workbench/webapp/routers/sync.py` 约 398 行），
  payload `AutomationPrimaryPayload{device_id, expected_generation?, takeover?}`（`webapp/api.py` 约 377 行）；
  语义见 `src/summit_workbench/repositories/automation_primary.py::claim_automation_primary`：
  同一设备 = **幂等返回**；别的设备且 `takeover=false` ⇒ `primary_already_claimed`；
  `expected_generation` 不匹配 ⇒ `primary_generation_conflict`；`takeover=true` 才接管并**递增 generation**。
- **要做**：在设置页的同步/工作台区块加一处显式入口，显示
  「本机 device id / 当前主设备 id / generation / 本机角色」，提供「**声明/接管主设备**」按钮：
  - 同设备时按钮应说明"已是主设备"（幂等，无副作用）；
  - 别的设备持有主设备时，需要**显式勾选接管**（文案要说清后果：定时自动化会转移到本机、
    generation 递增、需与另一台机器沟通），并把 `expected_generation` 带上；
  - 成功后**同时把 profile 的 `device_role` 更新为 `automation-primary`**（补上 A2 缺的"可改"能力），
    失败按稳定错误码显示（`primary_generation_conflict` / `primary_already_claimed` …）。
- **前端落点**：`web/src/features/settings/*`（`render.ts` / `actions.ts` / `types.ts` / `index.ts`）
  或 `web/src/features/sync/*`；按钮加进 `web/scripts/test-browser-contract.mjs` 的契约锚点，
  渲染与请求体进 `web/scripts/test-settings-render.mjs` 或 `test-sync-render.mjs`。
- **别忘了指南**：`docs/product/WEB_USAGE_GUIDE.md` 改动会被**构建哈希**覆盖
  （`docs/product/WEB_USAGE_GUIDE.md` → `web/src/guide.md`），改完必须跟一个构建提交。

### A4 · G2：界面没有"把已有本地工作台首次发布到新远端"的路径（**范围要先问**）

- **现状**：设置页 remote 区块只做**规范化**：`workflows/remote_normalization.py`
  的 preview/apply 要求**已存在** `origin` + upstream（`preview_remote_normalization` 约 205 行；
  没有 origin ⇒ `remote_missing`；不是 git 仓库 ⇒ `vault_not_a_repository`）。
  向导的 remote 模式只做 **clone**（已有远端 → 本地）。
  ⇒ 本地已存在、远端尚未创建的工作台只能手工 `git init` / `git remote add` / 首次 push。
- **三个可选范围（§7 对齐问题里要让使用者选）**：
  1. **最小**：在设置页把"本工作台还没有远端"变成一个**可执行**的说明块（写清手工步骤、
     复制诊断里给出仓库路径与分支），不改任何写路径；
  2. **中等**：加一个"绑定已有远端"流程（用户自己先在 GitHub 建好仓库）：校验远端为空/可推送 →
     `git remote add origin <https>` → 首次 `push -u`，复用现有 PAT 输入与规范化逻辑；
  3. **完整**：再往前一步，用 PAT 经 GitHub API **创建**私有仓库并发布（复用向导里的远程凭据链，
     `WB_`… 请自行查现有 remote onboarding 代码，不要另造凭据存储）。
- **共同约束**：只走 HTTPS（`require_https_remote`）；凭据只进 workspace Keychain；绝不 force。

### A5 · G3：同步失败不落盘（`src/` 里**完全没有** logging 设施）

- **现状**：`grep -rn "getLogger\|basicConfig\|RotatingFileHandler\|FileHandler" src/summit_workbench`
  **零命中**；`~/Library/Logs/summitworkbench-panel.log` 里只有 Swift launcher 的 JSON 行
  （`component: "launcher"`）。所以"昨晚为什么没同步"只能看内存快照/重启 App。
- **注意**：**不要**把机器日志写进 vault 的 `logs/`（那是**被同步的内容**，会污染工作台、进提交）。
- **三个可选范围（§7 对齐问题里要让使用者选）**：
  1. **独立服务日志**：在 `~/Library/Logs/` 下新增 `summitworkbench-server.log`（JSON 行、单文件
     上限 + 轮转、0600、**只写稳定原因码与计数，绝不写 URL / 主机 / 路径 / 凭据 / 正文**），
     由一个新的小模块（如 `config/logging_setup.py` 或 `observability/`）初始化，同步/推送/拉取
     失败路径各打一行（`reason=credentials-missing` 之类，配合 D3/D11 的稳定码）；
  2. **并入 launcher 同一个文件**：与 Swift 侧约定同一 JSON schema，追加写入
     `summitworkbench-panel.log`（要先确认 launcher 的轮转/截断策略，避免两边互相覆盖）；
  3. **暂不做**，只把这条继续挂在文档里。
- **测试**：日志初始化幂等、单文件上限生效、**断言不出现敏感内容**（用一个含 URL/路径/凭据的
  假异常跑一遍，断言日志文本里没有它们）—— 这与 `scripts/secret_scan.py` 的取向一致。

---

## 3. 任务 B · 打交付包（build 34）

**约定（务必遵守）**：先提交源码（含测试），再跑构建生成静态资源并**单独提交**构建提交
（`build-meta.json` 的 `git_revision` = 产出该资源的源码提交）；**每个提交都带 `[skip ci]`**；
**不要跑 CI**（使用者明确要求）。

1. 源码修复提交（A1–A5 分条提交，各自带测试与变异验证）。
2. 全部门禁（§5）必须绿。
3. 前端资源：`npm --prefix web run build` → `node web/scripts/verify-build.mjs src/summit_workbench/webapp/static`
   → 提交（`build(web): refresh static assets for v<...>`）。
4. 出包（**必须带内置飞书凭据**）：
   ```bash
   cd /Users/yifengstudio/Documents/GitHub/SummitWorkbench
   B25=dist/releases-local-v0.4.7-b25/0.4.7/arm64/SummitWorkbench.app/Contents/Resources/feishu-defaults.json
   export WB_FEISHU_APP_ID=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['app_id'])" "$B25")
   export WB_FEISHU_APP_SECRET=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['app_secret'])" "$B25")
   export WB_FEISHU_REDIRECT_URI=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['redirect_uri'])" "$B25")
   REQUIRE_BUNDLED_FEISHU=true BUILD_NUMBER=34 ARCH=arm64 \
     RELEASE_OUTPUT_DIR=dist/releases-local-v0.4.7-b34 scripts/release-macos.sh
   ```
   - 若 b25 目录已被清理：**先在删之前**把它 `Contents/Resources/feishu-defaults.json` 复制到
     `dist/`（或仓库外）留档；**不要**把它提交进仓库。
   - `REQUIRE_BUNDLED_FEISHU=true` 是硬门：缺凭据就失败，绝不悄悄出一个不能授权飞书的包。
5. 安装与真机核验：
   ```bash
   osascript -e 'quit app "SummitWorkbench"'; sleep 3
   scripts/install-macos-app.sh dist/releases-local-v0.4.7-b34/0.4.7/arm64/SummitWorkbench.app
   ```
   - ⚠️ 该脚本经常打印「✗ App 已安装但服务未在 readiness 窗口内启动」——**它不一定真失败**：
     去读 `~/Library/Application Support/SummitWorkbench/runtime.json` 确认 `frontend_build` 是新包，
     并用下面的配方打接口。
   - 探针配方：`runtime.json` 取 `pid`/`port` → `ps eww -p <pid> | tr ' ' '\n' | grep '^WB_SESSION_TOKEN='`
     → `curl -H "X-WB-Session-Token: $TOKEN" -H "Origin: http://127.0.0.1:<port>" http://127.0.0.1:<port>/api/sync/status`。
   - 关键核验：`/api/sync/status` = `ready` / ahead-behind `0/0`；
     `POST /api/settings/acceptance-preflight` = 11 项全 PASS（含 `automation-role`）；工作树 clean。
6. Air 侧：使用者自行 AirDrop 安装（无法从 Studio 远程操作）。交付说明里要写清。
7. 记录：CHANGELOG 新增日期块 + `OPEN-VERIFICATION-ITEMS.md` 续 §R（DMG SHA-256、`frontend_build`、
   `git_commit`、app SHA-256、真机核验逐条、A1–A5 各自的证据与变异验证结论），提交并推送。

---

## 4. 任务 C · 仓库与冗余代码清理（**前提：功能与使用不受损**）

**铁律**：只做**等价清理**（删文件/删死代码/搬文档），**不改行为**。每一步都要：
改动 → 跑全部门禁（§5）→ 能跑就跑打包冒烟 → 小步提交。**任何一条门禁变红就回退该步。**

### 4.1 本地产物与缓存（不进仓库，纯磁盘清理，最安全）

实测（2026-09-13）：`dist/` 已 **1.6 GB**，其中 `dist/releases-local-v0.4.4*`、
`SummitWorkbench-0.4.6-arm64-INTERNAL-DEV.dmg`、`releases-local-v0.4.7-b25` 等是历史包。
- 保留：**最新交付包**（build 34）+ `b25`（凭据出处；若先复制出 `feishu-defaults.json` 则可删）。
- 删除：其余 `dist/releases-local-*` 与历史 DMG。
- 缓存：`.coverage`、`htmlcov/`、`.mypy_cache/`、`.pytest_cache/`、`.ruff_cache/`、`.hypothesis/`、
  各处 `__pycache__/`、仓库内 `.DS_Store`（`git status --ignored` 可列全）。
- 这些都在 `.gitignore` 里（`dist/`、`build/`、缓存、`.DS_Store`），**不影响仓库内容**。

### 4.2 已入库但已过期/冗余的文档

- `docs/archive/**`（8 个子目录）是历史归档：**默认只整理不删除**；若某文件被别处引用
  （`grep -rn "<文件名>" docs README.md PROJECTDESC.md`），先处理引用再决定。
- `docs/implementation/`（6 个）+ `docs/acceptance/`（6 个）：检查是否有**已被完全取代**的计划
  （例如已完成的拆分计划、`V0-4-4-*` 系列、被新验收文档取代的 runbook）。处理方式二选一：
  （a）移到 `docs/archive/` 并在原处留一行指针；（b）确证无引用后删除。**不要删掉仍被
  README/PROJECTDESC/CHANGELOG/代码注释引用的文档。**
- `CHANGELOG.md` 已 70KB+：可以考虑把 `[Unreleased]` 之前的旧版本段落到
  `docs/archive/CHANGELOG-<version>.md`，但**必须先问使用者**（这是可追溯性资产）。

### 4.3 冗余代码（最需要小心）

- 方法（保守、可验证）：
  1. Python：跑一次 `vulture`（**临时**装或 `uvx`，不要加进 `pyproject.toml` 的依赖）拿候选清单，
     然后对每个候选 `grep -rn "<symbol>"`（含 `tests/`、`scripts/`、`docs/`、`native/`、字符串型
     动态调用如 `getattr` / 反射 / 路由注册）；确认无引用再删。
  2. TypeScript：`tsc --noEmit` 已开严格模式；检查 `web/src/**/index.ts` 的再导出与
     `legacy-main.ts`（前端拆分后的组合根）里是否有拆分遗留的死分支；`web/scripts/*.mjs` 里
     是否有重复的测试脚本。
  3. 配置/脚本：`assets/`、`deploy/`、`prompts/`、`templates/`、`packaging/`、`scripts/` 逐个确认
     仍被构建或运行引用（`grep -rn "<文件名>" scripts native packaging .github pyproject.toml`）。
  4. `.github/workflows/*`：确认仍在用的工作流；**不要**因为"不跑 CI"就删掉工作流定义
     （那是仓库资产，使用者只是本轮不跑）。
- 反例警告（**别做**）：不要为了"看起来干净"去合并/重命名公共模块、不要动
  `src/summit_workbench/repositories/dulwich_git.py`、`workflows/sync_*`、`webapp/routers/*`
  的公开契约（路由、payload 字段名、错误码）—— 这些被契约测试与文档锁定。
- 每删一批就跑：`tsc` + 14 个前端脚本 + `pytest --cov` + `ruff` + `mypy` + `secret_scan`
  +（可选）打包冒烟 `WB_PACKAGED_APP=1 .venv/bin/python -m pytest tests/integration/test_packaged_app.py -q`。

---

## 5. 门禁与命令速查

```bash
cd /Users/yifengstudio/Documents/GitHub/SummitWorkbench
web/node_modules/.bin/tsc --noEmit -p web/tsconfig.json          # 前端类型
npm --prefix web run test:frontend                               # 14 个前端脚本
npm --prefix web run build                                       # 生成 static
node web/scripts/verify-build.mjs src/summit_workbench/webapp/static
.venv/bin/python -m pytest --cov -q                              # 944+ passed，覆盖率门 80%
.venv/bin/ruff check && .venv/bin/ruff format --check
.venv/bin/mypy                                                   # 334 个文件须无问题
.venv/bin/python scripts/secret_scan.py                          # 含 URL 形态的凭据模式
```

- `scripts/release-macos.sh` 内部会重跑上述大部分门禁 + 路由契约 + 打包验证。
- 每次删除/改动都要能回答："哪条测试/契约能证明它没坏？"答不上来就不要删。
- 秘密扫描的正则包含 `https?://[^/\s:@]+:[^@\s]+@` 与 `-----BEGIN … PRIVATE KEY-----` 等：
  写测试用的假凭据要避开这些形状（曾因此让门禁变红）。

---

## 6. 踩过的坑（省时间用）

1. **dulwich 不支持 SSH**：生产后端固定 dulwich（`webapp/context.py::git_backend_kind`），
   `require_https_remote` 会拒绝非 HTTPS —— 但**多值 `remote.origin.url`** 时
   dulwich 读**最后**一条（可能是 HTTPS，于是"预览 HTTPS 转换"报 `old==new` 什么都不改），
   而系统 `git remote -v` 的 fetch 走**第一条**（SSH）。真实 vault 就处于这种混合状态（§Q.2 的"同源观察"）。
   排查时**两边都要看**：`dulwich config.get(...)` vs `git remote -v`。
2. **`install-macos-app.sh` 的 readiness 假失败**：脚本报失败但 App 其实起来了 —— 以
   `runtime.json` + 接口探针为准。
3. **git 分页器**：`git log` 会进 `(END)` 卡住后续命令，脚本里一律 `GIT_PAGER=cat`。
4. **zsh 的 `nomatch`**：`ls -d dir/*` 无匹配会中止命令（bash 不会）；给使用者的命令避免裸 glob
   或加 `setopt nullglob`。
5. **Keychain 账户命名**大小写敏感：`git:<host>:<profile.git_username>`。Studio 是
   `git:github.com:Yifeng93`，Air 修复过程中还留着旧的 `git:github.com:yifeng93`（无害）。
6. **`/api/sync/conflict/recover` 的三条失败路径**都已被 D7 统一到
   `web/src/features/sync/conflict.ts::recoveryFailureMessage()`；改这里要同时照顾
   `selection/validate` 与 `prepare` 两条分支（第一版只修了一条，真机复验当场抓到）。
7. **恢复流程的铁律**：绝不 force/reset/rebase/stash；`.remote` 兄弟文件是 preserve-both 的
   确定性产物，**不可覆盖**（D8 已改为带 revision 短码 `*.remote.<rev7>`）；审计记录 body-free。
8. **不要把机器日志写进 vault**（会被同步、会被提交）。
9. **内置飞书凭据**：仓库里永远不出现 `feishu-defaults.json`；构建靠 `WB_FEISHU_*` 环境变量。
10. **不要跑 CI**；所有提交带 `[skip ci]`（历史上有一次漏了导致跑了一次 CI）。

---

## 7. 开工前必须与使用者对齐的问题（用选择题工具）

> 使用者明确要求：**下一个对话开始行动之前，必须先以选择题形式对齐需求。**
> 建议一次问 6–8 题（可分批），每题给出推荐项 + 取舍说明。至少覆盖：

1. **本轮交付范围**：只修 D9/D10 + G1，还是连 G2（首次发布远端）与 G3（日志设施）一起做？
   （G2/G3 都是**新功能**，工作量与风险明显更大。）
2. **G2 的范围**：① 只给可执行说明（最小）② 绑定已有远端并首次推送（中等，推荐）
   ③ 连 GitHub 建仓一起做（完整）。
3. **G3 的形态**：① 独立 `summitworkbench-server.log`（推荐）② 并入 launcher 同一个
   `summitworkbench-panel.log` ③ 本轮不做。
4. **G1/D10 的接管语义**：接管是否需要"必须显式确认 + 勾选 takeover + 带上 expected_generation"
   （推荐）？是否同时允许**降级**为 secondary（另一台机器要接手时用）？
5. **清理力度**：① 只清磁盘产物与缓存（最安全）② + 归档/删除过期文档 ③ + 删冗余代码
   （推荐：先 ①②，③ 单独一轮并逐批门禁）④ 连 `CHANGELOG.md` 历史版本也拆分归档（需确认）。
6. **交付包与验证**：build 34 是否要包含内置飞书凭据（推荐要，用 b25 那份）；
   出包后是否要**两台机器都装**（Air 需使用者 AirDrop）；
   是否要再跑一次双机往返冒烟（Air 写 → Studio「立即同步」拉）。
7. **演练仓库与历史产物**：`SummitYifeng/summitworkbench-rehearsal{,-2}` 现在删还是继续留？
   `dist/releases-local-v0.4.7-b25` 是保留（作为凭据出处）还是先导出凭据再删？
8. **是否更新对使用者的说明文档**：`README.md` / `PROJECTDESC.md` / `docs/product/WEB_USAGE_GUIDE.md`
   需要同步新增的 G1/G2 界面（注意指南改动会被构建哈希覆盖，必须跟构建提交）。

---

## 8. 完成定义（DoD）

- [ ] D9 / D10 已修，G1（及对齐后确定要做的 G2/G3）已实现；每条都有**行为测试 + 变异验证**。
- [ ] 门禁全绿：`tsc` / 14 个前端脚本 / `pytest --cov` / `ruff` / `ruff format --check` / `mypy` /
      `secret_scan` / `verify-build`。
- [ ] build 34 出包（内置飞书凭据）、装到 Studio、`runtime.json` 与 `/api/sync/status`、
      `acceptance-preflight` 全 PASS；Air 安装步骤写入交付说明。
- [ ] 清理完成且**功能不受损**：清理后重跑全部门禁 + 打包冒烟（能跑就跑）。
- [ ] CHANGELOG + `OPEN-VERIFICATION-ITEMS.md` §R 记录完毕；所有提交 `[skip ci]` 且已推送。
- [ ] 给使用者的交付说明：新包在哪、装了什么、Air 怎么装、本次清理删了什么、还剩哪些已知开放项。
