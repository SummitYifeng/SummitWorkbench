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
2. Air 的 vault 里能看到 Studio 第 5 步捕捉的内容（克隆真的带过来了）。
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

## 附 · 本次复跑发现的产品缺陷（3 个，均未修）

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
