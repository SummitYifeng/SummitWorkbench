# Web 工作台（wb web）设计说明

> 状态：v0.4.7 已交付（分发版：构建时内置飞书默认凭据，同事零预置即可「点一下授权」；前置为 v0.4.6 指南版本标记抗漂移、v0.4.4 的 UI/UX 优化、workspace-scoped 连接状态、原生生命周期与网页简报提交闭环，ADR 0024/0027/0045）· 配套 PRD L45–L52 与 3.2.7 节 · 操作指南见 [WEB_USAGE_GUIDE.md](WEB_USAGE_GUIDE.md)
>
> 本文回答「为什么这样设计」：形态、信息架构、边界与技术取舍。

## 1. 背景与目标

v0.1 的 `wb web` 是服务端渲染的审批面板：状态数字 + 表单 + 按钮。真实使用反馈是「死板、打开不知道要干什么、不知道该喂什么数据」。本次改版目标：

1. **打开第一眼就知道今天要干什么**——首屏是行动中心（捕捉/待确认/导入/项目），不是系统健康数字；
2. **知道该输入什么才有产出**——拖拽导入会议纪要成为首页常驻动作，「喂数据」是可见、有反馈的日常动作；
3. **体感像产品**——即时反馈（无整页刷新）、空状态引导、状态自动刷新。

## 2. 用户场景（三轮需求互动的结论）

| 场景 | 结论 |
|---|---|
| 第一场景 | 晨间指挥台 + 批量审批 + 随手记录（三选） |
| 最大痛点 | 首页没有「今天要做的事」、没有会议纪要导入入口、视觉工具化 |
| 第一优先 | 会议纪要上传/导入入口（全自动链路） |
| 形态偏好 | SPA（Vite + 原生 TS，无组件库） |
| 使用频率 | 每天多次，当工作台用 → 秒开、可见页 60s 自动刷新（页面隐藏时暂停读取，回到前台立即补一次）、常驻导航 |

## 3. 信息架构

```
顶栏    品牌 + 日期 + 健康点 + 手动刷新
页签    今日（默认） | 审批（带待确认角标） | 项目 | 设置
        （2026-09-16 下线「第二大脑」「指南」两个页签）

今日页  ① 快速捕捉输入框（回车入 inbox，AI 分类）
        ② 待确认审批卡片（有积压置顶 + 去处理→；无则绿色清空态）
        ③ 会议逐字稿拖拽导入抽屉（全自动归档+结构化+生成候选）
        ④ 项目推进卡（ADR 0023：只显示已建档 active 项目；卡片右下角「归档」按钮；
           未建档文件夹以邀请横幅出现）
        ⑤ 今日简报（L49：日程优先的组件化视图——会议时间列 + 待办任务截止语义色/
           倒计时 + AI 选中任务行「分类 · 排名」注解；未生成 → 空状态引导「现在生成」）

审批页  工具栏（待确认数 + 检查并写回；先预演再确认）
        按会议分组的候选卡片：即时批准/拒绝/改回/修改
        预演/应用结果以弹窗呈现，应用前可确认

项目页  全部项目（含归档）搜索 + 状态徽标 + 行内加入/归档/恢复（ADR 0023）
```

## 4. 各模块规格

### 4.1 快速捕捉（L47）

- 输入一行 → 模型分类（承诺/想法 + 截止日期，单次调用、8s 超时上限）→ 记入全局 inbox。
- `#项目` 标签**本地**解析到已建项目（project_registry），不经模型，避免臆造项目名。
- 分类以稳定标记写回 inbox（`<!-- wb-capture-kind: task -->`、`wb-capture-due`、`wb-capture-project`），供 M4 `wb task` 承接路由。
- **兜底**：模型不可用/超时/输出非法 → 一律按「想法」归档，录入永不失败、永不丢数据。
- 配置位：`[models.capture]`（可指更便宜模型，缺省回退 `[models.shared]`）。

### 4.2 待确认审批卡片

- 数据来自 `/api/state` 的 `status.backlog`（与 `wb status` 同一账本）。
- 积压 > 0：警告色卡片，显示条数与最老等待天数，一键切到审批页；= 0：绿色清空态。

### 4.3 会议逐字稿导入（L46）

