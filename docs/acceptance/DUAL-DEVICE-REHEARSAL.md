# 双机现场复跑（A6 / A7）

> 本文件是 [`OPEN-VERIFICATION-ITEMS.md`](OPEN-VERIFICATION-ITEMS.md) 中 **A6**（双设备冲突恢复）
> 与 **A7**（第二台机器的向导接入）的**可执行复跑步骤**。两项都必须由**人在两台真实机器上**执行，
> 自动化只能覆盖代码路径。
>
> **先读 §1**：A6 的完整流程**已经在 build 29 上双机验收通过**，所以它不是"从没做过"，
> 而是"结论要重新锚定到当前 build"。§1 把"当前 build 到底改了什么"量了出来，
> §A6 据此把复跑缩减成 **10 分钟的差异点抽查**；只有想完整重跑时才走 §A6.3 的原始 runbook。
>
> 复跑完请把证据按「已关闭」的格式登记回 `OPEN-VERIFICATION-ITEMS.md`，并注明提交/日期。

## 1 · 已经做过的双机轮次，与当前 build 的差异

**已做过的（都有记录，不要重复劳动）**

| 轮次 | build / 源码 | 覆盖内容 | 证据 |
| --- | --- | --- | --- |
| P1-07D | build 23 / `0.4.3` | remote preview/apply、schema 迁移、preflight 全 PASS、Studio↔Air 双向同步、Air 离线写入恢复、双端离线分歧进入 `diverged-protected` | `CHANGELOG.md` `[0.4.3]`、ADR 0041 |
| 覆盖安装冒烟 | build 24 / `0.4.3` | 两台设备覆盖安装与增量冒烟、secondary profile、零写入 | `CHANGELOG.md` `[0.4.3]` |
| **P2-02（= A6 本体）** | **build 29 / `697c239`** | 冲突详情、人工选择、`preserve-both`、临时预检、显式确认、双父提交 `c95b6c1`/`af662d5`、脱敏审计 `8a6a543`/`ec00260`、`conflict_snapshot_stale`、`current_worktree_dirty`、审计失败分支、普通 push、Studio 快进同 HEAD、双方 clean `0/0` | [`../archive/acceptance/P2-02-BUILD-25-STUDIO-AIR-RUNBOOK.md`](../archive/acceptance/P2-02-BUILD-25-STUDIO-AIR-RUNBOOK.md)、ADR 0043 |
| 分发版单机 | build 21 / `v0.4.7` | 从未安装过的 Mac：装包 → 飞书授权 → DeepSeek → 简报 | `CHANGELOG.md` `[0.4.7]` |

**从 build 29 到当前 HEAD，同步/冲突这条路上实际改了什么（已实测）**

| 层 | 结论 | 依据 |
| --- | --- | --- |
| 后端冲突恢复语义 | **没变**。`sync_coordinator.py`、`repositories/git.py`、`git_backend.py`、`config/git_credentials.py` 自 `697c239` 起**零提交** | `git log 697c239..HEAD -- <这些文件>` 为空 |
| 同步 API 契约 | **没变**。11 条 `/api/sync/*` 在 `docs/contracts/web-route-contract.json` 里**逐字节相同**（该契约由 `inspect.getsource` 抽取路由与错误码）；期间只**新增** 9 条无关路由，无删除、无变更 | 对比两个 revision 的契约快照 |
| 同步 API 实现 | 只搬了位置：`legacy_app.py` → `routers/sync.py`（+455 行，Step 6/16 机械外迁，`[skip ci]`，逐步对比特字节相同） | 后端拆分各步提交 |
| 前端冲突弹层 | 只搬了位置：`legacy-main.ts` → `features/sync/{conflict,banner,labels,state}.ts`（Step 1/6），逻辑行逐行对比特一致 | Step 1/6 提交 |
| 前端**唯一**用户可见变化 | `ee561f5` 给同步横幅加了**读取失败不静默隐藏**：`/api/sync/status` 失败时保留上次成功读取的保护态（含「查看冲突详情」入口），显示「同步状态读取失败…（上方为上次成功读取的状态）」+「重新读取」；轮询改为仅可见时进行 | `ee561f5` diff |

⇒ **A6 的复跑重点就是最后那一行**（新保护态在真机上的表现），加一条端到端闭环确认整体没退化。

## 0 · 前置与铁律

- 两台 Mac：**Studio**（已有工作台）与 **Air**（第二台，装同一个 App）。**两台装同一个 DMG**
  （必须是从当前源码新构建的，见 §0.1——历史 DMG 里没有「从另一台 Mac 克隆」这段代码）。
