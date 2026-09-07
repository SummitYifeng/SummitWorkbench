## [Unreleased] - 2026-09-07

> P1-07D 已完成：Studio + Air 双设备真机验收闭环（同一候选包 build 23，SHA-256 见
> `release-metadata.json`），build 24 已在 Studio 与 Air 完成覆盖安装与增量冒烟，进入 P2-01B 的前置门已解除。

- P2-01B 已完成：仅对既有 thread activity 接入 `shadow-read → dual-write`、确定性投影对比、
  差异诊断、一致性报告与回退开关；不迁移 inbox、会议决策或项目正文。
- P2-02 实现已收口；build 28 已在 Studio + Air 完成 Markdown、未知视图与 binary 的普通双父
  恢复、脱敏审计、普通 push 和最终同 HEAD。独立复核发现现场审计的事件/已登记视图计数均为
  `0`，且三条保护分支缺少可复核现场记录，因此 P2-02 继续保持 `[~]`，待同一 build 28 补验。
- build 28 现场追加 dual-write 时发现打包服务只提交 event、遗漏同事务的 legacy Markdown；已在
  `run_local_mutation` 增加主返回路径兜底并补 Dulwich 回归测试，build 29 重新打包，P2-02 现场验收
  改用 build 29。
- 当前主线质量门独立复核：`826 passed, 1 skipped`，覆盖率 `82.15%`，另有 packaged App smoke
  `1 passed`；ruff、格式检查、mypy、前端契约与生产构建、依赖锁、release 验证和 secret scan 均通过。

- P2-02：未知 `_views/**` 不再误判为可自动重建；改为人工 `preserve-both`，保留确定性的
  `.remote` 副本，并在保护态 UI 只展示安全选项；已定义的 thread activity 视图继续在
  临时目录确定性重建。
- P2-02：恢复双父提交成功后，脱敏审计写入失败会单独报告为审计失败，不再把已完成的
  恢复误报为可重试失败；前端同时区分恢复提交、普通同步与审计状态。

- build 24 内部 arm64 DMG 已由干净提交 `ac97db4aebb53147a394d83a34d9ed978d42b91e` 生成并通过 App/DMG 离线验证；产物 `dist/releases-build24/0.4.3/arm64/SummitWorkbench-0.4.3-arm64-INTERNAL-DEV.dmg` 的 SHA-256 为 `ef02907d637be755fe825d60b58fea8e1f67fe47cebcf03e782d2caf6f0e6590`。Studio 与 Air 增量检查均确认 build 24、HTTPS remote、preflight、基础同步、secondary profile、简报/周报友好跳过及零写入。

- 修复 DulwichGitBackend `fetch()`/`push()` 传 URL 而非 remote 名，导致
  `refs/remotes/origin/*` 永不更新：push 成功后 `ahead/behind` 与 `pending_wb_commits`
  不再永久停留在 1（`local-ahead` 假象），状态机不再在 ready / local-ahead 之间回退。
- 修复打包 App 从 Finder/LaunchServices 启动时没有代理环境变量、dulwich 直连
  `github.com` 被阻断的问题：无 env 代理时回退 macOS 系统代理（`scutil --proxy`），
  TLS 校验保持 `CERT_REQUIRED` + bundled CA，绝不关闭校验。
- acceptance preflight 报告完整 build identity（`version/build/frontend_build/git_revision`）；
  fetch 失败输出稳定脱敏码（auth/tls/certificate/proxy/credentials-unavailable/network/
  backend）与 host/credential/CA/proxy 诊断，不含 PAT、完整 URL 路径或本机路径。
- 新增 `GitCertificateError` / `GitProxyError` / `GitCredentialsUnavailable` /
  `GitBackendRuntimeError` 与 `classify_git_error()` 稳定错误码，区分证书、代理、凭据缺失、
  后端运行时与网络不可达。
- Air「连接已有工作台」向导新增 PAT 输入：clone 使用短生命周期 credential_resolver，
  确认后才写入 workspace-scoped Keychain；新增 `connect-remote` 预检流，允许尚未存在的
  clone 目标目录；confirm 回填 profile 的 `git_remote_url`。PAT 绝不进 draft、日志或 URL。