- 拖拽或点选 `.md/.txt` → 复用 `wb meeting import` 链路（scan → 预估 → archive + process → 生成候选，幂等不变）全自动执行。
- 响应回显：处理/跳过/失败/候选数 + 预估费用；软预算只提示不阻断（PRD L42 提醒线语义）。
- 写回边界不变：全自动只到「生成候选进审批页」，批准只做决定标记；检查并确认「应用（写回）」后才写回（L13）。
- 分组批量批准只纳入具备依据与落点的待确认候选，并在按钮上显示实际范围；批量拒绝显示全部待确认范围。前端单批上限为 100 条，超过时不发送请求。
- 审批卡片的会议笔记与逐字稿来源通过 `/api/sources/read` 只读打开（历史兼容入口 `/api/review/source` 仍在路由契约内，使用同一份知识目录白名单），并校验路径必须位于当前 vault 内、且属于允许的知识目录（`projects/`、`meetings/`、`logs/`、`artifacts/`、`inboxes/`、`daily/`、`reviews/`、`insights/` 或 `inbox.md`）；来源缺失、越界、非知识文件、非 Markdown、过大时返回可解释错误。正文超过 100,000 字符时只返回前 100,000 字符并带 `truncated: true`，面板显示「正文已截断」；文件本身超过 256 KiB 时仍然直接拒绝（413），不会整篇返回。
- 文件名建议 `YYYY-MM-DD-会议标题.txt`（日期与标题的稳定来源）。

### 4.4 项目推进卡

- 数据来自 `scan_projects`（离线 git 状态 + 项目 inbox 计数 + 主笔记「下一步」，与简报事实区同一来源）。
- 有动静的项目高亮（未提交/落后/积压），下一步文本直接取自主笔记，不经过模型。
- **显示集合是「工作台精选」而非全量文件夹（ADR 0023），且项目全集含知识线程（ADR 0026）**：
  `work_root` 下已建档（`_vault/projects/<name>.md` 存在、`type: project-main`）且
  `status: active` 的**文件夹项目**与**无文件夹的知识线程档案**（`scan_all_projects` =
  文件夹项目 + 线程合并；线程卡显示「知识线程」徽标 + 「最近活跃」（档案 `activity_at`，日志/产物等  机器活动刷新）+ >14 天无**实质更新**提示（档案 `updated`，只由建档/激活/归档/改名/状态确认刷新））
  一起渲染推进卡；**未建档的新文件夹**在项目区顶部以一条邀请横幅出现（逐条
  「加入工作台 / 归档」，不占卡片位），处理完即消失；归档项目（`status: archived`）不上
  首页但可在「项目」页一键恢复。每张首页卡片右下角有「归档」按钮（带确认），可直接把
  该项目移出首页。目标：本地文件夹到几十上百个量级时首页仍是清爽的推进视图。
- **线视图（ADR 0026）**：点项目/线程名打开 = 档案区块（当前状态 / 下一步 / 阻塞 /
  跟进事项 / 决策记录，跟进带「N 条待闭环」徽标）+ 时间线聚合（logs/artifacts/meetings
  按日期倒序）；视图内可直接「✎ 日志 / 存产物 / 刷新」与「✎ 显示名」。
- 第 4 个页签「项目」= 全部项目视图：列出 `work_root` 全量文件夹（含归档），支持按名搜索，
  排序为 在工作台 → 新 → 已归档；行内「加入工作台 / 归档」即改 `_vault` 档案状态，与
  `#项目` 标签解析、审批路由共用同一份项目账本。

### 4.5 今日简报（v2）/ 问答