- 一个**专用演练仓库**（GitHub 私有，例如 `summitworkbench-rehearsal`）+ 一个有 `repo` 权限的 PAT。
- 铁律（来自 [`UI-VERIFICATION-FINAL-PROMPT.md`](UI-VERIFICATION-FINAL-PROMPT.md) §0）：

  1. **Web 写操作会自动 commit 并 push**，而远端历史**不能**用本地 `reset` 收回（产品绝不 force-push）。
     ⇒ 演练**不要用真实工作区的远端**，一律用专用演练仓库。
  2. **`HOME` 隔离会切断 Keychain**。⇒ 演练全程用真实 `HOME`，只把工作区目录指向 `~/Documents/Rehearsal`。
  3. 演练用的工作区是**新建的空工作台**，跑完删掉即可，真实 vault 全程不参与。

### 0.1 为什么要"制造空安装"，以及怎么做

「从另一台 Mac 克隆」和「新建我的工作台」都**只在空安装的向导里**：完整 app 里从设置页重开的
向导会把步骤钉在「AI 模型」（`state.step = Math.max(fullApp ? 1 : 0, …)`），**没有选择/创建工作区
那一步**。所以两台机器都要先把本机 profile 收起来，制造一次真正的空安装。

做法（**改名，不要删** —— 这就是整场演练的还原路径）：

```sh
# 退出 App 后
cd ~/Library/Application\ Support
mv SummitWorkbench SummitWorkbench.real-bak     # 真实工作台注册表被"收起来"
```

App 是否进入空安装只取决于这个注册表（`resolve_workspace()` 只看 active profile；生产模式不允许
`WORK_ROOT` 回退），所以改完名打开 App 就是连接向导。**真实 vault（如 `~/Documents/Work`）和
Keychain 都不动。**

收尾时按 §收尾 反向改回来即可，相当于整场演练可一键回滚。

### 0.2 演练仓库与目录约定

- 新建工作台时向导问的是 **Work 文件夹**（`work_root`），vault 会是 `<work_root>/_vault`。
- 克隆时向导问的是**目标文件夹**，它要的就是 **vault 目录**本身。
  ⇒ 两台机器统一用：Studio 建 `~/Documents/Rehearsal`（vault = `~/Documents/Rehearsal/_vault`），
  Air 克隆目标填 `~/Documents/Rehearsal/_vault`（该路径在 Air 上必须**尚不存在**）。

## A7 · 第二台机器接入（向导「从另一台 Mac 克隆」）

**在 Studio 上准备演练仓库**（先按 §0.1 把 Studio 造成空安装）

1. 装新 DMG → 打开 App → 应直接进**连接向导**第 1 步「选择工作区」。
   确认四个选项都在：「新建我的工作台 / 连接已有工作台 / 升级这台 Mac 上的旧工作台 /
   **从另一台 Mac 克隆**」（最后一个是本轮新加的，只有空安装才有）。
2. 选「**新建我的工作台**」，路径填 `~/Documents/Rehearsal`，模型与飞书都点「跳过」，走到完成。
3. 在 GitHub 新建一个**空**私有仓库 `summitworkbench-rehearsal`（保持空，第一次 push 由本地完成）。
4. **先手工把 vault 变成 git 仓库并推一次**（**必需**，原因见本节末尾的「已知缺口」）：
   ```sh
   cd ~/Documents/Rehearsal/_vault
   git init -b main
   git add -A && git commit -m "演练：初始提交"
   git remote add origin https://github.com/<you>/summitworkbench-rehearsal.git
   git -c credential.helper= push -u origin main
   ```
   `-c credential.helper=` 只对这一次命令关闭钥匙串助手：git 会**在终端提示符里**问用户名与密码，
   用户名填 GitHub 登录名、密码粘 PAT。这样 PAT 不进命令行、不进 shell 历史，也**不会覆盖**你日常
   推送在用的那个 `github.com` 钥匙串条目（它可能是限定仓库的令牌）。
5. 现在 origin 与 upstream 都有了，回到 App：设置 → **高级与维护** → **Git 同步** →
   填**同一个** HTTPS 地址 + GitHub 用户名 + PAT → 点「**预览 HTTPS 转换**」→ 通过后点
   「**确认并转换**」。这一步才会把 **workspace 级**凭据写进 Keychain，App 之后才能自己 fetch/push。
6. 回到「今日」页捕捉 `演练-A` —— 现在它才会真的产生 `wb:` 提交并由 App 推送。
7. 核对：`git -C ~/Documents/Rehearsal/_vault log --oneline -3` 有提交，
   且远端有 workspace marker（`git -C ~/Documents/Rehearsal/_vault ls-files | grep ".summit-workbench/workspace.json"`）。