- secondary 的自动化「立即运行」与手动简报/周报生成改为友好跳过提示（`200` + `ok=true`），
  不再显示红色 `ApiError`；写入仍被 automation 角色门控跳过，绝不执行。
- 同步发现不再把 onboarding 遗留的 `.summit-workbench-remote-*` staging 目录当 workspace
  仓库同步。
- 质量门：`823 passed, 1 skipped`；ruff check / ruff format / mypy 通过；build 23 打包集成与
  TLS 诊断通过。Studio（automation-primary）与 Air（secondary）用同一 DMG 完成 remote
  preview/apply、schema 迁移、preflight 全 PASS、Studio↔Air 双向同步、Air 离线写入恢复、
  双端离线冲突进入 `diverged-protected`（不 force/reset/rebase/stash、不丢数据）。

## [0.4.3-rc.5] - 2026-09-06

- 原生 App 重启时可根据 runtime record 与精确 server 可执行路径识别并终止自身遗留进程；
  未知进程仍不会被接管或终止。

## [0.4.3-rc.4] - 2026-09-06

- 修复设置中心 remote preview/apply/rollback 请求缺少 JSON `Content-Type` 导致后端拒绝的问题。

## [0.4.3-rc.3] - 2026-09-06

- 允许旧 schema 的只读工作区执行受控 remote preview/apply/rollback，打破“迁移要求 HTTPS、
  HTTPS 转换又被只读门阻止”的循环；其它写入仍保持只读保护。

## [0.4.3-rc.2] - 2026-09-06

- 候选 release 的 feed 与 DMG URL 改为按 tag 自动推导，继续使用 draft/prerelease 且不更新
  `latest`。

## [0.4.3-rc.1] - 2026-09-06

> 候选版本，尚未稳定发布；等待一次 Studio + Air 双设备真机验收。

- P1-07D：生产同步正式限定 HTTPS remote；SSH/scp-style remote 明确返回
  `remote_scheme_unsupported`。
- 设置中心新增可预览、可回滚的 GitHub SSH → HTTPS 转换事务与脱敏 acceptance preflight。
- 修复 Dulwich clean-worktree 判定，补充 ignored directory、未跟踪文件、已跟踪删除和双设备
  schema/sync/divergence 回归。
- 候选 release 使用 draft/prerelease 渠道，不更新 `latest`；公开更新仓库只提供完整性，不
  提供保密性。

## [0.4.2] - 2026-09-06

修复 macOS 自包含 App 首次创建 workspace 时找不到 PyInstaller 内置 vault 模板的问题；
补充 packaged App 的真实 workspace 创建集成测试。

## [0.4.1] - 2026-09-04

维护加固发布（稳定性审计 P0/P0'/P1，ADR 0027）。核心问题不变（外置执行管理层 + 第二大脑）；本版收掉三类真问题：**写路径并发丢更新、全库无撤销、停滞点名被机器活动刷失明**。

### 修复