- **数据通路（ADR 0024）**：`/api/state.brief` 是结构化载荷（来自当日信号快照 `_signals/YYYY-MM-DD.json` 的 `*_list` 明细），前端 `web/src/brief-card.ts` 组件化渲染；读取 `/api/state` 只读取当前本地快照和实时状态，不会自动生成简报或写入飞书。快照是**附加演进**（计数键保留），旧快照缺明细时 `brief=null`，前端自动回退 Markdown 视图；只有明确点击「重新生成」才运行 `wb brief` 并写入新快照。vault 当日笔记的简报 Markdown 版式不变——Obsidian 侧与 G1 回归的唯一真源。
- **呈现语义（L49）**：日程优先——会议（时间列，过去淡化）与待办任务（截止紧迫度排序 + 语义色倒计时徽章）是主区；AI 选中的任务按 `task_id`↔`feishu-task:{guid}` 精确合并到对应行上叠加「分类 · 排名」注解（消除事实区/行动区重复）；清单之外的行动单列「需要行动 · 任务清单之外」；AI 提议与最近完成默认折叠带计数。
- 未生成给空状态引导，可一键触发 `wb brief`。
- 网页端触发简报后，`/api/run/brief` 使用 workflow 返回的显式持久化路径完成提交/推送；
  自动化 worker 还会把运行心跳作为显式路径加入同一提交，只包含当次简报、快照、用量、授权状态和
  心跳文件，不会把其他未提交文件带入提交。设置页「立即运行」使用 `force` 语义，避免被当天的
  `last_run_at` 误判为未到执行时间；定时调度仍保留原有 due 门控。
- **问答与指南两个页签已于 2026-09-16 下线**：语义问答统一归 SummitKnowledge（有向量检索与云端精排）；SWB 不再提供 `wb ask`/`wb kb` 或本地检索索引。`/api/sources/read` 与只读来源面板**保留**——审批页的证据核查仍在用。
- 产物入库与主档案状态同步分成两步：产物先保存；若用户选择同步当前状态，面板先展示最终摘要预览，
  只有确认后才覆盖主档案，取消只保留产物。
- 使用指南不再随包内置，只作为仓库文档维护（`WEB_USAGE_GUIDE.md`）；App 内不再有指南页签，减少离线资源的维护面。
- 设置页按连接的真实状态显示「未配置/未连接」「✓ 已配置/已授权」「验证失败」或「需重新授权」；失败状态不伪装成已配置，飞书授权失效时优先提示重新授权。

## 5. JSON API（FastAPI，复用既有领域逻辑）

| 端点 | 用途 |
|---|---|
| `GET /api/state` | 日期、状态速览（StatusReport.as_dict）、今日简报（`brief_md` + 结构化 `brief`，ADR 0024）、inbox 积压、项目推进 |
| `GET /api/review` | 审批页分组 JSON（meetings.md 事实源） |
| `GET /api/sources/read` | 只读读取允许的知识 Markdown（返回来源 ID、标题、日期、正文与截断标记；正文超过 100,000 字符时截断并置 `truncated: true`，文件超过 256 KiB 直接 413） |
| `GET /api/review/source` | 历史兼容的纯文本来源只读入口；与 `/api/sources/read` 使用同一份知识目录白名单 |
| `POST /api/review/decide` / `POST /api/review/edit` | 即时批准/拒绝/修改（review_edit）；批准要求候选具备依据与落点 |
| `POST /api/review/plan` / `POST /api/review/apply` | 预演 / 显式应用（apply_meeting_review） |
| `POST /api/capture` | 快速捕捉 + AI 分类 + 标记写回 |
| `POST /api/projects/activate` / `POST /api/projects/archive` | 加入/恢复工作台 / 归档（ADR 0023：写 `_vault` 档案 status，幂等） |
| `POST /api/projects/create` / `POST /api/projects/rename` | 知识线程建档（v0.4，无文件夹）/ 项目显示名（frontmatter `title`）|
| `GET /api/projects/view` | 线视图：档案区块 + 时间线聚合（ADR 0026）|
| `POST /api/threads/logs` / `POST /api/threads/artifacts` / `POST /api/threads/state` | ✎ 推进日志 / 存产物（含本地文件导入）/ 产物摘要 → 当前状态草案（v0.4）|
| `POST /api/meetings/import` | 拖拽上传逐字稿全自动导入（multipart） |
| `GET /api/undo/history` / `GET /api/undo/diff` / `POST /api/undo/revert` | 系统自动写回留痕的撤销（v0.4.1：最近 `wb:` 提交 / 差异 / git revert 一键还原；只作用于 vault 文件） |
| `POST /api/run/brief` / `POST /api/run/weekly` / `POST /api/ask` | 一键触发简报/周复盘/问答 |

所有端点与 CLI 共用 repositories/workflows，**meetings.md 永远是唯一事实源**。

> v0.4.1 起，面板写路径全部经过工作区锁（repository 级 RMW 原子化）并在成功后自动 git 留痕（显式路径、消息 `wb:` 前缀，非 git 仓库优雅降级）；「↩ 撤销」读取这些自动提交并提供差异与一键还原。