8. **Studio 就停在演练工作台上**，先别还原真实 profile（A6.1 需要它作为另一侧）。

> **已知缺口 D1（2026-09-13 实测发现，待排期；完整清单见文末「附 · 本次复跑发现的产品缺陷」）**：「新建我的工作台」**不会 `git init`**
> （`workflows/onboarding.py` 明确写着"全程不运行系统 git、不 `git init`"），而
> `preview_remote_normalization()` 一上来就 `GitRepo(vault_dir)` 并要求已有
> `origin` + `upstream`。两者合起来的效果是：**新工作台无法只靠界面接上远端**——新建后直接点
> 「预览 HTTPS 转换」会得到 `ApiError: 服务内部错误 [internal_error]`，日志里是
> `GitError: 不是 git 仓库：…/_vault`。上面第 4 步就是绕开它的手工引导。
>
> 同一根因还有第二个可见后果：在新工作台里「系统写回自动 git 留痕」在成为 git 仓库之前是
> **静默不生效**的（`commit_paths()` 返回 `NOT_GIT`，界面不报错）。⇒ 需要两处修：
> create-new 初始化仓库（或明确提示"本工作台尚未纳入版本管理"），以及预览失败时返回稳定错误码
> 而不是 500。另注：该预览在 `upstream` 缺失时会返回 `upstream_missing`，即它本质上是
> **同一仓库的 SSH→HTTPS 规范化**，不是"把新工作台发布到新远端"。

**在 Air 上走新旅程（这就是 A7 的证据）**（先按 §0.1 把 Air 造成空安装）

9. 装**同一个** DMG → 打开 App → 连接向导 → 选「**从另一台 Mac 克隆**」。
10. 填四项并点「**连接并检查**」：
   - 私有 HTTPS 仓库地址：`https://github.com/<you>/summitworkbench-rehearsal.git`
   - 目标文件夹：`~/Documents/Rehearsal/_vault`（Air 上**必须还不存在**）
   - GitHub 用户名、访问令牌（PAT）——**PAT 由本人粘贴，不进终端参数、截图、诊断包或聊天**
11. **期望**：短暂等待后出现确认块，显示 **工作区短码**、**兼容性**（应为 ok）、**远端地址**。
    此时 Air 上只有暂存目录（`~/Documents/Rehearsal/.summit-workbench-remote-*`），
    **还没有** `_vault`。
12. 点「**确认并开始使用**」→ 模型/飞书都跳过 → 进入工作台。

> **2026-09-13 实测修复**：这条旅程第一次在 Air 上跑时，点「连接并检查」直接 409
> `workspace_id_required`（"私有 remote clone 需要预期 workspace id 才能读取作用域凭据"）——
> 空安装向导拿不到 workspace id（它由远端 marker 决定），而它总是显式带上本次的 PAT，
> 不存在按作用域查 Keychain 的动作。已在提交 `94e5819` 修掉（守卫改为只在既没有 backend
> factory 也没有显式 resolver 时才要求 id），对应产物为 **build 27**。教训记一笔：原来的
> HTTP 测试把 `stage_remote_clone` 整个 stub 掉了，于是守卫/marker/兼容性/确认落盘全都没走到；
> 现在只假造网络 clone，其余走真实代码，并在变异验证下能复现那个 409。
>
> **同一意图的第二层（build 28）**：b27 之后重试，报的是兜底句「远端 clone 失败，请检查凭据、
> 网络或 TLS」。真因在更下面一层——`DulwichGitBackend.transport_kwargs()` 无条件要求非空
> `workspace_id`，早于它检查注入进来的 `credential_resolver`，于是向导的每次 clone 都抛
> `GitCredentialsUnavailable`；而 `stage_remote_clone()` 没有映射这一类，它落进兜底、原因消失。
> 已在 `2b534e0` 修（只在没有注入 resolver 时才要求作用域 id），并加了稳定码与
> `details.reasons` 透传。**要跑这条旅程请用 build 28 或更高。** 详见文末 D4。

**A7 通过标准（逐条留证）**

> 注意：设置页的「工作台切换」**不显示设备角色**（只显示路径、同步状态与连接状态），
> 所以角色要用下面第 1 条的命令从本机 profile 读，不要凭界面判断。

1. Air 的本机 profile 是 **secondary**，且回填了远端与用户名（`profiles/<workspace_id>/config.toml`）：
   ```sh
   grep -E "workspace_id|device_role|git_username|git_remote_url" \
     ~/Library/Application\ Support/SummitWorkbench/profiles/*/config.toml
   ```
   期望 `device_role = "secondary"`，`git_remote_url` 就是那个 HTTPS 仓库。
   同时界面「工作台切换」里能看到该工作台、徽标为它的工作区短码。
