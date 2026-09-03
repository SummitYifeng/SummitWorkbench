## [0.2.0] - Unreleased

### 新增

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
- **程序坞图标无限弹跳 / 打开报「无响应」**：`.app` 主程序原本是 bash 脚本，常驻进程从不向系统报告「启动完成」——前台形态 Dock 图标无限弹跳，改 `LSUIElement` 后台形态后 macOS 又报「不能打开…没有响应」。根治方案：主程序换成**原生 Swift/AppKit 启动器**（`scripts/summit_launcher.swift`，构建时 `swiftc` 编译），注册正常的应用生命周期；`LSUIElement=true` 不占 Dock，打开/退出全部由原生进程管理（拉起 `wb web` 子进程 + 打开 Chrome 面板窗口，周期探测 `/api/state`，服务停止即自动退出）。退出面板用网页顶栏「退出」按钮 → `POST /api/shutdown`（带 `X-WB-Shutdown` 自定义头防任意网页误关，跨站预检被无 CORS 配置拦截）优雅停服并关窗。

### 构建

- 前端源码在 `web/`（`npm install` + `npm run build`），产物打进 Python 包 `src/summit_workbench/webapp/static/`，`wb web` 开箱即用；开发模式 `npm run dev` 经 Vite 代理直连本机 `wb web`。

### 质量

- 项目精选（ADR 0023）补齐单测：建档状态读写与幂等、`ProjectState` 分类（新/归档）、`/api/state` 字段、activate/archive 端点（含非法名/越界/幂等），全套 **374 项全绿**；ruff + format + mypy strict 通过（新增 Web API / SPA 测试见 `tests/unit/test_webapi.py`、`test_project_registry.py`、`test_brief_repositories.py`）。
- 新增 14 项 Web API / SPA 测试（`tests/unit/test_webapi.py`）与 2 项 `/api/shutdown` 测试，全套 389 项全绿；ruff + format + mypy strict 通过。
- 批量裁决（`set_decisions`）、`/api/review/batch`、`wb review sweep` 补齐单测，全套 397 项全绿；ruff + format + mypy strict 通过。

## [0.1.0] - 2026-09-02

首个发布版。M0 / M1 / M2 全部完成并经真实数据/真机验证，质量门 360 项全绿。

### 新增