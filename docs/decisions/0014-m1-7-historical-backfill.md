# ADR 0014 · M1-7 历史补导

- 状态：✅ 实现完成并真机冒烟；⏳「按日期枚举全部会议」的飞书 API 待真实租户确认（见下）
- 日期：2026-09-01
- 里程碑：M1-7（历史补导）
- 依据：`docs/plans/DEVELOPMENT_PLAN.md` §6 M1-7；PRD L14 第 10 条

## 决策

- **输入源：本地逐字稿清单**（用户拍板）。`wb meeting backfill <目录|文件> --since --until`
  扫描本地逐字稿，按显式日期范围过滤。日期取 frontmatter `date`，缺失回退文件名 `YYYY-MM-DD` 前缀。
  不依赖尚未确认的「按日期自动枚举我参加的全部会议」飞书 API——该能力待真实租户/开放平台确认端点与
  scope 后再补自动发现层，届时只需替换发现来源，编排层不变。
- **先预估后执行**：`domain/backfill.py`（纯规则）汇总待补导会议数、输入/输出 token 与费用；
  输入 token 取本地文件实际长度（精确），输出按 `max_output_tokens` 保守估。CLI 开始前打印预估，
  默认需确认（`--yes` 跳过）。
- **跨预算再确认**：预计本月累计费用越过软预算时，即使 `--yes` 也再次确认（除非 `--force-budget`），
  对齐 PRD「预计跨越软预算或高成本阈值时再次确认」；软预算只提示不阻断。
- **幂等可续跑**：按状态账本判定终态（processed/pending-review/applied/ignored）即跳过；
  中断后重跑只处理未完成项。复用 M1-2 归档与 M1-3 处理链路（本地 source）。
- **默认只沉淀知识**：默认不生成行动候选；`--include-actions` 才由 `candidates_from_note(historical=True)`
  生成带 `historical` 标记的审批候选并刷新审批页。审批页渲染/解析已持久化 `historical` 字段，刷新不丢标记。

## 验收

- Ruff、mypy strict、pytest **215 项**全绿（+8）：日期过滤、账本续跑跳过、MockTransport 处理、
  historical 候选生成与审批页往返、失败上报、费用/预算预估与跨预算判定、CLI 注册。
- 真机冒烟（隔离 scratch vault，真实模型）：`wb meeting backfill` 预估→确认门→逐场处理→产结构化笔记；
  重跑幂等空转（待补导 0）；对 "n" 正确 abort、零模型调用。
- 严格验收（PRD L44）整体待真实数据显式回归。

## 遗留

「自动发现全部会议（不靠会议号/本地文件）」的飞书 API 仍未确认（memory：`list_by_no` ≤30 天窗、
不含 note_id）。当前 M1-7 以本地逐字稿清单满足补导需求；自动发现留作后续增强，不阻塞 M1 收口。