2. Air 的 vault 里能看到 Studio 第 5 步捕捉的内容（克隆真的带过来了；本例实际输入为 `测试的`）。
3. Air 的 Keychain 里有该 workspace 的 Git 凭据，且**值是那份 PAT**：
   ```sh
   security find-generic-password \
     -s com.summitworkbench.credentials.<workspace_id> \
     -a git:github.com:<user> -w | head -c 12
   ```
   （或打开「钥匙串访问」搜 `SummitWorkbench`。）注意：这一步会**打印 PAT 前缀**，
   不要把终端输出贴进任何记录。
4. `onboarding-draft.json` 已清理，或其中**没有 `pat`**：
   ```sh
   ls ~/Library/Application\ Support/SummitWorkbench/onboarding-draft.json 2>/dev/null || echo "已清理（期望）"
   ```
5. 演练仓库的任意提交里**不含** PAT：
   ```sh
   git -C ~/Documents/Rehearsal/_vault log -p | grep -c github_pat_   # 期望 0
   ```

## A6 · 双机分叉与冲突恢复

两台机器都已连上**同一个演练工作台**（A7 完成即满足）。顺序不能乱。

### A6.1 差异点抽查（推荐，约 10 分钟）

按 §1，后端与契约自 build 29 起逐字节未变，前端只有一处新保护态。所以先做这三步就够：

1. **新的保护态（`ee561f5`，本 build 唯一新行为）**：在 Air 上让 `/api/sync/status` 失败一次
   —— 最简单是**关掉 Wi-Fi**（或让本地服务暂时不可达），然后等一次自动刷新或点「重新读取」。
   - 预期：横幅**不消失**，保留上次成功读取的同步状态（若此前是保护态，则**仍保留**
     「查看冲突详情」按钮），并多出一行「同步状态读取失败：…（上方为上次成功读取的状态）」
     与「重新读取」按钮。
   - 对照旧行为：之前读取失败会**静默隐藏**横幅——这正是这次要确认改变的。
   - 恢复网络后点「重新读取」，预期错误行消失、状态回到实时值。
2. **一条闭环（确认整体没退化）**：走下面 A6.2 的第 1–6 步（Air 离线捕捉 → Studio 捕捉并 push →
   Air 重试进入 `diverged-protected` → 详情 → 选择 → 临时预检 → 确认恢复）。
3. **收敛与对端**：确认双父提交、普通 push 成功、Studio fast-forward 到同一 HEAD、
   两边 clean 且 ahead/behind `0/0`。

**抽查通过标准**

- [ ] `/api/sync/status` 失败时横幅保留保护态并可「重新读取」（新行为），不再静默隐藏。
- [ ] `git rev-list --parents -n1 HEAD` 在 Air 上有**两个父提交**。
- [ ] 两侧内容都在，按第 5 步的选择落地。
- [ ] 恢复后 push 成功；Studio 下次同步是 **fast-forward**。
- [ ] 双方最终同一 HEAD、工作树 clean、ahead/behind `0/0`。

### A6.2 完整闭环步骤

1. **Air 断网**（关 Wi-Fi）。在「今日」页捕捉一条 `离线-B`。
   预期：本地已提交、推送失败 → 顶部同步横幅显示**待推送 ≥ 1**（`local-ahead`），内容不丢。
2. **Studio 联网**。捕捉一条 `离线-A` → 自动 commit + push 成功。
3. **Air 恢复联网**，点同步横幅的「**立即重试**」。
   预期：进入**保护态**，状态为 `diverged-protected`，横幅上出现「**查看冲突详情**」按钮；
   Air 的本地提交**没有被改写**，`离线-B` 仍在。
4. Air 点「**查看冲突详情**」。弹层标题「同步冲突详情」，应显示：
   - 三个 revision：**共同基线 / 本机 / 远端**（各 12 位短码）
   - 「自动处理 N 项 · 需要选择 M 项」，并列出分叉文件（本次应有 `离线-A` 与 `离线-B` 两侧的内容）
   - 明确写出**不展示正文、确认前不修改 vault**
5. 对每个需要选择的文件选「**保留本机**」或「**采用远端**」→ 点「**临时预检（不写入）**」。
   预期：显示「**临时预检通过**」及事件数/聚合数/候选文件数；此时点「**确认恢复并创建提交**」才可用。
6. 点「**确认恢复并创建提交**」。
   预期：创建**普通本地双父提交**并尝试普通同步（不 force-push / 不 reset / 不 rebase / 不 stash）。

**A6 通过标准（完整版，逐条留证）**

