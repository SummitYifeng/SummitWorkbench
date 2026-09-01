# M1 严格验收记录（PRD L44）

- 日期：2026-09-01
- 结论：**6 项全部通过**（真实数据、真机运行）。M1「会议进入第二大脑」达标，可进入 M2。
- 依据：`docs/product/PRD.md` L44；`docs/plans/DEVELOPMENT_PLAN.md` §6 M1 严格验收。
- 环境：真实飞书租户 + 真实会议 + 云端模型（deepseek-v4-flash）；真实 vault
  `~/Documents/Work/_vault`。故障演示在隔离临时 vault + 本地 mock 进行，不污染真实数据。

## 逐项结果

### A. 3 场真实会议归档+结构化、可追溯、无重复 ✅
- 罗艺峰的视频会议（会议号 182929017，飞书妙记链路）、排版对齐（341011992，手动逐字稿
  `wb meeting import`）、财务对齐（手动逐字稿）三场均归档证据层并结构化为会议笔记。
- 可追溯：证据索引每条带「说话人 + 时间戳（MM:SS）+ 段落 + 原话引用」，行动项带截止日期。
- 无重复：`wb meeting import` 重跑显示「全部已导入，幂等空转」，处理 0 场。
- 真实发现（已记录）：另两场（862750061 财务对齐 / 735571543 Marketing 周进度）无飞书妙记
  → 系统正确记 `unavailable`，未冒充。据此确立**混合取稿策略**（妙记按需 + 手动 `import` 兜底，
  见 ADR 0011 补充决策）。

### B. 审批 批准/拒绝/修改 各≥1，未确认零写回 ✅
- 批准 ×2：decision-1 → 全局 inbox；decision-4 → `HIC_SWB_LaTEX` 项目主笔记（人工把 target
  改为别名「学员手册」，系统解析回规范 ID）。
- 拒绝 ×1：decision-2（删除线 + `#ignore`）→ 审计归档 audit-only。
- 修改 ×1：decision-4 的 target_project/route 被人工修改；审计文件同时记录 **AI 原值
  （unresolved / global-inbox）与用户最终值（HIC_SWB_LaTEX / project-main）**。
- 未确认零写回：其余 `- [ ]` 候选未产生任何写入（抽查 action-item-0 未进 inbox）。
- 幂等：`wb review apply --apply` 后重跑 dry-run 显示 批准写回=0、失败=0。

### C. 10 个真实问答均有来源 ✅
- 10 问经 `wb ask` 运行：9 条返回带来源引用的答案（事实逐条 `← [[来源]]`，事实/建议分区）；
  1 条（活满网课时间线）因 vault 尚无该项目内容，正确返回「未找到 / 0 来源」而**不编造**。
- 证明检索召回 + 严格 grounding + 拒绝越界引用均生效。策略提示：更广的战略型问答质量随
  导入的会议历史增多而提升。

### D. 一次可恢复故障 + 一次「初调+3 重试」全失败 ✅
- 隔离 vault + 本地 mock 演示：
  - 可恢复：mock 首次 503、重试成功 → 用量账本 `attempts=2`、同一模型、产出完整笔记。
  - 耗尽：mock 始终 503 → `attempts=4`（初调+3 重试）→ 进错误队列
    `_signals/model-errors/*.json`（含 task_key/model_id/prompt_version/stage/attempts/reason/
    transcript_path）、**零半成品**（无 note）、原文保留、**未自动换模型**。
- 附带修正：耗尽错误 reason 之前仅带单次「第 1 次」消息，已改为「初调+3 次重试（共 4 次调用）
  后仍失败：…」以匹配 attempts、强化失败可见性。

### E. 用量账本核对 ✅
- `wb status` 当月：14 次调用 / 0.176407 CNY，与账本 `_signals/model-usage/2026-09.jsonl`
  逐行求和**完全一致**（14 次 / 0.176407 CNY）。

### F. 积压阈值通知只响一次 ✅
- `wb status --notify` 第 1 次触发积压通知（待确认 23 条 ≥5；最老 25 天 >3）；
  第 2 次无新通知。去重状态落 `_signals/notifications/state.json`。

## 结论与后续
- M1 严格验收 6/6 通过，可进入 **M2 晨间简报与周复盘**。
- 常态运维建议：按混合策略用 `wb meeting import` 持续补入手动逐字稿；随会议历史积累，
  `wb ask` 的战略型问答与项目时间线类问题会逐步可答。
