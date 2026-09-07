# ADR 0043 · P2-02 同步冲突解释与恢复计划

- 状态：已实现第一阶段与恢复计划切片（2026-09-07；只读，不执行恢复写入）
- 范围：`diverged-protected` 等同步保护态的冲突分类与安全建议
- 前置：P1-07D（ADR 0041）、P2-01B（ADR 0042）

## 决策

1. 冲突解释只接受 vault 内相对路径，不读取文件正文，也不返回绝对本机路径、凭据或
   远端 URL。输出按路径稳定排序，便于 UI 和诊断包复用。
2. `_events/**/*.json` 归类为追加式 event，可在后续恢复阶段自动收集；`_views/**` 归类
   为可重建派生视图；Markdown 必须人工选择；二进制或未知格式先保留双方副本。
3. 当前提供 `GET /api/sync/conflict/explain`、`GET /api/sync/conflict/plan` 和
   `GET /api/sync/conflict/details` 三个只读接口。恢复计划只描述阶段、计数和禁止动作，
   分叉详情只返回两侧 revision/时间、路径分类、摘要和 event 标识，不返回正文；它们都
   不 fetch、不 merge、不替换工作树、不 force push，也不改变现有 `diverged-protected`
   写入保护。
4. 后续自动恢复必须在临时 clone/worktree 完成，经过 schema、event projection 和测试
   验证后才可提出可审计的恢复动作；本 ADR 不提前承诺该能力已实现。

## 验收

已覆盖分类稳定性、路径越界拒绝、混合冲突的人工确认提示、自动项必须先进入临时 worktree
验证阶段、双侧分叉元数据与 event 标识脱敏，以及三个 Web API 只读契约；临时 worktree
实际准备、事件自动收集、生成视图重建和人工确认写回留待 P2-02 后续阶段。
