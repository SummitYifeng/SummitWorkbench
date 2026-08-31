# ADR 0010 · M1-3 云端结构化处理

- 状态：✅ 实现与自动化故障注入完成；⏳ 待真实会议云端验收
- 日期：2026-08-31
- 里程碑：M1-3（云端结构化处理）
- 依据：`docs/plans/DEVELOPMENT_PLAN.md` §6 M1-3；PRD L15/L22/L36/L41/L42

## 决策

- **上下文预算**：配置 `context_window_tokens` 与 `context_safety_ratio`；按文本 token 估算判断是否分段，
  不按会议时长猜测。完整原文能安全放入时优先单次处理。
- **边界与层级合并**：分段优先保留段落和说话人行，单行仍过长才字符切分。各段使用同一会议模型提取，
  再用版本化 `meeting-merger` prompt 分层合并去重；任一阶段失败则整场失败。
- **证据约束**：`facts`、`decisions`、`action_items`、`open_questions` 均使用带证据的稳定 schema；
  evidence 必须包含原始时间戳或“段落 N”稳定锚点，截止日期必须为有效 ISO 日期。
- **统一重试上限**：任务编排控制“初调 + 最多 3 次指数退避”，覆盖瞬时 API 故障和 schema 违规；
  4xx 等非瞬时错误立即失败，始终使用同一模型，不自动切换供应商。
- **零半成品**：模型与 schema 全部成功后才渲染并原子替换 `meetings/notes/<date>-<slug>.md`；既有笔记
  默认不覆盖，保护人工编辑。任务状态才推进 `archived/failed → processed → pending-review`。
- **错误与用量**：每次取得模型响应即写月度用量账本。重试耗尽写
  `_signals/model-errors/<task-hash>.json` 并推进 `failed`；显式重跑成功后清除活动错误，状态日志保留历史。

## CLI 与验收

- `wb meeting process <meeting-transcript.md> [--task-key ...]`：处理一份已归档证据；成功、空转、失败使用
  不同退出码和明确路径输出。
- 自动化覆盖单次处理、schema 重试、超长分段与合并、证据/date 校验、笔记 schema、幂等、四次故障耗尽、
  错误队列、零半成品和失败后恢复。质量门：ruff、mypy strict、pytest 152 项全绿。
- 尚待：使用真实会议和本机模型配置运行，人工核对提取质量、证据链接、token/费用以及重跑空转。
