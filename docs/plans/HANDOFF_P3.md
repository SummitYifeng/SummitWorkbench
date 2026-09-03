# P3 交接（新对话窗口从这里继续）

> 2026-09-03 由上一会话整理。目标：新对话能零成本接续，不必重读整段历史。

## 现状一句话

SummitWorkbench 已完成「业务线程 = vault 一等公民」改造 P0/P1/P2 + P3 第一批，全部真机
验收通过并装机（当前前端 `215658a3`）。产品仓库本次提交含全部代码/文档/测试；vault
（`YifengWorkKnowledge`）含约定更新、4 条试点线程档案与用户真实使用沉淀。

## 权威资料（先读）

1. `docs/background/REQUIREMENT_REDISCOVERY_THREAD_PROJECTS.md` —— 六轮需求梳理 + 决策表 §3
   + 改造方案 §5 + **实施进度 §9（P0 ✅ / P1 ✅ / P2 ✅ / P3 部分 ✅，含原生壳修复）**。
2. `docs/product/PRD.md`（权威规格；本次改造尚未回写 PRD——如需可把 §9 结论固化进 PRD/ADR）。
3. `docs/product/WEB_USAGE_GUIDE.md`（已同步新功能使用说明）。

## 已实现（真机验收过）

- P0：知识线程项目（无文件夹建档/registry 全集/首页/审批下拉）、内部目录隔离、
  审批「跟进事项」落点 + 线程 inbox（`_vault/inboxes/`）、4 条试点线程
  （FinanceOps / CoachFinance / EnrollmentProduct / ERPExplore）。
- P1：✎ 日志（文本→AI 摘要→多线程 work-log）、存产物（thread-doc + title/summary/kind）、
  第二大脑按线程检索。
- P2：线视图（点项目名：档案区块 + 时间线聚合）、写入自动刷新 `updated`、
  线程信号进简报（下一步/阻塞/未闭环跟进）、>14 天未更新提示、重新生成按钮。
- P3 第一批：产物一键转「当前状态」（`POST /api/threads/state`）、本地文件导入（粘贴/
  label 选择/**拖放**）、项目显示名（`POST /api/projects/rename`，frontmatter `title`，
  全局显示名 + 线视图「✎ 显示名」）。
- P3 末项（代码+测试已完成，待装机复验）：**内容停滞检测进周复盘**（线程 >14 天无更新 +
  有阻塞/未闭环跟进 → 停滞项目点名，`weekly/collect.py`）；顺带修复未加引号 `updated`
  （YAML date 对象）读不到的归一化问题。
- 原生壳（LSUIElement）：`runOpenPanel`（文件选择）、最小「编辑」主菜单（⌘V 等）、
  窗口焦点交 webView。

## 质量门（推送前全绿）

pytest 全绿（491，含线程/简报/状态/改名/周复盘停滞检测测试）、mypy strict 119 文件、ruff 全绿、
web 构建通过、macOS App 打包安装通过（`scripts/build-macos-app.sh` + `install-macos-app.sh`）。

## 剩下的 P3 待办（可选，按需挑选）

1. ✅ **内容停滞检测进周复盘**（2026-09-03 完成，pytest 491 全绿）：线程 N 天无更新但有未决/
   未闭环跟进时，周复盘（`workflows/weekly/`）点名；实现 = `weekly/collect.py::_collect_thread_stalls`
   + `_thread_stall_reason`（阈值 `THREAD_STALL_DAYS = 14`，与首页卡「>14 天未更新」同口径；
   参考 `workflows/brief/collect.py` 的 `_thread_extra_signals` 与 `project_view.project_archive_state`）。
   顺带修复：`updated` 未加引号时 YAML 解析成 date 对象被丢弃 → `repositories/vault.py::meta_date_iso`
   统一归一（project_scan / project_view 已接入）。
2. 把本次改造结论回写 PRD/ADR（知识线程项目定义、L22 路由扩展、显示名/状态草案语义）。
3. CHANGELOG 补 v0.4.0 条目（当前未加）。
4. 让系统陪你跑几天后再定其它体验改进。

## 工程提醒

- App 是自包含包：**改 Python/前端/原生 Swift 后都要** `scripts/build-macos-app.sh`（内含
  npm build + PyInstaller + swiftc）→ `scripts/install-macos-app.sh dist/SummitWorkbench.app
  --replace-running`，再请用户从启动台打开。
- 从终端 `open` 拉起 App 会把会话环境带进 GUI 进程导致其服务卡住——验证请用启动台，
  或手动跑 `SummitWorkbenchServer --port <其他>` 做接口冒烟后 kill。
- vault 侧（conventions.md、线程档案等）属用户数据，随 `YifengWorkKnowledge` 推送/每日自动提交。
