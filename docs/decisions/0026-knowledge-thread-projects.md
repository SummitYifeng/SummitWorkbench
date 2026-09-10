# ADR 0026 · 业务线程 = vault 一等公民——知识线程项目（P0–P3）

- 状态：✅ 已实现并真机验收（2026-09-03；ruff + format + mypy strict + 前端 tsc + pytest 491 项全绿；P0/P1/P2 与 P3 第一批真机验收并装机，P3 停滞检测随 v0.4.0 装机后生效）
- 日期：2026-09-03
- 里程碑：v0.4.0 · 知识线程项目（需求再梳理结论 R2-A+）
- 依据：业务线（财务运营 / 教练财务 / 报名产品 / ERP 探索等）是「只开脑、不开文件夹」的**知识线程**——过去强行挂在某个 Work 文件夹/git 仓库下会污染仓库语义；六轮需求梳理确认「业务线程 = vault 一等公民」，不需要 Work 文件夹与 git（`docs/archive/background/REQUIREMENT_REDISCOVERY_THREAD_PROJECTS.md` §3 决策表 / §5 改造方案）

## 背景与问题

v0.2 的「项目推进精选」（ADR 0023）以 `_vault/projects/*.md` 建档 + `status: active` 为工作台项目口径，但**建档仍锚定 Work 文件夹**：新项目只能从 `work_root` 下的文件夹「加入工作台」，审批目标项目解析也只覆盖仓库项目名/别名。用户同时运转的多条**业务线程**（不是代码仓库）因此无处安放——要么被塞进无关仓库文件夹，要么根本没有入口记录。

## 决策

1. **知识线程 = vault 一等公民，不依赖 Work 文件夹与 git**。`POST /api/projects/create` 直接在 `_vault/projects/<id>.md` 建档（`type: project-main`，frontmatter `project/status/updated/aliases/title`）即入工作台；项目全集 = 文件夹项目 + 线程档案合并（`project_scan.scan_all_projects`），统一进首页推进卡、「项目」页、审批「目标项目」下拉与归档/恢复。**内部目录（下划线前缀）不进项目视野**（`project_scan.is_internal_dirname`：`_vault`、`_transcripts-inbox` 等）。
2. **审批路由扩展（承接 PRD L22/L23）**：审批「目标项目」解析覆盖线程规范 ID + 别名；新增落点 **`project-followup`（跟进事项）**——他人行动项写主档案 `## 跟进事项` 下的**待闭环责任记录**（`- [ ] ` 复选框，人工勾选闭环，不进本人待办），老档案首次写回自动补区块（`writeback._ensure_heading`）；知识线程的 inbox 落 `_vault/inboxes/<id>.md`（`type: project-inbox`），仓库项目仍写文件夹内 inbox。
3. **线程推进记录 = vault 笔记**（P1）：✎ 推进日志 → AI 消化（`prompts/log-digest.md`：摘要/涉及人/类型/下一步/决策）→ `_vault/logs/YYYY-MM-DD-NNN.md`（`type: work-log`，可关联 1..n 线程 `projects:[...]`，模型不可用只存原文 `status: draft`，绝不丢）；存产物 → `_vault/artifacts/<project>-NNN.md`（`type: thread-doc`，frontmatter `title/summary/kind`，kind ∈ 阶段总结/prd/背景包/timeline/other）；产物弹窗支持**本地文件导入**（`.md/.txt`：`runOpenPanel` 选择 + 拖放）与**一键转「当前状态」草案**（`POST /api/threads/state` → `writeback.set_project_status`，显式确认后写回并刷新 `updated`）。
4. **线视图 = 档案区块 + 时间线聚合**（P2）：`repositories/project_view.build_project_view` 从主档案取「当前状态 / 下一步 / 阻塞 / 跟进事项 / 决策记录」区块（跟进带「N 条待闭环」徽标），并把 `logs/`（work-log）、`artifacts/`（thread-doc）、`meetings/notes/`（meeting-note）中 frontmatter 命中该线程的笔记按日期聚合为时间线；视图内可直接日志/产物/刷新。**任何日志/产物/状态写入自动刷新关联档案 frontmatter `updated`**（`thread_notes._touch_projects_updated`），首页卡「更新 X」与停滞判定以此为唯一时钟。
5. **线程信号进简报与周复盘**（P2/P3）：采集改用项目全集（`scan_all_projects`）→ 线程「下一步」进主线推进、「阻塞」进防止停摆、未闭环跟进聚合为「跟进 X：…（共 N 条）」主线推进；已归档不产生信号。**内容停滞检测**：线程没有 git，「本周零提交」覆盖不到 → 以档案 `updated` 判停滞——距复盘周截止日 >14 天（`workflows/weekly/collect.THREAD_STALL_DAYS`，与首页卡「>14 天未更新」同口径）无更新且档案仍有阻塞/未闭环跟进（`project_view.project_archive_state`）时，周复盘「停滞项目」点名并派生「推进停滞项目 X」提议。
6. **项目显示名（P3）**：档案 frontmatter `title` = 显示名（`POST /api/projects/rename`）；不改规范 ID / 别名 / Work 文件夹 / git；卡片、项目页、审批建议下拉、第二大脑检索范围、日志/产物选择器统一显示显示名（与 ID 不同时标注 ID），线视图内「✎ 显示名」行内改名。
7. **frontmatter `updated` 读取归一（修复，停滞判定依赖）**：建档/写回生成的 `updated: 2026-09-03`（未加引号）会被 YAML 解析成 `date` 对象，str-only 判断会误读为空 → 新增 `repositories/vault.meta_date_iso`（str / date / datetime → `YYYY-MM-DD`）并接入 `project_scan` 与 `project_view`。