- [ ] Air 的 vault 里 `git rev-list --parents -n1 HEAD` 输出有**两个父提交**。
- [ ] 两侧内容都在（`离线-A` 与 `离线-B` 对应的文件都存在，按第 5 步的选择保持一致）。
- [ ] 审计记录为 body-free 且状态 committed（弹层/诊断里可见）。
- [ ] 恢复后的推送成功；**Studio** 下次同步是 **fast-forward**（Studio 侧无需再次解决冲突）。
- [ ] 若远端在恢复前又变了：Air 应**回到保护态**而不是硬覆盖 —— 这是正确的失败方式，记录截图即可。

### A6.3 完整重跑（可选）

想按 build 29 的口径完整重来一遍（含未知视图/二进制 `preserve-both`、`conflict_snapshot_stale`、
`current_worktree_dirty`、审计失败分支），直接用原始 runbook 的 §2 流程：
[`../archive/acceptance/P2-02-BUILD-25-STUDIO-AIR-RUNBOOK.md`](../archive/acceptance/P2-02-BUILD-25-STUDIO-AIR-RUNBOOK.md)。
本文件不复制它，避免两份清单漂移。

## 收尾

因为两台机器都是按 §0.1 用"改名"制造的空安装，收尾也用改名法——**整场演练可一键回滚**：

1. 两台机器都退出 App。
2. 删掉演练产生的 Application Support 目录（现在名字就叫 `SummitWorkbench`），
   把 `SummitWorkbench.real-bak` **改回** `SummitWorkbench`。
3. 打开 App → 应回到你**真实**的工作台（工作台列表里是原来那些）。
4. 两台都删掉 `~/Documents/Rehearsal`；删除 GitHub 上的演练仓库。

> 如果演练中想让某台机器就地"下车"而不整体还原，也可以用新按钮：设置 →
> 高级与维护 → 工作台切换 → 「**移除此 Mac 上的工作台**」（只删本机 profile/runtime/草稿，
> vault、远端与 Keychain 都不动；移除当前工作台后需重启才生效）。

5. 在 `OPEN-VERIFICATION-ITEMS.md` 里登记：**A7** 移入「已关闭」；**A6** 若只做了 §A6.1 抽查，
   把 A6 一行改写为"已在 build 29 完整验收 + 已在本 build 抽查通过"，并写明本 build 的
   `frontend_build`（`build-meta.json` 或设置页版本状态条）、日期与逐条证据；若走了 §A6.3
   完整重跑，按完整口径关闭。

## 附 · 本次复跑发现的产品缺陷（9 个：D1–D8 **已修**，D9 待修）

> 修复提交：D1 `98fcd84` / D2 `95cc848` / D3 `b5d4a2b` / D4 `2b534e0` / D5 `d2b07bd` / D6 `9ce7205` /
> D7 `fd19603` / D8 `fd19603`。产物：build 28（D4）、**build 29**（D1/D2/D3/D5/D6）、
> **build 30**（D7/D8，已真机复验通过，见文末与 `OPEN-VERIFICATION-ITEMS.md` §P）。
> D9 是 build 30 复验时新发现的，尚未修复。
> 下文的根因分析与修法方向保留原样，作为这些改动的依据与回归锚点。

2026-09-13 在 Studio 上按本流程实际执行时逐个撞上，全部**用户可复现**，且都在"首次把一台机器接到
远端"的必经路径上。修法方向一并记下，等排期。

### D1 · 「新建我的工作台」不初始化 git 仓库

- **证据**：`workflows/onboarding.py` 明确写着"全程不运行系统 git、不 `git init`"；全仓 `src/` 里
  **没有任何 `repo.init()` 调用点**；新建出来的 vault 只有 `.summit-workbench/`，没有 `.git`。
- **症状一**：在新工作台上直接点「预览 HTTPS 转换」→ `ApiError: 服务内部错误 [internal_error]`，
  日志是 `GitError: 不是 git 仓库：…/Rehearsal/_vault`
  （`routers/settings.py:825 → workflows/remote_normalization.py:217 → repositories/git.py:98 →
  repositories/dulwich_git.py:183`）。而该接口第一行就要求已有 `origin` + `upstream`。
- **症状二（同因，更隐蔽）**：`repositories/autocommit.py::commit_paths()` 直接返回 `NOT_GIT`，
  界面不报错 ⇒ **「系统写回会自动 git 留痕」在新工作台上静默不生效**。
- **修法**：create-new 初始化仓库（让新工作台天然纳入版本管理），或至少在界面上明确显示"本工作台
  尚未纳入版本管理"；同时让预览在拿不到仓库时返回稳定错误码而不是 500。
