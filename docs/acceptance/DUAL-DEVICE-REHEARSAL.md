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

- 两台 Mac：**Studio**（已有工作台）与 **Air**（第二台，装同一个 App）。
- 一个**专用演练仓库**（GitHub 私有，例如 `summitworkbench-rehearsal`）+ 一个有 `repo` 权限的 PAT。
- 铁律（来自 [`UI-VERIFICATION-FINAL-PROMPT.md`](UI-VERIFICATION-FINAL-PROMPT.md) §0）：

  1. **Web 写操作会自动 commit 并 push**，而远端历史**不能**用本地 `reset` 收回（产品绝不 force-push）。
     ⇒ 演练**不要用真实工作区的远端**，一律用专用演练仓库。
  2. **`HOME` 隔离会切断 Keychain**。⇒ 演练全程用真实 `HOME`，只把工作区目录指向 `~/Documents/Rehearsal`。
  3. 演练用的工作区是**新建的空工作台**，跑完删掉即可，真实 vault 全程不参与。

## A7 · 第二台机器接入（向导「从另一台 Mac 克隆」）

**在 Studio 上准备演练仓库**

1. 打开连接向导（设置页右上「重新打开连接向导」，或首次启动）。
2. 选「**新建我的工作台**」，路径填 `~/Documents/Rehearsal`，走到完成并进入工作台。
3. 新建一个空的 GitHub 私有仓库 `summitworkbench-rehearsal`。
4. 设置 → **高级与维护** → **Git 同步**：填 HTTPS 地址、GitHub 用户名、PAT →
   点「**预览 HTTPS 转换**」→ 通过后点「**确认并转换**」。
5. 回到「今日」页随便捕捉一条内容（例如 `演练-A`），让它产生一次提交并推送。

**在 Air 上走新旅程（这就是 A7 的证据）**

6. 装包并首次打开 → 连接向导 → 选「**从另一台 Mac 克隆**」。
7. 填四项并点「**连接并检查**」：
   - 私有 HTTPS 仓库地址：`https://github.com/<you>/summitworkbench-rehearsal.git`
   - 目标文件夹：`~/Documents/Rehearsal`（Air 上**必须还不存在**）
   - GitHub 用户名、访问令牌（PAT）
8. **期望**：短暂等待后出现确认块，显示 **工作区短码**、**兼容性**、**远端地址**。
   此时 Air 上 `~/Documents/Rehearsal` **还没有**正式落盘（只有暂存目录）。
9. 点「**确认并开始使用**」→ 继续连模型/飞书（可跳过）。

**A7 通过标准（逐条留证）**

- [ ] Air 的 `设置 → 高级与维护 → 工作台切换` 里出现该工作台，且 `设备角色` 为 **secondary**。
- [ ] Air 的 vault 里能看到 Studio 第 5 步写的内容（克隆真的带过来了）。
- [ ] Air 的 Keychain 里有 `com.summitworkbench.credentials.<workspace_id>` / `git:github.com:<user>` 条目，
      且**值是那份 PAT**（钥匙串访问.app 里搜 `SummitWorkbench`）。
- [ ] `~/Library/Application Support/SummitWorkbench/onboarding-draft.json` **不含** PAT
      （向导完成时会清理该草稿；若还在，也必须是 `git_mode=remote` + `remote_url` + `git_username`，无 `pat`）。
- [ ] 演练仓库的任意提交里**不含** PAT（`git log -p | grep -c github_pat_` 为 0）。

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

1. 两台机器上删掉演练工作台：`设置 → 高级与维护 → 工作台切换`，在对应条目点
   「**移除此 Mac 上的工作台**」（只删本机 profile/runtime/草稿，vault、远端与 Keychain 都不动）。
   移除**当前**工作台后需要重启工作台才生效——按提示重启即可。随后删掉 `~/Documents/Rehearsal`。
2. 删除 GitHub 上的演练仓库。
3. 在 `OPEN-VERIFICATION-ITEMS.md` 里登记：**A7** 移入「已关闭」；**A6** 若只做了 §A6.1 抽查，
   把 A6 一行改写为"已在 build 29 完整验收 + 已在本 build 抽查通过"，并写明本 build 的
   `frontend_build`（`build-meta.json`）、日期与逐条证据；若走了 §A6.3 完整重跑，按完整口径关闭。
