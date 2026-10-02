# SWB next-version entry and side-effect inventory (W0)

Inventory baseline: `c89677c`; see `ONEDRIVE-WORKBENCH-IMPLEMENTATION-PLAN.md`. New contract: `SWB-WORKSPACE-CONTRACT-v1.md`. “Git dependency” below means work-library Git; the source repository's Git is not in scope for removal.

| Surface / entry | Current implementation and writes | Model / external effects | Approval and Phase 1 disposition | Work-library Git dependency |
| --- | --- | --- | --- | --- |
| Web quick capture | `routers/capture.py`, `workflows/capture.py`, `repositories/inbox.py` → inbox | Explicit capture/suggest can call LLM; save is local | Keep as “记点什么”; capture remains pending until review | MutationRuntime commit/push to remove |
| Journal log / thought | `routers/journal.py`, `thread_notes.py`, `thought_notes.py` | None | Keep as shortcuts under “记点什么”; both formal writes require current-version approval | MutationRuntime commit/push to remove |
| Meeting import / processing | `routers/meetings.py`, `webapp/meeting_import.py`, `workflows/meetings/*`, meeting state/archive | Explicit process calls LLM; transcript import is local | Keep under “导入会议”; transcript excluded; extracted content reviewed | MutationRuntime commit/push to remove |
| Inbox promote / suggest | `routers/inbox.py`, `repositories/inbox.py`, `thought_notes.py`, `writeback.py`, `review_apply.py` | Suggest calls LLM; Feishu task target creates external task via outbox | Keep; fold into 3 destinations; no default selection | MutationRuntime commit/push to remove |
| Artifact import / save | `routers/threads.py`, `thread_notes.py`, review artifact flow | Optional organize calls LLM; file selection/read local | Keep under “存入文档／产物”; preserve full text; formal version requires approval | MutationRuntime commit/push to remove |
| Project create / status / archive | `routers/projects.py`, `writeback.py`, `note_status.py`, project registry/scan | No model; no remote action | Keep contextual editing; content changes require approval; archive lifecycle separate | MutationRuntime and project discovery scan Git repos to remove |
| Meeting review / apply | `routers/review.py`, `review_apply.py`, meeting note renderer, task outbox | Feishu task POST via durable outbox | Keep; consolidate into the three review destinations | MutationRuntime commit/push to remove |
| External action retry/recheck | `routers/review_apply.py`, `external_action_outbox.py`, `review_apply.py` | Feishu read/write; unknown result requires read-side reconciliation | Keep Feishu tasks only; preserve no-blind-retry and account binding | MutationRuntime commit/push to remove |
| Brief / weekly | Web `brief.py`; CLI `brief.py`/`weekly.py`; `workflows/brief/*`, `weekly/*`; launchd `automation_worker.py` | Feishu reads; brief ranking may call LLM; writes local app-support display files and workspace heartbeat/snapshots | Keep output; only confirmed work facts; remove device-role background writer and ensure user-visible lifecycle/context | Heartbeat and some snapshot writes currently committed; remove commit/push chain |
| Feishu calendar and existing tasks | `providers/feishu/calendar.py`, `tasks.py`, state + task routes | Read, edit, complete existing task/calendar events | Keep reads and explicit direct operations; task creation only via approved destination; audit scheduled-event creation before retiring | Some mutations currently flow through MutationRuntime |
| Settings / workspace onboarding | `routers/settings*.py`, `workspace.py`, `onboarding.py`, `workflows/onboarding.py`, native directory panel | Feishu/model config and OAuth; onboarding may initialize/commit | Keep workspace/model/Feishu; localize credentials; no work-library remote/SSH/proxy/role UI | Onboarding commit + remote configuration to remove |
| Sync / conflict / undo | `routers/sync*.py`, `workflows/sync*`, `repositories/*git*`, `routers/undo.py`, `cli/sync.py` | Git network fetch/push, conflict writes | Retire product UI, routes and work-library call chain; keep source-control tools for SWB repository | This surface is the old work-library Git dependency |
| CLI / doctor / launchd | `cli/*`, `scripts/install-launchd.sh`, `automation_worker.py` | Diagnostics, Feishu/model calls, scheduled writes | Keep diagnostics, validation, manual brief/weekly; retire git sync/undo, role takeover and persistent background writer | CLI sync/review and scheduled auto-commit need removal |
| App update path | `updates/feed.py`, native `AppDelegate` / automation bridge, scripts | GitHub feed check/download/install | Disable default GitHub check/download; retain manual DMG install guidance | No workspace Git; external GitHub dependency retired by default |
| Support / recovery | diagnostics, operation receipts, local drafts, review audit, restore flows | Local file writes; no provider action | Keep local recovery and portable operation receipts; secrets and absolute paths excluded from portable files | Mutation commit currently applies to some receipts |

## Explicit disposition for adjacent operations

- Keep Feishu calendar listing and direct edits/completion of existing tasks; retain their existing task-date behavior.
- Audit scheduled-event creation in W0 source paths: it is not a fourth review destination. Retire it if it is an unreviewed creation path; task creation proceeds only through “创建飞书任务”.
- Keep brief and weekly display generation, but remove unattended device-role semantics and work-library Git commits.
- Keep CLI status, diagnosis, validation and explicit maintenance; retire workspace Git sync and undo commands.
- Retain Git exclusively for the SWB source repository, development, and local artifact version stamping.