- **绕过**（本流程 §A7 第 4 步）：手工 `git init` + 首次提交 + `git remote add`，再用
  `git -c credential.helper= push -u origin main` 把 PAT 输在 git 自己的提示符里（不进命令行、
  不进 shell 历史、不覆盖通用 `github.com` 钥匙串条目）。

### D2 · 「确认并转换」后运行中的服务仍使用启动时的 profile 快照

- **证据链**：App 服务启动于 `2026-09-12T22:56:48Z`；「确认并转换」把 `git_username` 写进 profile 是在
  `23:11:08Z`（**晚 15 分钟**）。Keychain 里只有 `git:github.com:Yifeng93`，查 `git:github.com:`（空用户名）
  **未命中**。`webapp/context.py` 的 `WebContext.active_workspace` 在启动时冻结，而
  `sync_workspace(context=ctx.active_workspace)` 正是从它取 `git_username`。
- **症状**：转换成功并提示"转换完成"，但**同一进程内**点「立即重试」**必然** `error`；**重启 App 后立刻
  `ready`**（实测 `/api/sync/status`：`_vault:ready`、ahead/behind `0/0`、`last_sync_at=23:18:18Z`）。
- **修法**：转换成功后刷新内存里的 active workspace context；或让同步从磁盘 profile 读 `git_username`，
  不要用启动快照。
- **影响面**：这是"先转换 remote、再重试同步"的标准首次配置顺序，不是边缘情况。

### D3 · 同步失败原因被完全吞掉（不可诊断）

- **证据**：`domain/sync.py::classify_repo_error()` 对 `GitCredentialsUnavailable` **没有分支**，落到
  裸 `SyncState.ERROR`；持久化的 `sync-state.json` 里 `detail` 为空、`repo_states` 只有 `_vault:error`；
  `~/Library/Logs/summitworkbench-panel.log` 里**只有 `"component":"launcher"` 记录**，没有任何
  `warn`/`error`；`/api/sync/run` 也只回状态枚举。最终定位只能靠把同步器拉到进程内复现。
- **修法**：每个失败类别给一个稳定错误码 + 脱敏原因，写进 `sync-state.json`、banner 的 `detail` 与
  结构化日志；`GitCredentialsUnavailable` 至少要有独立码（如 `credentials-missing`）。
- **代价**：D2 的排查因为这一条多花了好几轮——三个缺陷叠在一起时，"没有错误信息"本身就是最大的缺陷。

### D4 · 私有 clone 的失败原因被兜底吞掉（本轮因它多花数轮）

- **本层根因（b27 之后暴露）**：`DulwichGitBackend.transport_kwargs()` 在 HTTPS 下**无条件**
  要求非空 `workspace_id`（`if not self._workspace_id or not self._username: raise
  GitCredentialsUnavailable(...)`），而这行在它使用注入的 `credential_resolver` **之前**。空安装
  向导按设计没有 workspace id（由远端 marker 决定），于是每次 clone 都抛
  `GitCredentialsUnavailable`；`stage_remote_clone()` 的映射表里既没有它、也没有 `GitProxyError`，
  两者都落进 `except Exception` 的兜底句「远端 clone 失败，请检查凭据、网络或 TLS」。
- **真机表现**：Air 上 `git ls-remote`（含 PAT）成功、`curl` 直连与**走 127.0.0.1:7890 代理**都通
  （`github` 404 / `api` 200），唯独 App 只给三选一的猜测——因为 curl/git 不读 macOS 系统代理，
  而 App 一定走它（`config/network_proxy.py`），故障域与提示完全对不上。
- **已修**（`2b534e0` / build 28）：`transport_kwargs()` 只在**没有注入 resolver** 时才要求
  作用域 id；`stage_remote_clone()` 为凭据与代理各加稳定码
  （`remote_credentials_unavailable` / `remote_proxy_failed`），兜底也带异常类名；
  向导现在把 `details.reasons` 一并显示。
- **教训**：b27 与 b28 是**同一意图在两层各写了一次检查**，第一次只修了上层（`stage_remote_clone`），
  下层（`transport_kwargs`）把上层放行的情况又拦了一次。功能测试覆盖不到这种"两层同名守卫"，
  所以这次补的是**针对该层**的单元测试 + 变异验证（恢复旧守卫能复现真机异常原文）。

### D5 · 向导草稿收尾不干净（低危，含一处路径未规范化）

- **证据**：`onboarding_view.py` 里**没有任何 `method:'DELETE'`**（`grep -c` = 0）；
  `/api/onboarding/remote/confirm` 成功后确实清了草稿，但紧接着向导的 `persist()` 又把它写回去，
  走到「设置完成」/「进入工作台」也不清。实测 Air 完成接入后草稿仍在，内容为
  `step: "done"`、`flow: "connect-existing"`、`git_mode: "remote"`、`remote_url`、`git_username`
  ——**无任何秘密**（`grep -c github_pat` = 0，字段白名单由 `OnboardingDraft` 的 `extra="forbid"` 保证）。
