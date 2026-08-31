# ADR 0007 · M0-10 飞书会议纪要拉取

- 状态：note → 逐字稿链路已实现（端点官方核实），真机冒烟待用户授权 + 提供 note_id
- 日期：2026-08-31
- 里程碑：M0-10（会议纪要 API 冒烟）
- 依据：`docs/plans/DEVELOPMENT_PLAN.md` §5 M0-4/M0-10；PRD L14/L15；ADR 0004（此处兑现其推迟项）

## 已核实端点（官方文档，2026-08）

| 步骤 | 方法 / URL | scope |
|---|---|---|
| 取纪要产物 | `GET /open-apis/vc/v1/notes/{note_id}` | `vc:note:read` |
| 读文档正文 | `GET /open-apis/docx/v1/documents/{doc_token}/raw_content` | `docx:document:readonly` |

`notes/{note_id}` 返回 `artifacts[]`：`artifact_type=1` 纪要文档、`artifact_type=2` **逐字稿文档**；
各带 `doc_token`。取 type=2 的 doc_token 读其 `raw_content` 即完整逐字稿纯文本。均支持 user_access_token。

## 决策

- `FeishuNoteSource.fetch_transcript(note_id)` 实装为：`get_note` → 选 `artifact_type=2` 的 doc_token
  → `read_doc_text`。**无逐字稿产物时显式报错**，不拿智能纪要冒充逐字稿，可降级到本地导入兜底（L14）。
- **按 note_id 驱动**。「会议 → note_id」的自动发现（需 vc 会议 scope 与会议列表/详情端点）留待 M1-1；
  M0-10 冒烟用一场真实会议的 note_id 直接验证 note → 逐字稿。
- 默认 scope 增加 `vc:note:read`（`docx:document:readonly` 已在）。之前误猜的
  `vc:meeting:readonly` / `minutes:minutes:readonly` 作废。

## 交付

- `providers/feishu/meetings.py`：`FeishuNoteSource.get_note / read_doc_text / fetch_transcript`；
  `TranscriptResult` 增加 `doc_token`，`meeting_id` 改可选。
- CLI `wb feishu note-transcript --note-id <id>`（M0-10 冒烟入口）。
- 契约测试（MockTransport）：选对 type=2、读正文、无逐字稿产物报错、note 实体缺失报错。
- 默认 scope 更新；ruff/mypy strict/pytest(88) 全绿。

## 尚待用户完成（真机冒烟）

1. 在飞书控制台给应用加 **`vc:note:read`** 权限（`docx:document:readonly` 应已开通）。
2. 重新授权取得含新 scope 的 token：`wb feishu authorize-url` → `login --code` →（可 `smoke` 复核）。
   config 的 `scopes` 若显式列写，需补上 `vc:note:read`；若未列写则用已含该项的内置默认。
3. 取一场真实会议的 `note_id`，运行 `wb feishu note-transcript --note-id <note_id>` 验证取回逐字稿。
   若该会议无逐字稿产物或 API 不可用，按 L14 走 `wb feishu import-local` 本地兜底。

## 验收对照（M0-10）

- ✅ `note_id → 逐字稿文档 → 完整文本` 链路实现并测试覆盖，端点官方核实。
- ⏳ 用真实历史会议冒烟：待用户加 `vc:note:read` + 重新授权 + 提供 note_id。
- ⏳ 「会议 → note_id」自动发现：M1-1（需 vc 会议 scope 与会议列表端点）。
