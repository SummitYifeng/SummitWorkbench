# ADR 0043 · P2-02 同步冲突解释与恢复计划

- 状态：已完成（build 29 双机退出验收通过，2026-09-07）
- 范围：`diverged-protected` 等同步保护态的冲突分类与安全建议
- 前置：P1-07D（ADR 0041）、P2-01B（ADR 0042）

## 决策

1. 冲突解释只接受 vault 内相对路径，不读取文件正文，也不返回绝对本机路径、凭据或
   远端 URL。输出按路径稳定排序，便于 UI 和诊断包复用。
2. `_events/**/*.json` 归类为追加式 event，可在后续恢复阶段自动收集；已登记的
   `_views/thread-activity.json` 归类为可重建派生视图；未登记的 `_views/**` 没有安全
   重建器，必须人工选择 `preserve-both` 并保留确定性的 `.remote` 副本；Markdown 必须人工
   选择；二进制或未知格式先保留双方副本。
3. 当前提供五个只读/预检接口：`GET /api/sync/conflict/explain`、`GET /api/sync/conflict/plan`、
   `GET /api/sync/conflict/details`、`GET /api/sync/conflict/validate` 和
   `POST /api/sync/conflict/selection/validate`；另有
   `POST /api/sync/conflict/recover` 作为显式本地恢复入口。
   恢复计划只描述阶段、计数和禁止动作，分叉详情只返回两侧 revision/时间、路径分类、
   摘要和 event 标识，不返回正文；validate 只在临时非 Git 目录校验 event schema/投影。
   已定义的 `_views/thread-activity.json` 会在临时目录重建；未定义视图转为人工
   `preserve-both`，不猜测业务语义。详情、计划、validate 和 selection
   validate 都不 fetch、不 merge、不替换工作树、不 force push，也不改变现有
   `diverged-protected` 写入保护。selection validate 还会校验人工选择是否完整、是否
   基于当前双侧 revision，但不会执行选择或写回。
4. `prepare_automatic_recovery` 提供快照绑定的临时准备结果：再次核对 base/local/remote
   revision，拒绝 dirty worktree，并在调用方上下文结束时清理 staging；准备结果不暴露
   绝对临时路径，也不写入当前 vault。
5. `prepare_manual_recovery` 在同一快照保护下从干净 local worktree 生成候选树：
   `keep-remote` 只替换 staging 中的选择路径，`preserve-both` 以确定性的 `.remote` 兄弟
   文件保留远端副本。
6. `apply_prepared_recovery` 是唯一写回入口：必须经过 schema、event projection 和测试
   验证、显式确认、再次通过 revision 快照校验且当前 worktree 干净，只把候选树的显式
   路径以原子写入落回，并创建普通双父 merge commit；随后 Web 调用方仅尝试普通 push。
   它不 fetch、不使用 force、reset、rebase 或 stash；远端变化、离线或凭据问题只返回
   可见状态，不覆盖本地恢复提交。合并提交一旦成功即报告为已提交；若后续脱敏审计
   写入失败，结果会单独标记审计失败，避免 UI 将已完成的双父提交误判为可重试失败。

## 验收

已覆盖分类稳定性、路径越界拒绝、混合冲突的人工确认提示、自动项必须先进入临时 worktree
验证阶段、双侧分叉元数据与 event 标识脱敏、临时目录 event schema/投影验证、已定义
thread activity 视图的确定性临时重建、快照绑定的临时准备、dirty/stale 保护、人工选择
候选树、preserve-both 保留规则、显式确认的本地双父恢复提交、人工选择预检、五个 Web
API 只读/预检契约、保护态 UI 接线、脱敏恢复审计、普通 push 尝试，以及未知派生视图
人工 `preserve-both` 回退与确定性 `.remote` 副本；合并成功但审计写入失败时的状态可见性。

自动化质量门与 build 29 双机退出验收均已通过。第一轮恢复提交 `c95b6c1`、审计提交
`8a6a543` 覆盖 Markdown、未知视图、binary、追加 event 和已登记视图重建，审计计数为
`4/1/1`；第二轮脏工作树保护先返回 `current_worktree_dirty`，清理后产生双父提交 `af662d5`
和审计提交 `ec00260`，计数为 `5/0/0`。Studio fast-forward 后双方最终同为 `ec00260`，
工作树 clean、ahead/behind `0/0`。隔离验收副本还验证了审计写入失败时保持
`committed` 并明确报告 `audit_status=failed` / `recovery_audit_failed`。这些证据覆盖了
主路径与保护分支，ADR 0043 现可视为完成。

build 25–29 的候选包证据、已完成项和补验步骤见
`docs/archive/acceptance/P2-02-BUILD-25-STUDIO-AIR-RUNBOOK.md`。P2-02 已完成并标记 `[x]`；P2-03
仍未启动。

## 后续状态

本 ADR 的结论锚定在 **build 29 / `697c239`**。此后前端做了整体拆分（`legacy-main.ts` →
`features/sync/*`，Step 1/6，逐行对比特一致），而冲突恢复的**后端与 API 契约自 `697c239` 起
逐字节未变**（11 条 `/api/sync/*` 在 `docs/contracts/web-route-contract.json` 中完全相同），
前端只有一处用户可见新增行为（`ee561f5`：`/api/sync/status` 读取失败时保留保护态，而不是静默
隐藏横幅）。因此"把结论重新锚定到当前 build"只需一次差异点抽查，范围与步骤见
[`../acceptance/DUAL-DEVICE-REHEARSAL.md`](../acceptance/DUAL-DEVICE-REHEARSAL.md) §A6；
未验证项以 [`../acceptance/OPEN-VERIFICATION-ITEMS.md`](../acceptance/OPEN-VERIFICATION-ITEMS.md) 为准。