- **写路径并发加固（P0）**：全库所有「读文件 → 变换 → 整文件原子重写」的 RMW 原语（审批页裁决/批量/修改与 refresh、inbox 与项目档案追加、set_project_status、当日笔记与周复盘、当日快照镜像、线程日志/产物、项目建档/激活/归档、review sweep、审批页状态收口）整体放入工作区锁（workspace_lock(vault_dir.parent)，与 publish_brief / sync 同一把 .wb.lock；**锁只包文件临界区，绝不跨 LLM/网络调用**；锁忙对用户可见——CLI 输出「工作区忙，稍后重试」并 exit(1)，面板返回可见失败）。裸 write_text 全量改 atomic_write_text（当日笔记可能含用户锚点外手写内容，断电/kill 不再留半截文件）。审批 apply_meeting_review 收尾改**乐观合并**（P0-5）：apply 执行外部写回期间用户在审批页的并发勾选/编辑不再被整页重写吞掉——收尾重读最新页，只移除本次执行且最新页中未变的候选，被并发改动的候选留在页上（账本幂等，下次 apply 清理不重复执行）。幂等账本（_signals/review-actions/log.jsonl）改逐行 Pydantic 容错读（ExecutionRecordRow），一条半截行只告警并隔离进 .quarantine，不再让 apply 幂等判定整体崩溃。线程日志/产物序号分配与落盘同锁且写前重查目标存在，并发写入不再算出同一序号静默覆盖。
- **系统写回自动留痕 + 面板撤销（P0'）**：每次系统侧写回成功后自动 git 提交（**显式路径**、绝不 add -A、消息带 wb: 前缀、非 git 仓库优雅降级不抛错、失败转可见状态不阻断写回）——覆盖面板捕捉（inbox）、推进日志/产物与关联档案、状态确认、审批应用（写回目标 + 审批页 + 审计归档）、项目建档/激活/归档/改名、任务完成/编辑与会议编辑（当日快照镜像）、逐字稿导入，以及 wb review sweep --apply（CLI 顺带）；launchd brief/weekly 沿用既有 publish，不重复提交。顶栏新增 **「↩ 撤销」**：最近 N 次 wb: 自动提交（含触碰文件）→ 单提交 before/after 差异预览 → 一键还原（等价 git revert，只作用于 vault 文件；**飞书侧已产生的副作用——已建任务/会议、已完成状态——不可撤销**，按钮旁与确认弹层文案明示；目标文件有未提交人工改动时拒绝还原）。新增 repositories/autocommit.py 与 GET /api/undo/history、GET /api/undo/diff、POST /api/undo/revert。
- **停滞信号语义修复（P1）**：档案 frontmatter updated 收窄为**实质更新**，只在建档/激活/归档/改名与用户显式确认的状态写回（threads/state）时刷新；日志/产物等机器活动改刷新新字段 **activity_at**（活动痕迹，读侧经 meta_date_iso 归一，project_scan / project_view / /api/state 载荷与前端同步）。首页线程卡「最近活跃」读 activity_at（缺省回退 updated）；「>14 天未更新」提示与周复盘停滞点名继续读 updated——AI 收尾的高频自刷新不再让停滞点名失明。

### 质量

- 新增并发写（T1–T6：并发裁决/apply 乐观合并/inbox 追加/线程序号/简报×完成镜像/坏账本行）、自动提交与撤销（U1–U4）与停滞语义（S1/S2）测试，另加**跨进程互斥**集成测试（两个真实子进程并发写当日笔记 + 快照，无交错）；全套 **514 项全绿**（较 491 净增 23）。ruff + format + mypy strict（200 文件）+ 前端 strict TS + Vite 构建通过；桌面 App 已重新打包装机。M3（带上下文启动与收尾）仍是下一步。

## [0.4.0] - 2026-09-03

发布版。核心问题不变（外置执行管理层 + 第二大脑），v0.4.0 完成需求再梳理结论 R2-A+ 的落地：**业务线程 = vault 一等公民**——知识线程（FinanceOps / CoachFinance / EnrollmentProduct / ERPExplore 等试点）不再依赖 Work 文件夹与 git，以 `_vault/projects/*.md` 档案建档即入工作台；线程有自己的推进日志（work-log）、AI 产物（thread-doc）、收件箱与**线视图**（档案区块 + 时间线聚合），信号（下一步 / 阻塞 / 未闭环跟进 / 长期无更新）进入晨间简报与**周复盘停滞点名**，第二大脑可按线程检索。桌面 App（LSUIElement）补上原生文件选择与编辑快捷键。质量门 491 项全绿。M3（带上下文启动与收尾）仍是下一步，未在本版开始。

### 新增

