# ADR 0007 · M0-10 飞书会议纪要拉取

- 状态：✅ 真机冒烟通过（2026-08-31，取回 2783 字符真实逐字稿）
- 日期：2026-08-31
- 里程碑：M0-10（会议纪要 API 冒烟）
- 依据：`docs/archive/plans/DEVELOPMENT_PLAN.md` §5 M0-4/M0-10；PRD L14/L15；ADR 0004（此处兑现其推迟项）

## 已核实端点（官方文档，2026-08）

| 步骤 | 方法 / URL | scope |
|---|---|---|
| 列会议（得 note_id）| `GET /open-apis/vc/v1/meetings/list_by_no`（meeting_no + start_time/end_time）| `vc:meeting.all_meeting:readonly` 等 vc 会议 scope |
| 取纪要产物 | `GET /open-apis/vc/v1/notes/{note_id}` | `vc:note:read` |
| 读文档正文 | `GET /open-apis/docx/v1/documents/{doc_token}/raw_content` | `docx:document:readonly` |

`list_by_no` 返回体每项直接含 `id`(meeting_id) / `topic` / `note_id`（无纪要则空）；
`notes/{note_id}` 的 `note_source.source_entity_id` 也回指 meeting_id。

`notes/{note_id}` 返回 `artifacts[]`：`artifact_type=1` 纪要文档、`artifact_type=2` **逐字稿文档**；
各带 `doc_token`。取 type=2 的 doc_token 读其 `raw_content` 即完整逐字稿纯文本。均支持 user_access_token。

## 决策

- `FeishuNoteSource.fetch_transcript(note_id)` 实装为：`get_note` → 选 `artifact_type=2` 的 doc_token
  → `read_doc_text`。**无逐字稿产物时显式报错**，不拿智能纪要冒充逐字稿，可降级到本地导入兜底（L14）。
- **会议发现**：`list_meetings_by_no(meeting_no, start, end)` 按会议号 + 时间范围列会议并取 note_id，
  逐页翻取。整条链路可由用户手上的 9 位会议号驱动：会议号 → note_id → 逐字稿。
- 默认 scope 增加 `vc:note:read`（`docx:document:readonly` 已在）。之前误猜的
  `vc:meeting:readonly` / `minutes:minutes:readonly` 作废。

## 交付

- `providers/feishu/meetings.py`：`list_meetings_by_no`（会议发现，翻页）+ `MeetingSummary`；
  `FeishuNoteSource.get_note / read_doc_text / fetch_transcript`；`TranscriptResult` 增加 `doc_token`。
- CLI `wb feishu meetings --meeting-no --since --until`（发现）与 `note-transcript --note-id`（冒烟）。
- 契约测试（MockTransport）：list_by_no 解析/翻页/空、选对 type=2、读正文、无逐字稿报错、note 缺失报错。
- 默认 scope 更新；ruff/mypy strict/pytest(91) 全绿。

## 尚待用户完成（真机冒烟）

1. 控制台已开 `vc:note:read`、vc 会议只读（`vc:meeting.all_meeting:readonly` 等）与 `docx:document:readonly`。
   注意 `vc:note:read` 若仅在 tenant 侧可用而 user 侧未授予，`notes/get` 会返回 121005；
   届时给 note/doc 读取加 tenant_access_token 通道（app 的 tenant 已具备相应权限）。
2. 重新授权取得含新 scope 的 token：`wb feishu authorize-url` → `login --code`。
3. `wb feishu meetings --meeting-no <9位会议号> --since <YYYY-MM-DD> --until <YYYY-MM-DD>` 列出会议与 note_id，
   再 `wb feishu note-transcript --note-id <note_id>` 取回逐字稿。无逐字稿产物或 API 不可用时按 L14 走本地兜底。

## 真机验证（2026-08-31）

- `wb feishu meetings --meeting-no 937075886 ...` → 列出会议 + note_id `7680022739336661970`。
- `wb feishu note-transcript --note-id 7680022739336661970` → 取回 **2783 字符**真实逐字稿
  （含说话人 + 时间戳）。整条链路用真实数据端到端跑通。
- 真机踩坑并解决：list_by_no 实际返回 `meeting_briefs`（不含 note_id，须再查会议详情）；
  docx 正文读取需在飞书控制台单独开通 **应用身份（tenant）** 的 `docx:document:readonly`。

## 验收对照（M0-10）

- ✅ 会议发现（会议号 → note_id）与 `note_id → 逐字稿文档 → 完整文本` 链路实现、测试覆盖、**真机通过**。
