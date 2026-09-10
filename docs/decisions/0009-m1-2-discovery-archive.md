# ADR 0009 · M1-2 会议发现与原文归档

- 状态：✅ 代码 + 单测 + **飞书主链路真机冒烟通过**（2026-08-31）；质量门全绿（ruff / mypy strict / pytest 141）
- 日期：2026-08-31
- 里程碑：M1-2（会议发现与原文归档）
- 依据：`docs/archive/plans/DEVELOPMENT_PLAN.md` §6 M1-2；PRD §3.1.9 L14/L15/L22；ADR 0007/0008

## 背景

先证据、后建议：M1-2 只负责证据侧——在**模型调用之前**可靠把完整逐字稿落盘，并以幂等键防重。
结构化处理（模型）属 M1-3。复用 M0 已跑通的会议发现（`list_meetings_by_no`）与取稿
（`FeishuNoteSource.fetch_transcript`），复用 M1-1 的状态机与幂等键。

## 决策

### 状态账本（`repositories/meeting_state.py`）

- `MeetingTask` 的状态变迁按 append-only JSONL 落 `_vault/_signals/meeting-state/log.jsonl`，
  沿用用量账本思路：`latest_task(idem_key)` 取同键最后一条即当前状态，整条日志即审计轨迹。
- `all_latest` 供 M1-5 `wb status` 汇总。仅读写，防重判定交给 workflow。

### 证据层归档（`repositories/meeting_archive.py`）

- 渲染 `type: meeting-transcript` / `status: archived` 的证据文件，保留说话人+时间戳原文，
  不与 AI 摘要混写；录像不下载，仅留来源标识（L15）。frontmatter 用 `yaml.safe_dump`
  保证合法，单测断言 `validate_note` 通过。
- 命名 `<date>-<slug>-transcript.md`；`slug` 保留中文、折叠不安全字符；`transcript_stem`/
  `note_stem` 供 M1-3 结构化笔记用同一 slug 回链，wikilink 与文件名一致。
- 写入幂等：证据文件已存在则不覆盖（`overwrite` 显式才覆盖），避免重复归档破坏证据。
- `projects` 在模型理解前默认 `[unresolved]`（L22 占位）；调用方已知可传入。

### 发现→归档编排（`workflows/meetings/archive.py`）

- `archive_meeting(vault_dir, DiscoveredMeeting, fetch, ...)`：取稿回调 `fetch` 由调用方注入，
  本模块不直接联网，可用假回调完整单测。
- 幂等（L14 第 6 条）：
  - 飞书链路先按 `meeting_id:note_id` 查账本，状态在「archived 及以后」（含 failed，逐字稿已落盘）
    即空转，**连取稿都不做**（单测断言 fetch 零调用）。
  - 本地导入按内容哈希防重（内容在手才能算键，先取后判）。
- `unavailable` 分支：无 `note_id` 的飞书会议记 `discovered → unavailable` 留原因，不取稿、
  不用标题/摘要冒充完整处理（L14 第 7 条）。
- 取稿失败：取稿前已记 `discovered`，异常向上抛、不产生 `archived`，状态停在 `discovered` 可重试。

### CLI

- `wb meeting archive --meeting-no --since --until [--project ...]`：飞书主链路，发现→取稿→归档，逐场汇报。
- `wb meeting archive-local <file> --title --date [--meeting-id --project ...]`：本地兜底（不联网）。

## 交付

- 3 个新模块 + `workflows/meetings/__init__` 与 `cli/main` 注册；21 项新单测（共 140）。
- 本地兜底链路已手工冒烟（archive → 幂等 skip → 状态账本 fetched→archived）。

## 真机冒烟（2026-08-31）

- ✅ **完整 happy path（会议号 182929017）**：发现「罗艺峰的视频会议」（有 `note_id`）→ 取回 6365 字符
  真实逐字稿（网课系统配置需求落地会议，8/27）→ 落 `meetings/transcripts/2026-08-27-罗艺峰的视频会议-transcript.md`
  （frontmatter 合规）→ 状态账本 `discovered → archived` → **重跑 `skipped-existing` 幂等空转、不重复取稿**。
- ✅ **unavailable 分支（会议号 493701461）**：该场无智能纪要（`note_id` 空）→ 正确记 `discovered → unavailable`
  留原因，**未写任何逐字稿文件、未冒充结果**（L14 第 7 条真机验证）。
- ⚠ 真机暴露并已修的**路径 bug**：证据层原误写入扁平 `meetings/`，应为 `meetings/transcripts/`
  （ADR 0003 / PRD 结构）；已改 `transcripts_dir` + `notes_dir`，加单测断言子目录。
- 📌 **飞书 API 约束**：`list_by_no` 时间跨度过大会 `param error`；实测约 30 天窗口可用，3 个月失败。
  M1-7 历史补导需把日期范围切成 ≤30 天窗口分批查询。
- 更广的「自动发现本人参加的全部已结束会议」（L14 第 7 条，不依赖会议号）需确认飞书是否有对应
  列表接口；当前发现仍以 9 位会议号驱动（沿用 ADR 0007），为后续接口/真机跟进项。

## 后续（不在本 ADR）

M1-3 接 `process_transcript`：读已归档证据 → 模型结构化 → 产出 `meeting-note` 并回链逐字稿，
状态 `archived → processed → pending-review`；失败进错误队列、`archived → failed`，零半成品（L41）。