## 落地位置

- 项目全集/线程发现：`repositories/project_scan.py`（`scan_all_projects` / `thread_projects` / `is_internal_dirname` / `ProjectState.is_thread`）、`project_registry.py`（建档/激活/归档幂等）、`domain/vault.py`（`project-inbox` 类型 + project-main `## 跟进事项` 模板）
- 审批路由：`domain/review.py`（`RouteTarget.PROJECT_FOLLOWUP`）、`repositories/writeback.py`（`append_project_followup` / `append_thread_inbox` / `_ensure_heading`）、`workflows/review_apply.py`、`webapp/views.py`（落点标签）
- 线程笔记：`repositories/thread_notes.py`（work-log / thread-doc 落盘 + `_touch_projects_updated`）、`repositories/note_status.py`、`domain/threaddoc.py`、`repositories/project_view.py`（线视图聚合 + `project_archive_state`）
- Web：`webapp/app.py`（`/api/projects/create|rename|view`、`/api/threads/state|logs|artifacts`、审批目标下拉）、`web/src/main.ts`（线视图/日志/产物/显示名/文件导入/拖放）
- 周复盘：`workflows/weekly/collect.py`（`_collect_thread_stalls` + `_thread_stall_reason`）、`domain/weekly.py`
- 原生壳：`native/SummitWorkbench/PanelWindowController.swift`（`runOpenPanel`）、`AppMain.swift`（编辑主菜单/窗口焦点）

## 验证

- 质量门 491 项全绿（ruff + format + mypy strict + 前端 strict TS + Vite 构建）。
- 真机（2026-09-03）：4 条试点线程建档（FinanceOps / CoachFinance / EnrollmentProduct / ERPExplore，中文别名可解析）→ 审批候选路由到线程跟进事项与 inbox → 线视图/推进卡呈现 → 日志/产物入库刷新 updated → 显示名/状态草案写回；P0/P1/P2 与 P3 第一批验收通过并装机。内容停滞检测进周复盘为本版代码完成项，随 v0.4.0 装机后生效。