- **知识线程 = vault 一等公民（P0）**：线程**无需 Work 文件夹 / git**，`POST /api/projects/create` 直接在 `_vault/projects/` 建档（`type: project-main`）即入工作台；registry 全集（`scan_all_projects` = 文件夹项目 + 线程档案合并）统一进首页推进卡、「项目」页与审批「目标项目」建议下拉；下划线前缀目录（`_vault`、`_transcripts-inbox` 等）是系统内部目录，不进项目视野。已建档 4 条试点线程（FinanceOps / CoachFinance / EnrollmentProduct / ERPExplore，含中文别名解析）。归档/恢复只动档案 frontmatter，文件夹与 git 零触碰。
- **审批路由扩展（P0，承接 L22）**：审批「目标项目」下拉与写作候选现支持已建档的**知识线程**；新落点 **「跟进事项」**（`project-followup`）把他人行动项写成主档案 `## 跟进事项` 下的**待闭环责任记录**（`- [ ] ` 复选框，人工勾选闭环，不进本人待办）；老档案首次写回自动补区块；知识线程的 inbox 落 `_vault/inboxes/<project>.md`（`type: project-inbox`），仓库项目仍写文件夹内 inbox。
- **✎ 推进日志（P1）**：线程/项目卡与线视图内「✎ 日志」粘贴推进文本（与谁沟通、定了什么、下一步），可勾选**多个线程/项目** → AI 消化为摘要（`prompts/log-digest.md`：摘要/涉及人/类型/下一步/决策）→ 写 `_vault/logs/YYYY-MM-DD-NNN.md`（`type: work-log`，`projects:[...]` 多线程 scope）；模型不可用只存原文（`status: draft`），绝不丢。
- **存产物（P1/P3）**：视图内「存产物」把与 AI 长对话产出的**阶段总结 / PRD / 背景包 / 时间线**全文存进所选线程（`_vault/artifacts/<project>-NNN.md`，`type: thread-doc`，frontmatter 自动命名 + `title/summary/kind` 摘要索引），之后第二大脑按线程可检索；产物弹窗支持 **📄 选择本地文件**（.md/.txt，`runOpenPanel`）与**拖放**（全环境可用），存量文档零成本收进线视图；勾选「同步更新主档案当前状态」可把产物摘要一键写为档案「当前状态」草案（`POST /api/threads/state`，显式确认后写回并刷新 `updated`）。
- **线视图（P2）**：点项目/线程名打开 = 档案区块（当前状态 / 下一步 / 阻塞 / 跟进事项 / 决策记录，跟进带「N 条待闭环」徽标）+ **时间线**（该线程的 logs / artifacts / meetings 按日期聚合，一屏看全）；视图内可直接「✎ 日志 / 存产物 / 刷新」。日志或产物入库自动刷新关联档案 frontmatter `updated`（首页卡「更新 X」即时）。
- **线程信号进简报与周复盘（P2/P3）**：线程「下一步」进今日简报**主线推进**、「阻塞」进**防止停摆**、未闭环跟进聚合为「跟进 X：…（共 N 条）」主线推进；已归档线程不产生信号。线程卡 >14 天无更新显示「⚠ N 天未更新」；**内容停滞检测进周复盘**——线程距复盘周截止日 >14 天无更新（`THREAD_STALL_DAYS`，与卡片同口径）且档案仍有阻塞/未闭环跟进时，周复盘「停滞项目」点名并派生「推进停滞项目 X」提议。
- **项目显示名（P3）**：`POST /api/projects/rename` 写档案 frontmatter `title`（显示名，不改规范 ID / 别名 / Work 文件夹 / git）；卡片/项目页/审批建议/第二大脑范围/日志与产物选择器统一显示显示名（不同于档案 ID 时标注 ID）；线视图内「✎ 显示名」行内改名。
- **桌面 App 原生壳（LSUIElement）**：`runOpenPanel`（自绘 NSOpenPanel）解决 WKWebView 在 accessory 应用下 `<input type="file">` 不弹系统面板；补最小「编辑」主菜单（⌘V 等路由第一响应者）；窗口焦点交 webView。

### 修复

- **frontmatter `updated` 读取归一（P3 内容停滞检测依赖）**：建档/写回产生的 `updated: 2026-09-03`（未加引号）会被 YAML 解析成 `date` 对象，`project_scan`/`project_view` 的 str-only 判断会把它当空丢弃 → 新增 `repositories/vault.py::meta_date_iso` 统一归一到 `YYYY-MM-DD` 字符串（str / date / datetime 同值同型），线程卡「更新」、>14 天未更新提示与周复盘停滞判定由此都能读到真实的最后更新时间。