- **影响**：同一台机器**下次**出现空安装时，`restore()` 会从 `step:'done'` 恢复，向导直接停在
  「设置完成」而不是第 1 步「选择工作区」（可点「上一步」退回，但很困惑）。
- **同处第二个瑕疵**：草稿里的 `vault_dir` 存的是**未展开**的 `~/Documents/Rehearsal/_vault`，而
  `work_root` 是展开后的绝对路径（后端 `expanduser()` 过）。目前只有向导自己把它当表单默认值读，
  所以只是数据卫生问题；一旦将来有别的消费者按路径使用它，`Path("~/…").is_dir()` 会是 False。
- **修法**：进入工作台时显式清一次草稿（或让后端在 confirm 后标记完成、`persist()` 不再写回）；
  向导持久化前对路径做 `expanduser()` 规范化。

### D6 · 干净工作区没有任何"主动拉取"入口（影响日常多设备使用）

- **证据**：全仓只有 `/api/sync/run` 会调用 `sync_coordinator.sync_workspace()`（`grep -rn
  "sync_workspace(" src/summit_workbench/webapp/routers/` 只有 `routers/sync.py:445` 一处）；而
  `/api/sync/run` 在前端**只由同步横幅的「立即重试」按钮触发**，横幅在状态 `ready` 时是**隐藏**的
  （`banner.ts`：`shouldShow = state !== 'ready' && state !== 'unconfigured'`）。60 秒轮询只调
  `refreshSyncBanner()`（读 `/api/sync/status`，即**内存快照**）与 `checkVersion`；
  `GET /api/state` 等读路径**完全不 fetch**。写路径用的是 `push_after_commit()`（**只 push、不 fetch**）。
- **实测后果**：Air 恢复成功并 push 后，Studio 处于"干净且 ready"，**界面上没有任何按钮能拉取**——
  本轮是直接调 `POST /api/sync/run`（与按钮同一端点）才完成快进的。对日常使用意味着：
  1. **只读为主的那台设备会一直显示旧数据**（简报/inbox 都是上一次同步时的内容），直到它自己写一次；
  2. 而它一旦写，`push_after_commit` 只推不拉 → 必然非快进 → 直接进入冲突保护态。也就是说
     "对端推送过 + 本机没及时拉" 会把一次本该无感的 fast-forward 变成一次人工冲突恢复。
- **修法方向**（择一或组合）：顶部栏加一个「立即同步」按钮；把 60 秒轮询在**工作树 clean 且非保护态**
  时升级为一次真正的 `sync_workspace()`；或在窗口获得焦点/变为可见时跑一次拉取（当前只有
  `checkVersion` + 状态刷新）。注意要保留"脏工作树绝不自动合并"的现有保护。

### D7 · 冲突恢复预检被拒时，界面只说"恢复准备未完成"

- **发现路径**：§A6.2 第 5–6 步第二次点「预检并写入」时，弹层只显示
  「临时预检未通过：恢复准备未完成。」——**没有任何可执行信息**，与 D3 是同一类缺陷，只是发生在
  前端。后端其实已经把原因装在 `preparation.error_code` 里（本例为 `preserve_both_path_collision`），
  是前端把它丢了。
- **证据**：`web/src/features/sync/conflict.ts::previewSyncConflictRecovery()` 只读
  `data.reason`，读不到就落到写死的字符串；`preparation.error_code` 与 `recovery.error_code`
  两个字段虽在类型里、却从未被使用（`grep -c error_code` 在前端仅出现在类型声明）。
- **修法**：按错误码给一张**可执行**的提示表（`RECOVERY_FAILURE_HINTS`），未知码退化为
  「恢复准备未通过（<code>）：请重新打开冲突详情后重试。」；`data.reason` 仍然优先。
  回归锚点：`web/scripts/test-sync-render.mjs` 用真实的被拒响应体断言弹层文案含具体原因、
  且**不再**出现「恢复准备未完成」；变异验证（去掉提示表查表）能复现旧文案。

### D8 · 同一路径第二次选「保留双方副本」必然失败（`preserve_both_path_collision`）

- **证据**：第一次恢复会把远端内容写到 `inbox.md.remote`；第二次对同一路径再选「保留双方副本」时
  `target.exists()` 为真，直接 `raise ValueError("preserve_both_path_collision")`，
  整次恢复被拒（`RecoveryPreparation(status='rejected', error_code='preserve_both_path_collision',
  candidate_paths=())`）。也就是说：**冲突恢复对同一文件不可重复执行**，而这恰恰是用户在
  「保留双方副本 → 发现还要再合一次」时最自然的动作。
