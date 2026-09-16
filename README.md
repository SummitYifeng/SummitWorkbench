# SummitWorkbench

SummitWorkbench 是一个运行在 Mac Studio 上的个人工作系统，定位为“外置执行管理层 + 第二大脑”。它将项目状态、会议转写、工作记录、飞书日历与任务汇集到 Obsidian 工作 vault，在保留证据和人工审批边界的前提下，持续回答三个问题：我做过什么、为什么这样决定、接下来最该做什么。

> **当前状态：`v0.4.7` 内部使用版（分发给同事的版本；build 由 CI `run_number` 决定）。** 分发版：把飞书 app_id / app_secret 作为**默认值**在构建时内置进安装包，同事装完只需「粘贴 DeepSeek API Key → 点一下『授权飞书』」，无需任何本机预置（不再需要编辑 `config.toml` 或用命令行写 Keychain）。产品行为与数据格式未改动。此前 `v0.4.6`（指南版本标记抗漂移）、`v0.4.5`（交付前清理 + 指南重写）、`v0.4.4`（UI/UX 与交付稳定性）的成果全部保留。**仓库不含凭据**：内置凭据文件只在构建期由环境变量生成，且 `build/`、`dist/` 均被 git 忽略；仓库也不含真实会议内容。发布流程与安全取舍见 [docs/RELEASING.md](docs/RELEASING.md)；远端 CI 质量门全绿。

## 产品解决的问题

用户同时负责多条产品线，工作信息散落在 Git 仓库、飞书会议、任务和临时记录里。真正的风险不是“少记了一条笔记”，而是项目静默停摆、会议结论没有进入执行系统、过去做过的工作无法被后续 AI 会话可靠复用。

SummitWorkbench 将这套工作方式收敛为两层能力：

- **外置执行管理层**：每天从可验证信号中挑出最多 5 个行动，提醒停滞、承诺和阻塞，但不把模型推断冒充事实。
- **第二大脑**：自动保存会议逐字稿与结构化笔记，积累项目状态、决策和工作记录，并通过带 `路径#区块` 来源的轻量 `wb ask` 回答工作问题。

> **与 SummitKnowledge 的边界**：SWB 是工作库的**唯一写入方**（看板、采集、审批、源数据处理），
> 保证自动沉淀的 Markdown 可被稳定索引、引用与判权威；**高级语义检索（向量召回、云端精排、
> 多步生成问答）唯一归属 [SummitKnowledge]**，工作库对 SK 只读。共享契约见
> [`docs/contracts/WORK-KB-RETRIEVAL-CONTRACT.md`](docs/contracts/WORK-KB-RETRIEVAL-CONTRACT.md)。

## 预期的日常图景

Mac Studio 在后台定时拉取新会议纪要并写入 Obsidian。会议原文和结构化笔记自动归档，可能改变项目或任务状态的内容进入集中待确认页。用户只需勾选、忽略或原地修改候选项，再批量应用。

> **用户日常入口 = 桌面 App 内的 Web 面板，不用 CLI。** 真人用户只打开桌面 App 完成全部日常工作；
> 直接运行 `wb web` 时才使用默认的 `http://127.0.0.1:8787`（捕捉/审批/导入/项目/问答，见
> [WEB_USAGE_GUIDE](docs/product/WEB_USAGE_GUIDE.md)）；CLI 保留给自动化（launchd、脚本、
> `wb review sweep` 等）与深度操作。因此**开发任何用户可见功能都以 Web 面板为默认交付面**，
> 改动后必须重建前端产物并重启面板服务才生效（见
> [WEB_WORKBENCH §8](docs/product/WEB_WORKBENCH.md) 与 [DESKTOP_APP](docs/DESKTOP_APP.md)）。

每天 08:00 前，`wb brief`（由 launchd 定时触发）把 Obsidian 当日笔记写成晨间指挥台：显示会议、最近完成、项目状态和最多 5 个建议行动。每周一 `wb weekly` 生成跨项目复盘，帮助重新分配注意力。

## 文档优先级

发生冲突时，按以下顺序判断：