### 质量

- 线程扫描 / 审批落点 / 线视图 / 简报线程信号 / 显示名与状态 / 周复盘停滞检测等新增测试，全套 **491 项全绿**；ruff + format + mypy strict（src 119 文件）+ 前端 strict TS + Vite 构建通过。P0/P1/P2 与 P3 第一批经真机验收并装机（前端 `215658a3`）；内容停滞检测进周复盘（本版代码完成，随本版装机后生效）。

## [0.3.0] - 2026-09-03

发布版。核心问题不变（外置执行管理层 + 第二大脑），v0.3.0 把「工作台 → 飞书」的**双向写回**补全：在 v0.2 只读呈现（读任务/日历进简报）之上，现在可以在工作台**一键完成 / 行内编辑**飞书任务、**行内编辑**日历会议，并能在审批时把会议结论落成**新建日历日程事件**；飞书始终是任务与日程状态的唯一真源，本地只镜像当日渲染快照、vault 简报 Markdown 一字不动。日历权限由只读升级为**读写**（`calendar:calendar`，需重新授权），全部写回端点经真机验证（2026-09-03：建日程 / 改会议标题与起止时间 / 改任务标题与截止 / 一键完成契约修正）。质量门 457 项全绿。M3（带上下文启动与收尾）仍是下一步，未在本版开始。

### 新增

- **工作台内一键完成飞书任务（反向写回）**：v0.2「待办任务」默认只读、完成必须去飞书；现在每行最右新增小圆钮「✓」——点击即 `PATCH` 设置任务 `completed_at`（毫秒时间戳，`update_fields=["completed_at"]`，真机收敛的完成形态）把任务在**飞书侧**标记完成（真源），成功后把当日**渲染快照**镜像一致（该任务从 `task_list` 移除并计入 `completion_list`「最近完成」、引用它的行动候选一并移除，避免以「需要行动」重新出现），前端刷新即消失；任务不在当日快照时完成照常成功（飞书为准）。vault 简报 Markdown 与 Obsidian 阅读体验一字不动。新增 `providers.feishu.complete_task`（FeishuClient 增 `patch`/`delete`，`delete_task` 供校验清理）、`repositories.signal_snapshot.mark_task_completed`、`POST /api/tasks/complete`（`TaskCompletePayload`）；快照镜像按 `task_id`↔`feishu-task:{guid}` 大小写不敏感匹配，旧格式快照零写入降级。前端 `web/src/brief-card.ts` 待办行渲染 + `main.ts` 点击处理 + CSS（`.bf-done` 小圆钮）；使用指南同步（「今日」页与 FAQ）。质量门新增 7 项测试（Feishu PATCH 契约、快照镜像仓储、`/api/tasks/complete` 端点含失败/缺 id/无快照分支），全套 **440 项全绿**；ruff + format + mypy strict 通过（顺带修复 mypy 2.3.1 下既有 6 处严格类型报错：`webapp/api.py` 简报载荷 3 处与 `test_brief_domain.py` 3 处）。
- **审批新增「新建会议」落点 + 今日任务/会议行内编辑（双向写回飞书）**：审批候选在「修改」里可选落点 **「新建会议」**（`RouteTarget.FEISHU_MEETING`），并填**开始/结束时间**（结束留空按开始 + 1 小时）；批准并「应用（写回）」即经日历 v4 `POST .../calendars/{id}/events` 在主日历**新建定时日程事件**（标题 = 候选正文，不邀请他人，按候选 ID 审计幂等）；无开始时间或未注入创建器时条目留在审批页并记可见失败。「今日」简报行内编辑：**待办任务行「✎」** 改标题/截止（清空截止 = 移除），**会议行「✎」** 改标题/起止时间——均 `PATCH` 写回飞书本体后镜像当日渲染快照（任务连同其 AI 行动候选同步标题/截止；会议更新标题/展示时间与原始 ts），刷新即生效；会议快照附加演进 `event_id/start_ts/end_ts`（旧快照无键则不显示编辑钮），全量事件不开放编辑。日历写权限：`DEFAULT_SCOPES` 把 `calendar:calendar:readonly` 升级为 **`calendar:calendar`（读写）**，需在开放平台开通并**重新授权一次**后才能真机写回（`wb doctor --online` 可查授权状态）。同时修正一键完成的契约（真机报错驱动、多形态实测收敛）：Task v2 的 `PATCH update_fields` 白名单**不含** `completed`，第三方文档所述 `POST .../tasks/{guid}/complete` 在本租户返回 404；完成正解为 `PATCH completed_at`（毫秒字符串）并列入 `update_fields`（`update_task` 的 `summary/due` 不受影响）。质量门新增 17 项测试（日历创建/更新契约、`update_task` PATCH 契约、`feishu-meeting` actionable 与审批页起止字段往返、apply 经 `MeetingCreator` 建事件与幂等/失败隔离、快照镜像编辑、`/api/tasks/update`·`/api/meetings/update`·审批编辑端点），全套 **457 项全绿**；ruff + format + mypy strict + 前端 tsc 通过。
- **真机核实（ADR 0025，2026-09-03）**：日历/任务写回端点、`update_fields` 契约与日历读写权限经真实飞书数据验证——建日程事件、改会议标题与起止时间（回读一致）、改任务标题与截止（改回原文）、一键完成 `PATCH completed_at` 契约（带 assignee 任务：建 → 完成 → 出现在已完成列表 → 删除，闭环通过）；日历 scope 升级后需重新授权一次（旧 token 不带新权限）。

