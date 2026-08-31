# ADR 0011 · M1-4 集中审批与写回

- 状态：✅ 实现与人工审批解析完成；⏳ 待项目 ID 解析与真实写回验收
- 日期：2026-08-31
- 里程碑：M1-4（集中审批与写回）
- 依据：`docs/plans/DEVELOPMENT_PLAN.md` §6 M1-4；PRD L21/L22/L23

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