1. [产品需求文档](docs/product/PRD.md)——唯一权威产品规格与验收标准。
2. [历史开发计划](docs/archive/plans/DEVELOPMENT_PLAN.md)——已完成阶段的实现顺序、模块边界和质量门禁。
3. [项目说明](PROJECTDESC.md)——面向开发者与 AI Agent 的稳定项目摘要。
4. [架构决策记录](docs/decisions/README.md)——各工作包的落地决策与真机验证结论（ADR 索引）。
5. [需求思考记录（归档）](docs/archive/background/THINKING_DOC.md)——历史背景，不代表当前结论。
6. [旧架构示意图（归档）](docs/archive/architecture/ARCHITECTURE.html)——v0.1 历史材料，部分结论已失效；必须按 PRD 更新后才能作为实现参考。

## 仓库结构

```text
SummitWorkbench/
├── README.md / PROJECTDESC.md / config.example.toml
├── docs/
│   ├── product/          # 权威 PRD
│   ├── archive/          # 已完成阶段的背景、计划、旧验收和设计预览
│   ├── decisions/        # 当前架构决策记录（ADR 0043–0045；历史 ADR 见 archive/decisions/）
│   ├── acceptance/       # 当前版本本地发布验收
│   ├── implementation/   # 当前增量实施与交接记录
│   ├── contracts/        # API/路由契约
│   └── DESKTOP_APP.md    # macOS .app 打包说明
├── src/summit_workbench/
│   ├── cli/              # wb 命令入口
│   ├── config/           # 分层配置、路径、Keychain 引用、工作区跨进程锁
│   ├── domain/           # 领域模型、稳定 schema、状态机、纯规则
│   ├── providers/        # 飞书与云端模型适配（含公共退避重试）
│   ├── repositories/     # vault / 状态账本 / 用量账本 / 原子写 / JSONL 容错读
│   ├── workflows/        # meetings·review·ask·brief·weekly·sync 编排
│   ├── observability/    # status·运行心跳健康度·通知·预算/积压告警
│   └── webapp/           # 本地 Web 工作台（FastAPI：/api/* JSON + 静态托管 + SSR 回退）
├── prompts/              # 版本化 prompt，禁止内联到业务实现
├── templates/vault/      # Obsidian 笔记模板
├── deploy/launchd/       # Mac Studio 定时任务 plist 模板
├── scripts/              # 安装、打包与图标脚本
├── assets/               # 应用图标源
└── tests/                # unit / integration / contract
```

## 实施进度

项目采用严格串行里程碑：

1. **M0 地基** ✅：工作目录与 vault、项目档案、飞书权限、同步与模型/API 冒烟。
2. **M1 会议进入第二大脑** ✅：会议拉取、双文件归档、云端结构化、集中审批、状态与费用、`wb ask`。
3. **M2 晨间简报** ✅：事实采集、行动排序、每日简报（`wb brief`）与每周复盘（`wb weekly`）。
4. **M3 带上下文启动与收尾**（本期不实施）：不新增交互式工作会话编排。
5. **M4 分流录入**（规划中）：`wb task`、`wb note` 与 inbox 路由。

M1 的真实会议、问答、审批、故障恢复、费用和积压测试（PRD L44 严格验收 6/6）在进入 M2 前全部真机通过（验收记录已并入 `docs/decisions/` 的 M1 ADR 索引）。

## 硬边界

- MVP 只在 Mac Studio 开发、部署和验收；Mac Air 不进入首版。
- 产品进程本地运行，模型推理全部使用可配置的云端模型 API；不引入本地模型。
- 所有会议内容可进入已配置的云端模型；录像不下载、不发送。
- 未经用户确认的会议提取项不得写入项目状态或创建飞书任务。
- **不建云端服务端、常驻守护进程、向量库或语义 RAG。** 后加入的本地 Web 面板（`wb web`）与原生 macOS 桌面 App 均为**纯本地、按需启动**的可选便利层：它们只复用既有领域逻辑、不引入服务端、不改变数据边界（`.app` 双击启动 bundle 内 server + WKWebView 面板，服务仍是 `127.0.0.1` 上的同一套本地面板）。高级语义检索（embedding / 向量库 / 精排）归 SummitKnowledge，SWB 只做块级本地检索与强制引用。
- 凭据只进入 macOS Keychain 或运行时环境，禁止进入 Git、vault、日志、fixture 和模型上下文。
- **本机机器日志与工作台内容分开**：同步/推送失败只写稳定原因码、计数与异常类名到
  `~/Library/Logs/summitworkbench-server.log`（JSONL、0600、5 MiB 轮转，见
  `observability/server_log.py`）；机器日志**绝不写进 vault**——vault 里的 `logs/` 是被同步、
  会被提交的**工作台内容**。