## [0.2.0] - 2026-09-03

发布版。核心问题不变（外置执行管理层 + 第二大脑），交付面收敛：**用户日常入口 = 原生 macOS 桌面 App 内的本地 Web 工作台**。在 v0.1.0（M0/M1/M2 + 韧性/正式使用前加固）之上完成 Web 工作台产品化、桌面 App 正式化与晨间简报 v2 呈现改版；vault 内简报 Markdown 版式不变（Obsidian 侧与 G1 回归的唯一真源）。质量门 433 项全绿。

### 新增

- **macOS 桌面 App（自包含正式版）**：`.app` 从「Swift 启动器 + 外部 Chrome 面板」演进为**自包含 bundle**——PyInstaller 打包 bundle server + 原生 Swift/AppKit 壳 + **受管 WKWebView 面板**（同源加载本地面板，生命周期受监督：服务就绪握手、面板自动恢复、退出即优雅停服）。构建/安装/自更新原子化（`scripts/build-macos-app.sh` + `install-macos-app.sh`，替换失败自动回滚），前端构建身份（frontend_build + server_instance）随版本握手校验，面板不匹配自动重启自带服务；`wb web` 独立直跑形态保留（读仓库 static，重建+重启即生效）。安装位 `/Applications/SummitWorkbench.app`（桌面副本弃用，详见 `docs/DESKTOP_APP.md` 与 ADR 生命周期方案）。
- **晨间简报 v2（ADR 0024 / PRD L49）**：Web 面板把简报从纯文本清单升级为**日程优先的组件化视图**——会议时间列（过去淡化）+ 待办任务按截止紧迫度排序（今天到期红 / 剩 1–2 天琥珀 / 一周内蓝 / 更远灰，语义色倒计时徽章）；AI 选中的任务行叠加「分类 · 排名」注解并与待办清单**合一**（精确关联 `task_id`↔`feishu-task:{guid}`，消除事实区/行动区重复展示）；清单之外的行动（git 未提交 / 项目下一步 / inbox 积压）单列「需要行动 · 任务清单之外」；AI 提议与最近完成默认折叠带计数。数据经**信号快照附加演进**（`as_snapshot()` 增 `meeting_list/task_list/proposal_list/completion_list/health_reasons` 等明细）由 `/api/state.brief` 下发；旧快照自动回退 Markdown 视图、存量零迁移。前端设计令牌全局换新（Linear 型 zinc + 靛紫主色，深浅双色精修，`web/src/style.css` CSS 变量集中）。`web/src/brief-card.ts` 纯字符串渲染模块 + 静态预览生成（`web/scripts/preview-brief.mjs` → `docs/design/brief-v2-preview.html`）。

