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