# SummitWorkbench

SummitWorkbench 是一个运行在 Mac Studio 上的个人工作系统，定位为“外置执行管理层 + 第二大脑”。它将项目状态、会议转写、工作记录、飞书日历与任务汇集到 Obsidian 工作 vault，在保留证据和人工审批边界的前提下，持续回答三个问题：我做过什么、为什么这样决定、接下来最该做什么。

> 当前状态：**M1 进行中**。M0 地基、M1-1（schema/状态机）、M1-2（会议发现与原文归档）已完成；M1-3（云端结构化）代码与故障注入测试完成，支持完整原文优先单次处理、按 token 预算分段与层级合并、强制证据锚点、同模型最多 3 次重试、错误队列和零半成品。真实归档链路已真机跑通；M1-3 尚待真实会议云端处理验收。仓库不含凭据或真实会议内容。

## 产品解决的问题

用户同时负责多条产品线，工作信息散落在 Git 仓库、飞书会议、任务和临时记录里。真正的风险不是“少记了一条笔记”，而是项目静默停摆、会议结论没有进入执行系统、过去做过的工作无法被后续 AI 会话可靠复用。

SummitWorkbench 将这套工作方式收敛为两层能力：

- **外置执行管理层**：每天从可验证信号中挑出最多 5 个行动，提醒停滞、承诺和阻塞，但不把模型推断冒充事实。
- **第二大脑**：自动保存会议逐字稿与结构化笔记，积累项目状态、决策和工作记录，并通过带来源的 `wb ask` 回答工作问题。

## 预期的日常图景

Mac Studio 在后台定时拉取新会议纪要并写入 Obsidian。会议原文和结构化笔记自动归档，可能改变项目或任务状态的内容进入集中待确认页。用户只需勾选、忽略或原地修改候选项，再批量应用。

每天 08:00 前，Obsidian 当日笔记成为晨间指挥台：显示会议、最近完成、项目状态和最多 5 个建议行动。需要深入工作时，从指挥台带着项目档案、当前状态和近期会议上下文启动交互式工作会话；结束后，项目主笔记与工作记录自动收尾。每周一生成跨项目复盘，帮助重新分配注意力。

## 文档优先级

发生冲突时，按以下顺序判断：

1. [产品需求文档](docs/product/PRD.md)——唯一权威产品规格与验收标准。
2. [开发计划](docs/plans/DEVELOPMENT_PLAN.md)——实现顺序、模块边界和质量门禁。
3. [项目说明](PROJECTDESC.md)——面向开发者与 AI Agent 的稳定项目摘要。
4. [需求思考记录](docs/background/THINKING_DOC.md)——历史背景，不代表当前结论。
5. [旧架构示意图](docs/architecture/ARCHITECTURE.html)——v0.1 历史材料，部分结论已失效；必须按 PRD 更新后才能作为实现参考。

## 计划中的仓库结构

```text
SummitWorkbench/
├── README.md
├── PROJECTDESC.md
├── docs/
│   ├── product/          # 权威 PRD
│   ├── plans/            # 开发计划
│   ├── architecture/     # 架构资料；当前 HTML 为历史版本
│   ├── decisions/        # 后续架构决策记录（ADR）
│   └── background/       # 非权威需求背景
├── src/summit_workbench/
│   ├── cli/              # wb 命令入口
│   ├── config/           # 配置、路径与凭据引用
│   ├── domain/           # 领域模型与稳定 schema
│   ├── providers/        # 飞书与云端模型适配器
│   ├── repositories/     # vault、状态与用量账本读写
│   ├── workflows/        # 会议、审批、问答、简报、上下文、录入
│   ├── observability/    # 状态、错误、通知与费用可见性
│   └── scheduling/       # 定时任务编排
├── prompts/              # 版本化 prompt，禁止内联到业务实现
├── templates/vault/      # Obsidian 笔记模板
├── deploy/launchd/       # Mac Studio 定时任务定义
├── scripts/              # 安装、迁移和运维入口
└── tests/
    ├── unit/
    ├── integration/
    ├── contract/
    ├── acceptance/
    └── fixtures/
```

空目录使用 `.gitkeep` 保留；它们只表示未来模块边界，不代表已有实现。

## 实施顺序

项目采用严格串行里程碑：

1. **M0 地基**：工作目录与 vault、项目档案、飞书权限、同步与模型/API 冒烟测试。
2. **M1 会议进入第二大脑**：会议拉取、双文件归档、云端结构化、集中审批、状态与费用、`wb ask`。
3. **M2 晨间简报**：事实采集、行动排序、每日简报和每周复盘。
4. **M3 带上下文启动与收尾**：交互式工作会话的上下文拼接与自动写回。
5. **M4 分流录入**：`wb task`、`wb note` 与 inbox 路由。

M1 的真实会议、问答、审批、故障恢复、费用和积压测试全部通过之前，不开始 M2。

## 硬边界

- MVP 只在 Mac Studio 开发、部署和验收；Mac Air 不进入首版。
- 产品进程本地运行，但模型推理全部使用可配置的云端模型 API；不引入本地模型。
- 所有会议内容可进入已配置的云端模型；录像不下载、不发送。
- 未经用户确认的会议提取项不得写入项目状态或创建飞书任务。
- 不建独立 App、服务端、向量库、RAG 或常驻进程。
- 凭据只进入 macOS Keychain 或运行时环境，禁止进入 Git、vault、日志、fixture 和模型上下文。

## 安装与使用

项目用 [uv](https://docs.astral.sh/uv/) 管理 Python 3.12 环境与依赖：

```bash
uv sync --extra dev          # 安装运行时与开发依赖
uv run wb diagnose           # 环境体检（运行时 / 路径 / 系统工具）
uv run wb vault check        # 校验工作 vault 的 frontmatter 与固定区块
```

已实现的 `wb` 命令组：

- `wb diagnose`、`wb version`：环境诊断与版本。
- `wb vault check`：vault Markdown schema 校验。
- `wb feishu authorize-url | login | smoke | import-local`：飞书身份授权、鉴权冒烟与本地逐字稿兜底。
- `wb feishu meetings | note-transcript`：按会议号 + 时间范围列出会议及 `note_id`；按 `note_id` 拉取逐字稿。
- `wb meeting archive | archive-local`：会议发现 → 取回逐字稿 → **模型调用前**落盘证据层（`meetings/transcripts/`），幂等防重；本地兜底导入。
- `wb meeting process`：读取已归档原文，生成 `meetings/notes/` 结构化笔记并回链证据；失败进入 `_signals/model-errors/`，不保存半成品。
- `wb model smoke`：云端会议模型结构化冒烟，含 token 与费用记账。
- `wb sync`：以 git remote 为唯一真源，非破坏性批量同步 `~/Documents/Work/` 下各仓库与 vault。

本机配置放 `~/.config/summit_workbench/config.toml`（模板见 [config.example.toml](config.example.toml)）；所有凭据只进 macOS Keychain，不进仓库。质量门：`uv run ruff check . && uv run mypy && uv run pytest`。

## 下一步

**M1（会议进入第二大脑）进行中**：M1-1/M1-2 已完成并真机跑通；M1-3 实现与 152 项自动化测试已完成，下一步用真实会议验收结构化质量、token/费用与错误恢复，随后进入 M1-4 集中审批与写回。之后依次是 M1-5 状态与费用、M1-6 `wb ask`、M1-7 历史补导。各批次决策见 [docs/decisions/](docs/decisions/)。
