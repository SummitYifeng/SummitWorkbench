# 双机现场复跑（A6 / A7）

> 本文件是 [`OPEN-VERIFICATION-ITEMS.md`](OPEN-VERIFICATION-ITEMS.md) 中 **A6**（真实双设备冲突恢复）
> 与 **A7**（第二台机器的向导接入）的**可执行复跑步骤**。两项都必须由**人在两台真实机器上**执行，
> 自动化只能覆盖代码路径（`tests/integration/test_acceptance_dual_device.py`）。
>
> 复跑完请把证据按「已关闭」的格式登记回 `OPEN-VERIFICATION-ITEMS.md`，并注明提交/日期。

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
5. 对每个需要选择的文件选「**保留本机**」或「**使用远端**」→ 点「**临时预检（不写入）**」。
   预期：显示「**临时预检通过**」及事件数/聚合数/候选文件数；此时点「**确认恢复并创建提交**」才可用。
6. 点「**确认恢复并创建提交**」。
   预期：创建**普通本地双父提交**并尝试普通同步（不 force-push / 不 reset / 不 rebase / 不 stash）。

**A6 通过标准（逐条留证）**

- [ ] Air 的 vault 里 `git rev-list --parents -n1 HEAD` 输出有**两个父提交**。
- [ ] 两侧内容都在（`离线-A` 与 `离线-B` 对应的文件都存在，按第 5 步的选择保持一致）。
- [ ] 审计记录为 body-free 且状态 committed（弹层/诊断里可见）。
- [ ] 恢复后的推送成功；**Studio** 下次同步是 **fast-forward**（Studio 侧无需再次解决冲突）。
- [ ] 若远端在恢复前又变了：Air 应**回到保护态**而不是硬覆盖 —— 这是正确的失败方式，记录截图即可。

## 收尾

1. 两台机器都删掉 `~/Documents/Rehearsal`。
2. 删除 GitHub 上的演练仓库。
3. 在 `OPEN-VERIFICATION-ITEMS.md` 里把 A6、A7 移入「已关闭」，写明日期、两台机器、App 版本
   （`build-meta.json` 的 `frontend_build`）与上面的逐条证据位置。

> **已知缺口（本轮未做）**：设置页目前**没有**「移除本机 profile」的按钮
> （`data-action="profile-remove"` 的派发分支存在，但没有渲染入口），所以演练工作区只能靠删目录 +
> 手动确认不再是当前项来收尾。若这成为日常操作，需要单独排期。
