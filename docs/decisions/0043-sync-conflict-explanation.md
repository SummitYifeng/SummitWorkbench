# ADR 0043 · P2-02 同步冲突解释与恢复计划

- 状态：已实现第一阶段与恢复计划切片（2026-09-07；只读，不执行恢复写入）
- 范围：`diverged-protected` 等同步保护态的冲突分类与安全建议
- 前置：P1-07D（ADR 0041）、P2-01B（ADR 0042）

## 决策

1. 冲突解释只接受 vault 内相对路径，不读取文件正文，也不返回绝对本机路径、凭据或
   远端 URL。输出按路径稳定排序，便于 UI 和诊断包复用。
2. `_events/**/*.json` 归类为追加式 event，可在后续恢复阶段自动收集；`_views/**` 归类
   为可重建派生视图；Markdown 必须人工选择；二进制或未知格式先保留双方副本。
3. 当前提供 `GET /api/sync/conflict/explain`、`GET /api/sync/conflict/plan`、
   `GET /api/sync/conflict/details`、`GET /api/sync/conflict/validate` 和
   `POST /api/sync/conflict/selection/validate` 五个只读/预检接口。
   恢复计划只描述阶段、计数和禁止动作，分叉详情只返回两侧 revision/时间、路径分类、
   摘要和 event 标识，不返回正文；validate 只在临时非 Git 目录校验 event schema/投影。
   已定义的 `_views/thread-activity.json` 会在临时目录重建；未定义视图仍返回
   `view-rebuild-pending`，不把未重建视图算作完成。
   它们都不 fetch、不 merge、不替换工作树、不 force push，也不改变现有
   `diverged-protected` 写入保护。selection validate 还会校验人工选择是否完整、是否
   基于当前双侧 revision，但不会执行选择或写回。已定义的
   `_views/thread-activity.json`，validate 会在临时目录按 event projection 重建并校验；
   未定义的 `_views` 仍返回 `view-rebuild-pending`，不会猜测其业务语义。
4. `prepare_automatic_recovery` 提供快照绑定的临时准备结果：再次核对 base/local/remote
   revision，拒绝 dirty worktree，并在调用方上下文结束时清理 staging；准备结果不暴露
   绝对临时路径，也不写入当前 vault。
5. 后续自动恢复必须在临时 clone/worktree 完成，经过 schema、event projection 和测试
   验证后才可提出可审计的恢复动作；当前仍不执行工作树替换、人工选择写回或审计提交。

## 验收

已覆盖分类稳定性、路径越界拒绝、混合冲突的人工确认提示、自动项必须先进入临时 worktree
验证阶段、双侧分叉元数据与 event 标识脱敏、临时目录 event schema/投影验证、已定义
thread activity 视图的确定性临时重建、快照绑定的临时准备、dirty/stale 保护、人工选择
预检，以及五个 Web API 只读/预检契约；临时 worktree 实际恢复、生成视图写回和人工确认
写回留待 P2-02 后续阶段。