- **首页卡片一键归档 + 内置「指南」页签**：首页每个项目推进卡右下角新增「归档」按钮（带确认，归档即离开首页、可在「项目」页恢复）；顶部新增第 5 个页签「指南」，把 `WEB_USAGE_GUIDE.md`（日常使用 + FAQ）在构建时同步内置进前端（`npm run sync-guide`），离线可看，FAQ 折叠为可展开条目——用户日常入口是 Web 面板，不必翻仓库文档。
- **项目推进精选（ADR 0023）**：首页「项目推进」不再平铺 `work_root` 全部文件夹，只显示已建档（`_vault/projects/*.md`）且 `status: active` 的项目；未建档的新文件夹在项目区顶部以邀请横幅出现（逐条「加入工作台 / 归档」）；新增第 4 页签「项目」= 全部项目视图（搜索 + 排序 + 行内加入/归档/恢复）。`/api/state` projects 增 `registered/status` 字段；新增 `POST /api/projects/activate`、`POST /api/projects/archive`（写 `_vault` 档案 status，幂等，校验必须是 work_root 直接子目录）。归档/恢复只动 frontmatter，文件夹与 git 历史零触碰。
- **Web 工作台（SPA）**：`wb web` 由服务端渲染面板升级为「今日工作台」单页应用（Vite + 原生 TypeScript，无组件库；FastAPI 新增 `/api/*` JSON 端点；构建产物存在时 `/` 服务 SPA，否则回退 SSR，旧路由与 CLI 语义完全保留）。
  - 「今日」页：顶部快速捕捉（回车记入全局 inbox）、待确认审批卡片（积压置顶 + 一键跳转）、会议逐字稿拖拽导入区、项目推进卡（未提交/落后/下一步/inbox 积压）、今日简报（未生成时给出空状态引导）、问第二大脑。
  - 「审批」页：即时批准/拒绝/改回 + 原地修改 + 预演/应用弹窗，不再整页刷新；状态 60s 自动刷新。
- **Web 端会议导入**：`POST /api/meetings/import` 拖拽上传 `.md/.txt` 逐字稿 → 复用 `wb meeting import` 链路全自动归档 + 结构化 + 生成审批候选，报告处理/跳过/失败/候选数与预估费用（软预算只提示不阻断，PRD 提醒线语义不变）。
- **快速捕捉智能分类**：新增 `capture` 模型能力位与 `prompts/capture-classifier.md`；`POST /api/capture` 先分类（承诺/想法 + 截止日期，单次调用、8s 超时）再入 inbox，分类以稳定标记写回（`wb-capture-kind/due/project`）；`#项目` 标签本地解析到已建项目，不经模型；模型不可用/超时/输出非法一律按「想法」兜底，录入永不丢数据。
- **通知闭环**：`wb status --notify` 评估出的预算/积压/定时任务告警真正发到 macOS 通知中心（此前只打印到 stdout，launchd 调用时不可见）；`wb web --open` 一条命令：服务未运行时后台拉起，再打开浏览器直达面板。
- **审批批量操作**：「审批」页每个会议分组新增「✓ 全批 / ✗ 全拒」按钮（只作用于该组待确认条目），工具栏新增「一键拒绝过期项」（截止早于今天的待确认条目批量置为拒绝）；待确认条目截止日期早于今天时在元信息里标注「已过期」。后端新增 `POST /api/review/batch`（`repositories.review_edit.set_decisions` 单次解析 + 单次原子重写，未知 ID 幂等跳过）。
- **`wb review sweep` 清理命令**：一键退役测试/旧会议——审批页候选批量拒绝、笔记 frontmatter 置 `ignored`（正文原文保留）、任务状态收口 `ignored`；支持 `--before YYYY-MM-DD` 只清理旧会议，默认 dry-run 零写入（与 `wb review apply` 同款安全姿态）。
- **会议提取门槛收紧**：`prompts/meeting-processor.md` v2→v3——`decisions` 只收已拍板结论，`action_items` 只收「谁、何时前、做什么」明确的承诺；拿不准的一律降级到 `facts` / `open_questions` / `ai_suggestions`，减少审批页噪音。

