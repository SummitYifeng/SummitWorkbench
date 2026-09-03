# ADR 0025 · 工作台 → 飞书双向写回——一键完成 / 行内编辑 / 审批新建会议

- 状态：✅ 已实现并真机核实（2026-09-03；ruff + format + mypy strict + 前端 tsc + pytest 458 项全绿）
- 日期：2026-09-03
- 里程碑：v0.3.0 · Web 工作台双向写回
- 依据：v0.2「待办任务/会议」只读呈现，完成必须去飞书、改任务/会议无入口；用户确认要「反向在工作台点完成」并扩展到审批新建会议与任务/会议行内编辑；日历权限由只读升级为读写并重新授权

## 背景与问题

v0.2 的 Web 工作台对飞书任务/日历是**单向只读**：简报把飞书任务、日历事件拉进当日快照展示，用户完成一条任务必须切去飞书点。v0.3 的诉求是补齐「工作台 → 飞书」的写回闭环，同时不破坏既有安全姿态（写回必须显式、可审计、vault 简报 Markdown 一字不动）。

## 决策

1. **飞书是任务与日程状态的唯一真源；本地只镜像当日渲染快照**。完成/编辑一律先 `PATCH`/专用端点写回飞书，成功后才调用 `signal_snapshot.mark_*` 把 `_vault/_signals/YYYY-MM-DD.json` 镜像一致（任务从待办移除并计入「最近完成」/标题截止同步，行动候选同步移除或改名，避免以「需要行动」重新冒出来）；任务不在当日快照时完成照常成功（飞书为准）。vault 简报 Markdown（Obsidian 侧唯一真源）不参与写回，保持一字不动。
2. **三个写回形态**：
   - **一键完成**：待办任务行尾「✓」→ `complete_task` → 快照移除 + 计入最近完成；
   - **行内编辑**：任务行/会议行尾「✎」→ `PATCH` 任务（`update_fields` 白名单内的 `summary/due`）或日历事件（标题/起止时间）→ 快照镜像；
   - **审批新建会议**：`RouteTarget.FEISHU_MEETING` 落点 + 候选 `start_at/end_at`（本地 naive `YYYY-MM-DDTHH:MM`，结束留空按开始 + 1 小时）→ 批准 +「应用（写回）」经 `MeetingCreator` 创建主日历定时事件，按候选 ID 审计幂等。
3. **日历写权限与契约（真机报错驱动修正）**：日历 scope 由 `calendar:calendar:readonly` 升级为 `calendar:calendar`（读写），需在开放平台开通并**重新授权一次**（旧 token 不带新 scope）；日历事件时间戳按官方契约用 **unix 秒字符串**。任务侧真机发现 `PATCH update_fields` 白名单**不含 `completed`**——完成改用官方专用端点 `POST /open-apis/task/v2/tasks/{guid}/complete`（首版按文档猜的 `PATCH completed:true` 真机被拒，本 ADR 固化正确端点）。
4. **会议行内编辑的快照演进**：`MeetingFact`/快照 `meeting_list` 附加 `event_id/start_ts/end_ts`（纯附加；旧快照无键则行内编辑钮不出现，全量/无时间戳事件不开放时间编辑）。
5. **范围**：不邀请参会人（日历 events attendees 二次调用不做）、不做任务删除 UI（provider `delete_task` 仅校验清理用）、取消完成不提供（`uncomplete` 端点留给将来）。

## 落地位置

- 领域/路由：`src/summit_workbench/domain/review.py`（`RouteTarget.FEISHU_MEETING`、候选 `start_at/end_at`、`is_actionable` 免项目）
- 审批页：`repositories/review_page.py` / `review_edit.py`（起止字段 Markdown 往返）、`workflows/review_apply.py`（`MeetingCreator` 注入、缺开始时间/创建器留页记失败）
- 飞书 provider：`providers/feishu/calendar.py`（`create_event/update_event` + 秒级时间戳换算）、`tasks.py`（`complete_task` 专用端点 / `update_task` / `delete_task`）、`client.py`（`patch/delete`）、`config.py`（日历读写 scope）
- Web：`webapp/api.py`（载荷模型 + 简报会议字段透出）、`webapp/app.py`（`/api/tasks/complete|update`、`/api/meetings/update`、审批编辑时间字段、`_build_meeting_creator`）
- 快照镜像：`repositories/signal_snapshot.py`（`mark_task_completed/mark_task_edited/mark_meeting_edited`）
- 前端：`web/src/brief-card.ts`（行尾 ✓/✎）、`web/src/main.ts`（弹窗表单/事件/草稿/落点选项）、`web/src/style.css`
- 测试：contract 日历/任务写契约、`review_apply` 建会议、快照镜像、端点（单元 458 项全绿）

## 验证

- 质量门 458 项全绿（ruff + format + mypy strict + 前端 strict TS + Vite 构建）。
- 真机（2026-09-03，权限开通并重新授权后）：日历建事件 → 改标题/起止时间 → 回读一致；任务改标题/截止 → 还原；一键完成建临时任务 → 面板完成 → 删除（闭环通过）。测试日程事件由用户确认后手动删除。
