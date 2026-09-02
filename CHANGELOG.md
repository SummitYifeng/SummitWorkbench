## [0.2.0] - Unreleased

### 新增

- **Web 工作台（SPA）**：`wb web` 由服务端渲染面板升级为「今日工作台」单页应用（Vite + 原生 TypeScript，无组件库；FastAPI 新增 `/api/*` JSON 端点；构建产物存在时 `/` 服务 SPA，否则回退 SSR，旧路由与 CLI 语义完全保留）。
  - 「今日」页：顶部快速捕捉（回车记入全局 inbox）、待确认审批卡片（积压置顶 + 一键跳转）、会议逐字稿拖拽导入区、项目推进卡（未提交/落后/下一步/inbox 积压）、今日简报（未生成时给出空状态引导）、问第二大脑。
  - 「审批」页：即时批准/拒绝/改回 + 原地修改 + 预演/应用弹窗，不再整页刷新；状态 60s 自动刷新。
- **Web 端会议导入**：`POST /api/meetings/import` 拖拽上传 `.md/.txt` 逐字稿 → 复用 `wb meeting import` 链路全自动归档 + 结构化 + 生成审批候选，报告处理/跳过/失败/候选数与预估费用（软预算只提示不阻断，PRD 提醒线语义不变）。
- **快速捕捉智能分类**：新增 `capture` 模型能力位与 `prompts/capture-classifier.md`；`POST /api/capture` 先分类（承诺/想法 + 截止日期，单次调用、8s 超时）再入 inbox，分类以稳定标记写回（`wb-capture-kind/due/project`）；`#项目` 标签本地解析到已建项目，不经模型；模型不可用/超时/输出非法一律按「想法」兜底，录入永不丢数据。
- **通知闭环**：`wb status --notify` 评估出的预算/积压/定时任务告警真正发到 macOS 通知中心（此前只打印到 stdout，launchd 调用时不可见）；`wb web --open` 一条命令：服务未运行时后台拉起，再打开浏览器直达面板。

### 构建

- 前端源码在 `web/`（`npm install` + `npm run build`），产物打进 Python 包 `src/summit_workbench/webapp/static/`，`wb web` 开箱即用；开发模式 `npm run dev` 经 Vite 代理直连本机 `wb web`。

### 质量

- 新增 14 项 Web API / SPA 测试（`tests/unit/test_webapi.py`），全套 374 项全绿；ruff + format + mypy strict 通过。

## [0.1.0] - 2026-09-02

首个发布版。M0 / M1 / M2 全部完成并经真实数据/真机验证，质量门 360 项全绿。

### 新增