# 变更记录

本文件记录 SummitWorkbench 的显著变更。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.1.0] - 2026-09-02

首个发布版。M0 / M1 / M2 全部完成并经真实数据/真机验证，质量门 360 项全绿。

### 新增

- **底座（M0）**：`wb version` / `wb diagnose`；分层配置与 macOS Keychain 凭据引用；`wb vault check` vault schema 校验；`wb sync` 以 git remote 为唯一真源、非破坏性批量同步工作项目与 vault。
- **飞书接入（M0-4 / M0-10）**：身份授权、最小权限与 refresh token 轮换；按会议号 → `note_id` → 逐字稿的纪要拉取（tenant token）；日历/任务只读冒烟。
- **云端模型（M0-6）**：供应商无关的 OpenAI 兼容适配、超时/429/5xx 退避重试、四类能力配置位与 `[models.shared]` 回退；月度用量与费用账本。
- **会议链路（M1）**：稳定 schema 与处理状态机、双文件归档（证据层逐字稿 + 结构化笔记）、模型调用前落盘证据、失败进错误队列零半成品；`wb meeting archive`/`archive-local`/`import`/`process`/`backfill`。
- **集中审批（M1-4）**：稳定候选、集中审批页、dry-run 默认、批准/拒绝/原地修改、审计归档、双层幂等；项目别名解析为规范 ID，未匹配项目零摩擦落入全局 inbox；`wb project new`/`list`。
- **状态与问答（M1-5 / M1-6）**：`wb status` 汇总进度/费用/软预算/积压；`wb ask` 本地召回 + 只引用进上下文来源、事实/建议分区。
- **晨间简报与周复盘（M2）**：`wb brief`（事实采集 → 模型排序/确定性回退 → 幂等写当日笔记）、`wb weekly` 跨项目复盘；launchd 定时任务模板与安装脚本。
- **本地 Web 面板**：`wb web` 服务端渲染的审批面板 + 看板 + 一键触发（可选 `web` extra，复用领域逻辑，无独立前端框架）。
- **macOS 启动器 App**：`scripts/build-macos-app.sh` 打包双击启动本地面板的 `.app`（雪山主题图标）。

### 加固

- 工作区级跨进程锁（ADR 0016）：序列化飞书 token 轮换与 git 写序列。
- JSONL 日志容错读（ADR 0017）：逐行兜底、半截/缺键行跳过并隔离，不再整本崩溃；配套写侧原子写归并（`_atomic.py`）。
- 飞书 HTTP 公共退避重试 + 尊重 `Retry-After`（ADR 0018）。
- 持久化状态 schema 版本号（ADR 0019）；运行心跳与定时任务健康度、连续失败去重告警（ADR 0020）；统一预检 `wb doctor`，默认离线无副作用（ADR 0021）；飞书 token 失效降级与可见性（ADR 0022）。
- GitHub Actions 质量门（macOS：ruff + format + mypy strict + pytest）与覆盖率体检。

### 依赖

- 运行时：`typer` / `pydantic` / `pydantic-settings` / `httpx` / `pyyaml`（均带大版本上界护栏，可复现由 `uv.lock` 保证）。
- 可选 `web` extra：`fastapi` / `uvicorn` / `python-multipart`。

[0.1.0]: https://github.com/yifeng93/SummitWorkbench/releases/tag/v0.1.0