### 修复

- **入口页禁缓存（根治“点了没更新”）**：`/` 响应加 `Cache-Control: no-cache`——前端每次改版都换带哈希的资源名，若入口 index.html 被浏览器启发式缓存会一直指向旧资源，呈现旧界面/旧标签；现在刷新或重开 App 必取最新入口。
- **弹窗遮罩常驻屏幕（亮条 + 整页变灰 + 点击无效）**：`.modal-backdrop` 的 `display: grid` 覆盖了 `hidden` 属性（作者样式优先于 UA 的 `[hidden]{display:none}`），导致未打开的弹窗遮罩从一开始就铺满全屏——中间的空白弹窗呈「很亮的矩形条」，背后整页被 45% 黑色遮罩压灰，且遮罩拦截所有点击（`closeModal` 因样式覆盖而失效）。已在 `web/src/style.css` 加 `[hidden]{display:none!important}` 防御规则并重建前端产物。
- **程序坞图标无限弹跳 / 打开报「无响应」**：`.app` 主程序原本是 bash 脚本，常驻进程从不向系统报告「启动完成」——前台形态 Dock 图标无限弹跳，改 `LSUIElement` 后台形态后 macOS 又报「不能打开…没有响应」。根治方案：主程序换成**原生 Swift/AppKit 启动器**（`scripts/summit_launcher.swift`，构建时 `swiftc` 编译），注册正常的应用生命周期；`LSUIElement=true` 不占 Dock，打开/退出全部由原生进程管理（拉起 `wb web` 子进程 + 打开 Chrome 面板窗口，周期探测 `/api/state`，服务停止即自动退出）。退出面板用网页顶栏「退出」按钮 → `POST /api/shutdown`（带 `X-WB-Shutdown` 自定义头防任意网页误关，跨站预检被无 CORS 配置拦截）优雅停服并关窗。（该「启动器 + Chrome 面板」形态随后被**自包含原生 App（受管 WKWebView）**取代：删除 `scripts/summit_launcher.swift`，`.app` 直接烘焙 bundle server 与面板，见上方「macOS 桌面 App（自包含正式版）」条目。）

### 构建

- 前端源码在 `web/`（`npm install` + `npm run build`），产物打进 Python 包 `src/summit_workbench/webapp/static/`，`wb web` 开箱即用；开发模式 `npm run dev` 经 Vite 代理直连本机 `wb web`。

### 质量

- 项目精选（ADR 0023）补齐单测：建档状态读写与幂等、`ProjectState` 分类（新/归档）、`/api/state` 字段、activate/archive 端点（含非法名/越界/幂等），全套 **374 项全绿**；ruff + format + mypy strict 通过（新增 Web API / SPA 测试见 `tests/unit/test_webapi.py`、`test_project_registry.py`、`test_brief_repositories.py`）。
- 新增 14 项 Web API / SPA 测试（`tests/unit/test_webapi.py`）与 2 项 `/api/shutdown` 测试，全套 389 项全绿；ruff + format + mypy strict 通过。
- 批量裁决（`set_decisions`）、`/api/review/batch`、`wb review sweep` 补齐单测，全套 397 项全绿；ruff + format + mypy strict 通过。
- 晨间简报 v2（ADR 0024）补齐快照附加演进与 `/api/state.brief` 契约测试（`test_brief_domain.py` / `test_webapi.py`），全套 **433 项全绿**；ruff + format + mypy strict 通过；前端 strict TS（tsc --noEmit）+ Vite 构建通过，预览页 headless DOM 抽查确认。

## [0.1.0] - 2026-09-02

首个发布版。M0 / M1 / M2 全部完成并经真实数据/真机验证，质量门 360 项全绿。

### 新增