- **风险面**：不能用覆盖解决——`inbox.md.remote` 是那份远端内容的唯一副本；也不能让用户在
  两个同名文件里手动猜。修法必须**确定性**且**不丢数据**。
- **修法**：兄弟名改为带远端 revision 短码
  `f"{path}.remote.{remote_revision[:7]}"`（同一份远端内容 ⇒ 同名；不同内容 ⇒ 不同名，天然不撞），
  并把实际落盘的相对路径（`target.relative_to(staging).as_posix()`）写进 `candidate_paths`，
  让预检报告与真正写回的文件名一致。回归锚点：
  `tests/unit/test_sync_conflict_recovery.py::test_second_preserve_both_uses_a_revision_suffixed_sibling`
  连做两次保留双方并断言两份副本内容都在；变异验证（恢复旧的 `raise`）能复现 `rejected`
  + `preserve_both_path_collision`。

> **D7/D8 的产物状态**：两者都在 build 29 的真机复跑中撞到，修完随 **build 30**
> （`frontend_build = v2026.09.13-b31c3ac-c7517c5a`，DMG SHA-256
> `8a87044ba839ba2c291013a5b6d373b7834e9f1596259da9fa89fda0a131b645`）出包，
> 并已在装好的 build 30 上真机复验：**D8 通过**（重造分叉 + vault 里已有第一轮
> `inbox.md.remote`，选「保留双方副本」→ 预检 `validated`、写回
> `applied_paths = ["inbox.md.remote.09aebd7"]`、第一轮兄弟文件哈希不变、两份内容同时在位）；
> **D7 对齐**（"快照过期"响应带 `error_code`，命中的是具体原因而不是「恢复准备未完成」）。
> 复现步骤 = §A6.2 第 5 步连点两次「保留双方副本」，第 1 次成功、第 2 次应成功并落成
> `*.remote.<rev7>`；若被拒，提示语必须带具体原因而不是笼统的"恢复准备未完成"。
> 完整证据见 [`OPEN-VERIFICATION-ITEMS.md`](OPEN-VERIFICATION-ITEMS.md) §P。

### D9 · 恢复提交后的 push 被误判为非快进（**未修，待排期**）

- **怎么撞到的**：build 30 的真机复验里，冲突恢复写回成功（`recovery.status = committed`）之后，
  同一次响应里的 `push` 却是 `diverged-protected` + 「远端已有新提交，需要处理分叉
  （non-fast-forward）」。而这一对提交其实是**干净快进**。
- **证据**（逐条可复核）：
  - `dulwich.graph.can_fast_forward(repo, 09aebd7, f0a51bc) = False`，但同一条
    `can_fast_forward(repo, 09aebd7, 001df9a) = True`（直接子提交时正常）；
  - `git merge-base --is-ancestor 09aebd7 HEAD` = **YES**（图可达性角度确实是快进）；
  - `porcelain.push` 抛 `DivergedBranches(b'09aebd7…', b'f0a51bc…')`，App 归类
    `non-fast-forward`；同一对提交用系统 git（走 127.0.0.1:7890 代理）推送**成功**
    （`09aebd7..f0a51bc`），随后 `POST /api/sync/run` 回到 `ready`、`ahead/behind 0/0`。
- **根因**：dulwich 的 `can_fast_forward` 用 `commit_time` 剪枝找公共祖先，不是图可达性。
  本地恢复提交 `001df9a`（`01:47:21Z`）与审计 `f0a51bc`（`01:47:22Z`）都**早于**远端父
  `09aebd7`（`01:50:00Z`）⇒ 从 tip 出发的遍历把整条路径剪掉，找不到 LCA，
  于是"不是快进"。**"恢复提交 + 审计提交"这个固定两跳组合正好落在坏区里**（直接子提交不触发）。
- **本次的触发条件是我人工造的**（为了让远端提交与本地分叉，我把远端提交的时间写晚了），
  但形状在**两台机器时钟有偏差**时天然成立：对端"未来"的提交 + 本机按真实时间生成恢复提交
  ⇒ 恢复成功、推送被拒、卡在 `diverged-protected`；重试恢复也一样（新的恢复提交依旧"更早"）。
- **修法方向**：`DulwichGitBackend.push` 捕获 `porcelain.DivergedBranches` 后，用**不依赖时间戳的
  图可达性**复核（从本地头沿 parents 走到远端 ref）；只有确认真快进时才对该 ref 显式
  `force=True` 重推一次，并把"图复核通过"写进状态原因。**不做无条件 force。**
