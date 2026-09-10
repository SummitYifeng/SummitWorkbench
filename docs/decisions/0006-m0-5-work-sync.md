# ADR 0006 · M0-5 work-sync 同步基础

- 状态：已执行并对真实 `~/Documents/Work` 冒烟通过
- 日期：2026-08-31
- 里程碑：M0-5（同步基础）
- 依据：`docs/archive/plans/DEVELOPMENT_PLAN.md` §5 M0-5；PRD §6 M0-9、NFR-3、L10

## 决策

`wb sync` 遍历 `WORK_ROOT` 直接子目录中的 Git 仓库（含 `_vault`），以 **git remote 为唯一真源**
批量同步。核心是**非破坏性**：

- 只做三种操作：`fetch`、`merge --ff-only`、`push HEAD`。**没有** reset / stash / rebase / force。
- **dirty 仓库不动工作树**：只 fetch，不合并；若同时领先则仍可安全 push（push 只推提交，不涉工作树）。
- 与 upstream **分叉**时报告 `diverged` 并停手，绝不 force，远端不被覆盖。
- 逐仓库隔离：任一仓库失败（无远端 / 未设 upstream / 网络 / 分叉 / 推送失败）都转成可见状态，
  不中断也不掩盖其它仓库（NFR-6）。
- **幂等**：全部同步后重复运行只报告 `up-to-date`，无副作用。

退出码：全部无问题 0；存在需人工处理的仓库 1。

## 状态词表

`up-to-date` / `pulled` / `pushed` / `pulled+pushed` / `dirty` / `no-remote` / `no-upstream` /
`diverged` / `fetch-failed` / `push-failed`（后五个 + no-upstream 视为需人工处理）。

## iCloud/Dropbox 边界（L10 / NFR-3）

同步机制是 git remote，**不是**文件级云同步。ADR-0002 已确认 `~/Documents` 未开启 iCloud
「桌面与文档」同步。本工具不引入任何 iCloud/Dropbox 对含 `.git` 目录的同步。

## 交付

- `repositories/git.py`：单仓库安全 git 操作封装（GitRepo / GitError），只暴露非破坏性原子操作。
- `workflows/sync.py`：发现仓库 + 逐仓库同步 + 聚合，SyncStatus 词表。
- CLI `wb sync`（可 `--work-root` 覆盖）。
- 集成测试（真实 git、本地裸仓库做远端、无网络）覆盖 up-to-date/push/pull/dirty/no-remote/
  diverged/幂等/发现与隔离，共 10 项；ruff/mypy strict/pytest(87) 全绿。

## 真机验证

对 `~/Documents/Work` 的 5 个仓库运行 `wb sync`：全部正确识别为 dirty（用户尚未提交的
M0-2/M0-3 文档改动 + `_vault` 的用量账本），`HIC_WebClass_Chinese_Final` 落后 3 但因 dirty
**正确跳过合并**，0 个需人工处理，退出码 0——非破坏性与隔离性得到真实验证。

## 验收对照（M0-5 / M0-9）

- ✅ 遍历 WORK_ROOT 批量 pull/push；git remote 为唯一真源。
- ✅ dirty / 冲突(diverged) / 无远端 / 网络失败给明确状态，不做破坏性自动修复。
- ✅ 重复运行幂等；任一仓库失败不掩盖其它。
- ✅ 不引入 iCloud/Dropbox 对 `.git` 目录的同步。
