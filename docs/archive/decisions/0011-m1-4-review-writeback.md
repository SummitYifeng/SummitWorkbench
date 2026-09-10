# ADR 0011 · M1-4 集中审批与写回

- 状态：✅ 实现、人工审批解析与项目名解析完成；⏳ 待真实项目别名录入与显式写回验收
- 日期：2026-08-31
- 里程碑：M1-4（集中审批与写回）
- 依据：`docs/archive/plans/DEVELOPMENT_PLAN.md` §6 M1-4；PRD L21/L22/L23

## 决策

- **候选边界**：第一版只从明确决策与明确行动项生成候选，普通事实不会被推断成项目状态变化。
  候选 ID 由会议幂等键 + kind + index 派生，重跑稳定。
- **审批语法**：`review/meetings.md` 按会议分组；`- [ ]` 待确认、`- [x]` 批准、
  `~~整条候选~~` 拒绝（兼容可选的 `#ignore`）。正文、target_project、route、due_date 可原地编辑；
  AI 原值以隐藏元数据保留。
- **刷新保护**：刷新只新增未知 ID，已有勾选状态和人工编辑原样保留。语法错误、重复 ID 时拒绝覆盖。
- **应用安全**：`wb review apply` 默认 dry-run 且零写入；只有显式 `--apply` 才执行业务写回。
  缺目标/依据/route 或目标文件不存在的批准项留在审批页并显示 error。
- **路由与审计**：决策/无期限明确下一步写项目主笔记；期限行动项创建飞书 Task v2；其余 route
  支持项目/global inbox。批准与拒绝均归档 AI 原值、用户最终值、目标和结果。
- **幂等与部分失败**：本地 Markdown 写入候选 marker；飞书请求使用候选 ID 派生 `client_token`；
  审批执行另有 append-only JSONL 账本。成功项立即记账并移出活动页，失败项保留，重跑不重复成功项。

## 项目名解析（补齐缺口）

`repositories/project_registry.py` 扫描 `_vault/projects/*.md`，以每篇 `project-main` 笔记的
`project` frontmatter 为规范 ID，可选 `aliases: [...]` 登记自然语言别名（如「网课系统」）。
解析器**只向上升级**别名→规范 ID（大小写/空白不敏感），解析不到时返回 `None`、目标原样保留，
沿用「目标文件不存在 → 留在审批页标 error」的安全行为，绝不猜错目标或造新项目名。
接入两处：候选生成（`review_candidates`，页面一开始即显示规范 ID 与正确 route）与
`wb review apply`（人工在审批页填的别名在应用前解析回规范 ID）。别名事实源在项目笔记
frontmatter，加别名不改代码。

## 补充决策（2026-09-01）：未匹配项目 = 零摩擦捕获，而非报错

真实场景是「多数会议未必对应已导入项目；workbench 会持续梳理出新项目，新项目才匹配后续会议」。
因此把「解析不到项目」从**阻塞错误**改为**兜底捕获**：

- 候选生成时未匹配到已建项目的（含模型对未建项目的猜测）一律记 `unresolved`，路由到全局
  inbox，不再 dead-end 在不存在的项目文件上。
- `ApprovalCandidate.is_actionable` 改为 route 感知：全局 inbox 落点不要求已解析项目即可写回；
  项目主笔记/项目 inbox 仍要求已建项目。
- 全局 inbox（`_vault/inbox.md`）作为主兜底落点，缺失时按 schema 自建。
- 新增 `wb project new/list`（`repositories/project_registry.create_project_note`）：在第二大脑侧
  快速为新项目建档（**不碰任何 GitHub 仓库**），建档后即可被后续会议审批解析命中。审批页里
  批准一条指向未建项目的候选时，错误提示引导先 `wb project new`。

## 飞书适配

依据飞书官方服务端 SDK 的 Task v2 类型定义：创建接口 `POST /open-apis/task/v2/tasks`，请求使用
`summary`、可选 all-day `due`、`client_token`，响应读取 `task.guid/task_id`。CLI 只在显式 `--apply`
且实际存在 `feishu-task` route 时才按需刷新用户令牌并调用接口。

## 验收

- Ruff、mypy strict、pytest 166 项全绿；覆盖编辑保留、注释兼容、dry-run 零写入、批准/拒绝、
  原值/最终值审计、部分失败、错误回显、状态收口、本地/飞书幂等与 Task v2 HTTP 契约。
- 真实 vault：扫描 1 篇 pending-review 笔记，生成 5 条候选（3 decision / 2 action-item），
  5/5 有有效目标和证据，审批页解析零错误；未勾选状态执行 dry-run，业务写回为零。
- 用户已在真实审批页完成批准、拒绝和两处原地修改；解析器正确保留 AI 原值和人工最终值。
- dry-run 识别 1 条批准与 1 条拒绝，并因自然语言项目名“网课系统”未对应到实际主笔记
  `HIC_WebClass_Chinese_Final` 而安全拒绝批准项。下一步补齐项目 ID 解析，再显式应用并核对重跑幂等。
