# ADR 0008 · M1-1 会议链路稳定 schema 与状态机

- 状态：✅ 纯领域实现完成，质量门全绿（ruff / mypy strict / pytest 119）
- 日期：2026-08-31
- 里程碑：M1-1（稳定 schema 与状态机）
- 依据：`docs/plans/DEVELOPMENT_PLAN.md` §6 M1-1；PRD §3.1.9 L14/L21/L22/L41；`docs/plans/M1_KICKOFF.md`

## 背景

M1 把两条已跑通的链路（会议发现 / 逐字稿拉取 → 结构化处理）串起来并加审批边界。
先落纯领域的 schema 与状态机，可独立测试，后续切片（M1-2…M1-7）在其上挂适配器与持久化。
边界：领域层不读文件、不访问网络（沿用 M0 模块约定）。

## 决策

### 处理状态机（`domain/pipeline.py`）

- `ProcessingState`：主链路 `discovered → fetched → archived → processed → pending-review
  → applied/ignored`，分支 `unavailable`（无完整文本权限，L14-7）、`failed`（模型重试耗尽，L41）。
- 迁移表 `ALLOWED_TRANSITIONS` 为单一事实源，`can_transition/ensure_transition` 依它判定。要点：
  - `fetched → archived` 唯一出边：**双文件归档必须先于模型调用**（L15）；取稿瞬时失败不改状态，
    停在 `discovered` 等重试；确认无完整文本权限才 `discovered → unavailable`。
  - 模型失败只在 `archived`/`processed` 之后发生（L41），保留原文进 `failed`。
  - `unavailable`/`failed` 是**可重试的停泊态**而非终态：修复权限/额度/配置后显式重试
    （`unavailable → fetched`、`failed → processed`，重跑再失败 `failed → failed`）。
  - 终态仅 `applied`/`ignored`（`TERMINAL_STATES`）。
- `MeetingTask`：把「来源 + 幂等键 + 状态 + 原因」绑定的不可变记录；`advanced_to` 校验迁移后返回新实例。
- `ProcessingState` 的字符串值与 `domain.vault.STATUS_VOCAB` 中会议笔记经历的状态刻意一致，
  但两者是不同关注点：pipeline 跟踪链路进度，vault 是笔记 frontmatter。故**未**把 pipeline 专属状态
  （discovered/fetched/processed/unavailable/failed）加入笔记词表。

### 幂等键（L14-6）

- `remote_idempotency_key(meeting_id, note_id)`：`meeting_id:note_id`；无 note_id（多为 unavailable）
  以 `meeting_id` 独占。
- `local_idempotency_key(content)`：`local:` + 逐字稿内容 SHA-256（strip 归一，防尾随空白抖动）。

### 审批候选与路由（`domain/review.py`，L21/L22）

- `EvidenceRef`（说话人 + 时间戳/锚点 + 原话）：`is_valid` 要求至少有锚点或原话——只有说话人不算依据。
- `ApprovalCandidate`：稳定 `candidate_id`、`kind`、`target_project`、`route`、`evidence` 等；
  `is_actionable` = 目标已解析（非空且非 `unresolved`）**且**有有效依据——缺目标或依据者不可勾选（L21）。
- `route_candidate`（L22 优先级）：目标不明 → 全局 inbox；有期限或涉他 → 飞书任务；
  明确内部下一步 → 项目主笔记；否则（未成熟想法）→ 项目 inbox。
- `candidate_id(idem_key, kind, index)`：由幂等键派生，重跑稳定，避免待确认页重复条目。
- `CandidateDecision`（pending/approved/rejected）对应待确认页的 `- [ ]` / `- [x]` / `~~~ #ignore`。
- `historical` 标记预留给 M1-7 历史补导候选（L14-10）。

## 交付

- `domain/pipeline.py`、`domain/review.py`，经 `domain/__init__.py` 导出。
- `tests/unit/test_pipeline_state_machine.py`、`tests/unit/test_review_schema.py`（+26 项，共 119）。
- 无适配器/持久化改动；供 M1-2 起各切片复用。

## 后续（不在本 ADR）

M1-2 会议发现与双文件归档接上 `MeetingTask` 与 `remote/local_idempotency_key`；
M1-4 审批写回接 `ApprovalCandidate` / `route_candidate`。
