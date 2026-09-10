# ADR 0012 · M1-5 状态、费用与提醒

- 状态：✅ 实现完成，质量门全绿；⏳ 待真实积压/预算边界的显式验收
- 日期：2026-08-31
- 里程碑：M1-5（状态、费用与提醒）
- 依据：`docs/archive/plans/DEVELOPMENT_PLAN.md` §6 M1-5；PRD L44、NFR-8

## 决策

- **`wb status`**：只读聚合，不改状态。汇总
  - 各处理状态计数（discovered…failed，来源 `meeting_state.all_latest`）；
  - 当月用量（调用数/输入输出 token/估算费用，来源 `usage_ledger.monthly_totals`）；
  - 软预算评估与待确认候选积压。
  支持 `--json`（脚本消费）与 `--notify`（评估阈值并按去重规则发新通知，供 launchd 定时调用）。
- **用量账本字段**：M0-6 的 `UsageRecord` 已记录能力、模型、任务键、token、重试次数与
  调用时单价/费用快照，M1-5 直接复用，未新增字段。
- **月度软预算**：`domain/budget.py` 纯规则，`[budget].monthly_soft_limit`（缺省不启用）。
  越过软上限只告警、**绝不阻断**新会议处理。币种默认 CNY，建议与 pricing 一致。
- **待确认积压阈值**：`domain/backlog.py`，条数 ≥5 或最老候选等待 >3 天触发。严重度 =
  触发的阈值个数（0/1/2）。积压条数与最老天数取自审批页 `- [ ]` 候选（候选粒度，
  非会议粒度；`wb status` 用「待确认会议」与「待确认候选积压」两个标签区分）。
- **只响一次 / 升级重通知（L44）**：`observability/alerts.py` 纯评估 + `notify_state.py`
  去重状态（`_signals/notifications/state.json`）。预算按月去重（跨月重置）；积压仅在
  严重度较上次通知升高时再通知，回落也写回状态，日后再次跨阈值可重新通知。

## 模块边界

- `domain/`：预算与积压纯规则（不读盘、不发通知）。
- `observability/`：`wb status` 聚合与通知评估/去重（PRD §2.2 归属）。
- `repositories/notify_state.py`：通知去重状态读写。
- `cli/status.py`：结果呈现与退出码，不承载业务规则。

## 验收

- Ruff、mypy strict、pytest **193 项**全绿（+18）：预算阈值、积压严重度、只响一次/升级/
  回落后重通知、跨月重置、聚合正确、CLI `--json` 可解析。
- 真机冒烟：对真实 `_vault` 运行 `wb status` 正确显示 2 场会议（1 待确认 / 1 不可用）、
  当月 2 次调用 0.0250 CNY、3 条待确认候选最老 4 天并标记「需处理」。
- 严格验收（PRD L44「积压阈值通知只响一次」）待真实跨阈值场景显式回归。