## 安装与使用

项目用 [uv](https://docs.astral.sh/uv/) 管理 Python 3.12 环境与依赖：

```bash
uv sync --extra dev          # 安装运行时与开发依赖（含可选 web 面板依赖）
uv run wb doctor             # 端到端就绪预检（底座 / 配置 / vault / 凭据 / launchd，默认离线无副作用）
uv run wb vault check        # 校验工作 vault 的 frontmatter、固定区块与检索就绪契约
```

本地 Web 面板依赖是可选 extra：仅装运行时用 `uv sync`，需要 `wb web` 再加 `--extra web`（`--extra dev` 已包含）。

Web 工作台前端（`web/`）的构建产物已随包分发，`wb web` 开箱即用；改动前端后需重新构建：`cd web && npm install && npm run build`（产物写入 `src/summit_workbench/webapp/static/`）。开发时可用 `npm run dev` 经 Vite 代理直连本机 `wb web`（端口 8787）。

`wb` 命令组：

- `wb version` / `wb diagnose`：版本号与底座环境诊断。
- `wb doctor [--online]`：一条命令端到端就绪表（底座 / vault schema / 飞书配置+凭据可解析 / 模型配置+API key / launchd）。默认完全离线、无副作用、不打印任何秘密值；`--online` 才做真实飞书 token 刷新。
- `wb vault check`：vault Markdown schema 校验。
- `wb feishu authorize-url | login | smoke | import-local | meetings | note-transcript | calendar | tasks`：飞书身份授权、鉴权冒烟、按会议号取 `note_id` 与逐字稿、日历/任务只读冒烟、本地逐字稿兜底。
- `wb meeting archive | archive-local`：会议发现 → 取回逐字稿 → **模型调用前**落盘证据层（`meetings/transcripts/`），幂等防重；本地兜底导入。
- `wb meeting process`：读取已归档原文，生成 `meetings/notes/` 结构化笔记并回链证据；失败进入 `_signals/model-errors/`，不保存半成品。
- `wb meeting import <目录|文件>`：混合取稿策略的手动入口——把手动下载的逐字稿（`.md`/`.txt`，带讲话人+时间戳）一条命令归档+结构化，无需日期区间、幂等可续跑。
- `wb meeting backfill <目录|文件> --since --until [--include-actions] [--yes]`：按显式日期范围补导本地逐字稿，开始前预估会议数/token/费用、预计跨软预算再确认，逐场幂等续跑；默认只沉淀知识，`--include-actions` 才生成带 historical 标记的候选。
- `wb project new | list`：在第二大脑侧为新项目建档（不碰 GitHub 仓库）并查看已建项目及别名。
- `wb review refresh | apply`：幂等刷新集中审批页；`apply` 默认零写入预演，只有显式 `--apply` 才执行本地/飞书写回并归档审计；写回前把项目别名解析为规范 ID，未匹配项目的候选零摩擦落入全局 inbox。
- `wb web [--host --port] [--open]`：启动本地 **Web 工作台**（SPA，Vite + 原生 TS 构建，产物随包分发）。CLI 默认使用 `127.0.0.1:8787`；桌面 App 使用自包含 bundle 管理动态 loopback 端口。工作台包含 **今日**、**审批**、**项目**、**设置** 四个页签；交互走 `/api/*` JSON 端点。（2026-09-16 起下线「第二大脑」与「指南」两个页签：语义问答归 SummitKnowledge，使用说明在 `docs/` 里——App 只留看板与源数据处理，越简洁用得越勤。）
- `wb brief [--date --dry-run --commit --push --json]`：生成今日晨间简报，幂等写入 `_vault/daily/YYYY-MM-DD.md`（锚点区块只替换不重复）；排序失败走确定性回退并在首行标注降级。网页端一键生成会显式提交本次生成的简报、快照、用量和授权状态文件，不会使用 `add -A` 带入用户其他改动。
- `wb weekly [--date --dry-run --commit --push --json]`：从 git 提交 + 会议决策 + inbox + 停滞项目重新汇总上周复盘，幂等写入 `reviews/weekly/YYYY-Www.md`。
- `wb status [--json --notify]`：汇总会议处理进度、当月 token 与估算费用、软预算、待确认积压、定时任务健康度与飞书授权健康度；`--notify` 按去重规则把新通知真正发到 macOS 通知中心（供 launchd 定时调用，积压/费用/任务失败会主动提醒你）。
- `wb ask "问题" [--save --project P --limit N]`：本地**块级**检索（SQLite FTS5/trigram + Python BM25 降级 + 多信号融合 + 双链扩展）召回相关区块，云端模型只引用进入上下文的来源作答（事实/建议分区、证据冲突并列）；默认不保存，`--save` 才落 qa-insight。候选条数默认由**路由计划**决定（`--limit` 可显式覆盖），CLI 与验收脚本同口径。工作台面板不再内置问答入口（见上）。`wb ask` 是轻量兜底，不是语义 RAG——语义检索请用 SummitKnowledge。
- `wb model smoke`：云端会议模型结构化冒烟，含 token 与费用记账。
- `wb sync`：以 git remote 为唯一真源，非破坏性批量同步 `~/Documents/Work/` 下各仓库与 vault。

本机配置放 `~/.config/summit_workbench/config.toml`（模板见 [config.example.toml](config.example.toml)）；所有凭据只进 macOS Keychain，不进仓库。定时任务安装见 [deploy/launchd/README.md](deploy/launchd/README.md)，桌面 App 打包见 [docs/DESKTOP_APP.md](docs/DESKTOP_APP.md)。

质量门：`uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`；前端还需通过 route contract、`npm run test:frontend` 和生产构建。`v0.4.7` 的本地门禁已通过：**971 passed / 1 skipped、覆盖率 83.54%**，ruff、ruff format、mypy strict、`npm run build`（含 `verify-build.mjs` 与前端契约测试）、打包冒烟（`WB_PACKAGED_APP=…/SummitWorkbench.app`）全部通过，`scripts/release-macos.sh` 完整跑通并产出 build 34 DMG（内置飞书凭据）。远端 GitHub Actions 质量门（[`.github/workflows/ci.yml`](.github/workflows/ci.yml)，含 macOS arm64 构建矩阵与 packaged App smoke）在 `SummitYifeng/SummitWorkbench` 上全绿。

建议运行 `scripts/install-git-hooks.sh` 安装 pre-push hook：`scripts/pre-push-gate.sh` 会执行与 CI 相同的检查，并在 push 前校验每个 `uses:` 的 action ref 是否真实存在（防止引用不存在的 tag 直到 CI 才暴露）。

尚未取得验证证据的项集中在 [`docs/acceptance/OPEN-VERIFICATION-ITEMS.md`](docs/acceptance/OPEN-VERIFICATION-ITEMS.md)——那是该清单的单一真源，其他文档只链接过去。

## 版本

`v0.1.0`（首个发布版）→ `v0.2.0`（Web 工作台产品化 + macOS 桌面 App 正式化 + 晨间简报 v2）→ `v0.3.0`（工作台 → 飞书双向写回，真机核实）→ `v0.4.0`（知识线程项目）→ `v0.4.1`（维护加固）→ `v0.4.2`（打包修复）→ `v0.4.3`（P1-07D/P2-01B/P2-02 产品化基线）→ `v0.4.4`（UI/UX 与交付稳定性维护版）→ `v0.4.5`（交付前清理 + 指南重写）→ `v0.4.6`（指南版本标记改为抗漂移，build 20）→ `v0.4.7`（分发版：内置飞书默认凭据，同事点一下即可完成授权；build 34 收口 D9/D10 并新增主设备接管、首次发布到远端与本机服务日志）。当前仅保留 `main` 主线；变更记录见 [CHANGELOG.md](CHANGELOG.md)，各批次决策见 [docs/decisions/](docs/decisions/)。