## 6. 技术实现

- 前端：Vite + 原生 TypeScript（无组件库）；`web/` 目录，`npm run build`（tsc --noEmit + vite）输出到 `src/summit_workbench/webapp/static/`（随 Python 包分发，`wb web` 开箱即用）。
- 简报 v2 渲染为纯字符串模块 `web/src/brief-card.ts`（无 DOM 依赖，可独立生成历史静态预览：`node web/scripts/preview-brief.mjs` → `docs/archive/design/brief-v2-preview.html`）；全局设计令牌（zinc + indigo、深浅双色）集中在 `web/src/style.css` 的 CSS 变量。
- 开发：`npm run dev` 经 Vite 代理直连本机 `wb web`（8787），热更新。
- 后端：FastAPI 新增 `/api/*`；`/` 在 static/index.html 存在时服务 SPA，否则回退 SSR（views.py 保留，旧路由 `/review`、`/run/*`、`/ask` 全部可用）。
- 通知闭环（L48）：`wb status --notify` 真正投递 macOS 通知中心（osascript）；`wb web --open` 服务未运行时后台拉起 + 打开浏览器。
- 同步横幅：页面启动和 60 秒轮询读取 `/api/sync/status`；顶栏手动刷新也会立即刷新该状态，避免已恢复的工作树继续显示旧的 `dirty-protected`。

## 7. 用户入口与交付注意（开发必读）

- **用户的日常入口是 Web 面板，不是 CLI。** 真人用户只打开 `/Applications` 里的桌面 App
  （自包含 bundle：PyInstaller server + 原生 Swift/AppKit + 受管 WKWebView，加载同一套面板）
  或在直接运行 `wb web` 时访问默认的 `http://127.0.0.1:8787` 完成全部日常工作；桌面 App
  使用动态 loopback 端口，CLI 只用于自动化（launchd/脚本）
  与深度操作。因此**任何「用户可见」的功能改动，默认交付到 Web 面板**，并同时保证 CLI
  语义不倒退（两者共用 repositories/workflows）。
- **两种运行形态，更新路径不同**：
  - 从仓库直跑 `wb web`：读仓库 `src/summit_workbench/webapp/static/`——`cd web && npm run build`
    后重启服务即生效；
  - 桌面 App（`/Applications/SummitWorkbench.app`）：**自包含且版本锁定**（bundle 内烘焙 server +
    static + 前端构建身份），更新需重跑 `scripts/build-macos-app.sh` 并
    `scripts/install-macos-app.sh <dist>.app --replace-running`（详见 `docs/DESKTOP_APP.md`）；
    App 启动时校验 frontend_build 与自身 manifest 一致，不一致会重启自带服务。
- **「改了版本但点开没更新」的排查顺序**：
  1. 面板服务是不是在本次构建**之后**重启的？（服务读的是磁盘上的 static，重启即新版本）
  2. 浏览器是否缓存了旧 `index.html`——它引用的旧哈希资源已从磁盘删除，会呈现旧界面或
     白屏；**⌘⇧R 强刷**一次。
  3. 打开的是不是当前构建的 App？`/Applications` 里的 `SummitKnowledge.app`、
     `SummitServerAI.app` 是历史遗留的旧名/旧前端产品（内嵌冻结运行时），**不是本仓库的
     产物**；请打开 `/Applications/SummitWorkbench.app`（唯一正式安装位，桌面副本已弃用）。

## 8. 边界与约束（与 PRD 一致）

- 纯本地 `127.0.0.1`、按需启动；不引入服务端、常驻守护进程、向量库或 RAG。
- 会议内容上云边界（L33）、写回需确认（L13）、软预算提醒线（L42）全部不变。
- 质量门：ruff + format + mypy strict + `pytest tests/unit`、route contract、前端契约测试和生产构建。
  v0.4.7 本地验证为 **925 passed / 1 skipped、覆盖率 82.77%**，ruff、ruff format、mypy strict、
  route contract、frontend test 与生产构建全部通过；远端 GitHub Actions 质量门在
  `SummitYifeng/SummitWorkbench` 上全绿（含 macOS arm64 构建矩阵与 packaged App smoke）。
