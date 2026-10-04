# SummitWorkbench

## 当前状态（2026-10-04）

当前开发与验收版本为 `0.5.0`。本机 MacBook Air 已安装 arm64 INTERNAL-DEV build `2026100401`，包内源码提交为 `1141155`，前端身份为 `v2026.10.04-b12c1720`。此包未发布，也不接自动更新。发布版本历史见 [CHANGELOG.md](CHANGELOG.md)；本机包身份与验收阶段见 [文档导航](docs/README.md)。

- **Phase 1：已完成。** W0–W8 和隔离单机验收见 [Phase 1 验收报告](docs/acceptance/SWB-WORKBENCH-PHASE1-REPORT.md)。该报告保留 build `2026100305` 等当时的交付身份。
- **Phase 2：已完成用户确认的样板验收。** OneDrive 样板库、导入材料和此前操作记录见 [Phase 2 验收报告](docs/acceptance/SWB-WORKBENCH-PHASE2-REPORT.md)、[导入清单](docs/acceptance/ONEDRIVE-SAMPLE-IMPORT-MANIFEST.md) 和 [快速使用说明](docs/product/ONEDRIVE-SAMPLE-QUICKSTART.md)。2026-10-04 用户确认阶段验收完成、OneDrive 同步已完成，三份虚构测试文件的删除也已同步。报告会保留原始过程，并补记后续确认证据。
- **Phase 3：尚未开始。** Studio → Air → Studio 双机验收须使用同一验收包；阶段顺序与工作库边界见 [四阶段计划](docs/implementation/ONEDRIVE-WORKBENCH-IMPLEMENTATION-PLAN.md) 和 [工作库契约 v1](docs/contracts/SWB-WORKSPACE-CONTRACT-v1.md)。

下文 0.4.x 交付与使用说明是历史版本背景，不描述 0.5.0 新工作库行为。

## 0.4.x 已发布版本背景（历史记录）

**最近已发布的 0.4.x 版本**：`0.4.11`（tag `v0.4.11`，提交 `6253d31`），由 CI build `25` 构建；
发布产物哈希与升级说明以 `AGENTS.md` 的交付基线及 `CHANGELOG.md` 为准。这里保留 0.4.x 行为史；
当前 0.5.0 INTERNAL-DEV 包未发布、无自动更新 feed，见上方阶段报告。

本版修一个**用户可见的同步阻断**：打包 App（固定 dulwich）× **HTTPS 远端一直无法同步**
（`porcelain.fetch` 在 dulwich 1.2 不再接受 `pool_manager`，调用点未跟上 ⇒ `unclassified`
「未分类的同步失败」）。详见 [CHANGELOG.md](CHANGELOG.md) 的 `[0.4.10]`。
该批次门禁在 `4e91469` 上实测 **1399 passed / 1 skipped、覆盖 84.55%**；这是 0.4.10 的历史基线。

> 上一份交付 `0.4.9 / build 2026091925`（本机构建，无更新 feed）**不要再用**——它同样带这个
> 同步 bug。装机与升级步骤见
> [从 0 装机核对清单](docs/acceptance/FRESH-INSTALL-STUDIO-AIR.md)。

本版（相对 `0.4.9`）还含 2026-09-15～09-19 的全部批次：收件箱提升通路（契约 §10）、
「日常手记」「工作思考」两个写入入口、批次 A 语料边界、跨端闸门 8 步、写回双空行与 `inbox.md`
手写条目路由两处用户可见修复，以及一批纯代码简化重构。

剩余人工/跨端确认见 [未验证清单](docs/acceptance/OPEN-VERIFICATION-ITEMS.md)，逐版变更见
[CHANGELOG.md](CHANGELOG.md)，发布流程与内置凭据见 [docs/RELEASING.md](docs/RELEASING.md)。

## 0.4.x 历史交付与产品说明

以下内容描述 0.4.x 的 Git 工作库、定时任务与产品行为。0.5.0 新工作库行为以本文顶部阶段状态、四阶段计划和工作库契约 v1 为准。

### 2026-09-18 交付状态（历史）

修掉三处会持续制造新错误的问题：SSH（SCP 形状）remote 的 push 被误判为不存在的本地路径、逐字稿结构化失败的真因是输出预算被思考模式推理吃光、原生壳不显示 Dock 图标。内容层面：会议笔记不再生成 `## AI 建议`（九区块减为八区块），决策页新增「只记业务结论」硬规则与机器守卫。设置页按使用者偏好精简为三张主卡（工作区 / AI 模型 / 飞书，每张一行），自动化与模型参数移入「高级与维护」。该轮详情见 `CHANGELOG.md`。

使用说明见 [桌面版使用指南](docs/product/WEB_USAGE_GUIDE.md) 与 [`docs/DESKTOP_APP.md`](docs/DESKTOP_APP.md)。

SummitWorkbench 是 macOS 本地工作台，整理项目状态、会议记录、工作输入及飞书日历／任务。0.5.0 将工作内容放入由用户选择的可移动工作库，并以版本批准控制正式内容；OneDrive 负责跨设备文件同步。

> **已发布基线为 `v0.4.11`；当前本机内部验收包为 `0.5.0 / build 2026100401`，包内源码提交 `1141155`。** 0.5.0 尚未发布到更新通道。仓库不含凭据：飞书应用默认凭据只在构建期注入，流程见 [docs/RELEASING.md](docs/RELEASING.md)。

## 产品解决的问题

用户同时负责多条产品线，工作信息散落在 Git 仓库、飞书会议、任务和临时记录里。真正的风险不是“少记了一条笔记”，而是项目静默停摆、会议结论没有进入执行系统、过去做过的工作无法被后续 AI 会话可靠复用。

SummitWorkbench 将这套工作方式收敛为两层能力：

- **外置执行管理层**：每天从可验证信号中挑出最多 5 个行动，提醒停滞、承诺和阻塞，但不把模型推断冒充事实。
- **第二大脑**：自动保存会议逐字稿与结构化笔记，积累项目状态、决策和工作记录，供 SummitKnowledge 只读检索。

> **与 SummitKnowledge 的边界**：SWB 是工作库的**唯一写入方**（看板、采集、审批、源数据处理），
> 保证自动沉淀的 Markdown 可被稳定索引、引用与判权威；**高级语义检索（向量召回、云端精排、
> 多步生成问答）唯一归属 [SummitKnowledge]**，工作库对 SK 只读。共享契约见
> [`docs/contracts/WORK-KB-RETRIEVAL-CONTRACT.md`](docs/contracts/WORK-KB-RETRIEVAL-CONTRACT.md)。

## 预期的日常图景

Mac Studio 在后台定时拉取新会议纪要并写入 Obsidian。会议原文和结构化笔记自动归档，可能改变项目或任务状态的内容进入集中待确认页。用户只需勾选、忽略或原地修改候选项，再批量应用。

> **用户日常入口 = 桌面 App 内的 Web 面板，不用 CLI。** 真人用户只打开桌面 App 完成全部日常工作；
> 直接运行 `wb web` 时才使用默认的 `http://127.0.0.1:8787`（捕捉/审批/导入/项目，见
> [WEB_USAGE_GUIDE](docs/product/WEB_USAGE_GUIDE.md)）；CLI 保留给自动化（launchd、脚本、
> `wb review sweep` 等）与深度操作。因此**开发任何用户可见功能都以 Web 面板为默认交付面**，
> 改动后必须重建前端产物并重启面板服务才生效（见
> [WEB_WORKBENCH §8](docs/product/WEB_WORKBENCH.md) 与 [DESKTOP_APP](docs/DESKTOP_APP.md)）。

每天 08:00 前，`wb brief`（由 launchd 定时触发）把 Obsidian 的**晨间指挥台**写在本机程序目录（不在知识库内）：显示会议、最近完成、项目状态和最多 5 个建议行动。每周一 `wb weekly` 生成跨项目复盘，帮助重新分配注意力。

### 0.4.x 实施进度（历史）

下列 M0–M4 里程碑记录 0.4.x 产品线，不表示 0.5.0 工作库阶段进度；当前进度见本文开头。

### 0.4.x 文档优先级（历史）

发生冲突时，按以下顺序判断：

1. [四阶段工作台实施计划](docs/implementation/ONEDRIVE-WORKBENCH-IMPLEMENTATION-PLAN.md) 与 [工作库契约 v1](docs/contracts/SWB-WORKSPACE-CONTRACT-v1.md)——0.5.0 新工作库的范围、门槛与数据语义。
2. [验收报告](docs/acceptance/)——按具体版本和阶段记录已验证事实、用户确认及剩余缺口；历史快照不覆盖较新的验收记录。
3. [产品需求文档](docs/product/PRD.md)——主要描述 0.4.x 既有产品行为；与新版工作库计划冲突时，以新版计划和契约为准。
4. [项目说明](PROJECTDESC.md)——面向开发者与 AI Agent 的稳定项目摘要；修改架构后应同步更新。
5. [架构决策记录](docs/decisions/README.md)——历史实现决策与验证结论。
6. `docs/archive/` 下文档均为历史资料，不作为当前目录结构或行为的依据。

## 仓库结构

```text
SummitWorkbench/
├── README.md / PROJECTDESC.md / config.example.toml
├── docs/
│   ├── README.md         # 当前契约、活文档、阶段报告与历史资料导航
│   ├── product/          # 使用指南、产品说明与 0.4.x PRD
│   ├── archive/          # 已完成阶段的背景、计划、旧验收、设计预览与**已完结的实施/交接记录**
│   ├── decisions/        # 当前架构决策记录（ADR 0043–0045；历史 ADR 见 archive/decisions/）
│   ├── acceptance/       # 发布、阶段与人工环境验收报告
│   ├── implementation/   # 当前实施计划、工作包盘点与历史拆分指路 stub
│   ├── contracts/        # API/路由契约
│   └── DESKTOP_APP.md    # macOS .app 打包说明
├── src/summit_workbench/
│   ├── cli/              # wb 命令入口
│   ├── config/           # 分层配置、路径、Keychain 引用、工作区跨进程锁
│   ├── domain/           # 领域模型、稳定 schema、状态机、纯规则
│   ├── providers/        # 飞书与云端模型适配（含公共退避重试）
│   ├── repositories/     # vault / 状态账本 / 用量账本 / 原子写 / JSONL 容错读
│   ├── workflows/        # meetings·review·brief·weekly·sync 编排
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
2. **M1 会议进入第二大脑** ✅：会议拉取、双文件归档、云端结构化、集中审批、状态与费用。
3. **M2 晨间简报** ✅：事实采集、行动排序、每日简报（`wb brief`）与每周复盘（`wb weekly`）。
4. **M3 带上下文启动与收尾**（本期不实施）：不新增交互式工作会话编排。
5. **M4 分流录入**（规划中）：`wb task`、`wb note` 与 inbox 路由。

M1 的真实会议、问答、审批、故障恢复、费用和积压测试（PRD L44 严格验收 6/6）在进入 M2 前全部真机通过（验收记录已并入 `docs/decisions/` 的 M1 ADR 索引）。

## 硬边界

- MVP 只在 Mac Studio 开发、部署和验收；Mac Air 不进入首版。
- 产品进程本地运行，模型推理全部使用可配置的云端模型 API；不引入本地模型。
- 所有会议内容可进入已配置的云端模型；录像不下载、不发送。
- 未经用户确认的会议提取项不得写入项目状态或创建飞书任务。
- **不建云端服务端、常驻守护进程、向量库或语义 RAG。** 后加入的本地 Web 面板（`wb web`）与原生 macOS 桌面 App 均为**纯本地、按需启动**的可选便利层：它们只复用既有领域逻辑、不引入服务端、不改变数据边界（`.app` 双击启动 bundle 内 server + WKWebView 面板，服务仍是 `127.0.0.1` 上的同一套本地面板）。检索与问答归 SummitKnowledge，SWB 只负责工作库写入、结构与审批边界。
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
- `wb brief [--date --dry-run --commit --push --json]`：生成今日晨间简报，幂等写入**本机程序目录** `~/Library/Application Support/SummitWorkbench/profiles/<workspace_id>/briefs/YYYY-MM-DD.md`（锚点区块只替换不重复；**不在知识库内**）；排序失败走确定性回退并在首行标注降级。`--commit` / `--push` 是显式无操作（库内已无简报文件可提交）；网页端一键生成只提交快照/用量/授权状态等 `_signals/` 机器状态（已 gitignore），不会使用 `add -A` 带入用户其他改动。
- `wb weekly [--date --dry-run --commit --push --json]`：从 git 提交 + 会议决策 + inbox + 停滞项目重新汇总上周复盘，幂等写入**本机程序目录** `…/profiles/<workspace_id>/weekly/YYYY-Www.md`（**不在知识库内**）；`--commit` / `--push` 同样是显式无操作。
- `wb status [--json --notify]`：汇总会议处理进度、当月 token 与估算费用、软预算、待确认积压、定时任务健康度与飞书授权健康度；`--notify` 按去重规则把新通知真正发到 macOS 通知中心（供 launchd 定时调用，积压/费用/任务失败会主动提醒你）。
- `wb model smoke`：云端会议模型结构化冒烟，含 token 与费用记账。
- `wb sync`：以 git remote 为唯一真源，非破坏性批量同步 `~/Documents/Work/` 下各仓库与 vault。

本机配置放 `~/.config/summit_workbench/config.toml`（模板见 [config.example.toml](config.example.toml)）；所有凭据只进 macOS Keychain，不进仓库。定时任务安装见 [deploy/launchd/README.md](deploy/launchd/README.md)，桌面 App 打包见 [docs/DESKTOP_APP.md](docs/DESKTOP_APP.md)。

质量门：`scripts/pre-push-gate.sh` 会在推送前执行 actionlint/ref、`uv lock --check`、ruff、mypy、pytest 覆盖率、前端 TypeScript/契约、secret scan、原生更新行为和空白检查；前端生产构建与打包 App 由发布门执行。远端日常质量门（[`.github/workflows/ci.yml`](.github/workflows/ci.yml)）永久只接受 `workflow_dispatch` 手动触发，push 和 PR 不会自动消耗 runner；需要时使用 `gh workflow run ci.yml --ref main`。

建议运行 `scripts/install-git-hooks.sh` 安装 pre-push hook：`scripts/pre-push-gate.sh` 会执行与 CI 相同的本地质量检查，并在 push 前校验每个 `uses:` 的 action ref 是否真实存在。远端 CI 不会随 push/PR 自动运行，避免账单或额度异常时产生无意义的失败记录。

尚未取得验证证据的项集中在 [`docs/acceptance/OPEN-VERIFICATION-ITEMS.md`](docs/acceptance/OPEN-VERIFICATION-ITEMS.md)——那是该清单的单一真源，其他文档只链接过去。

## 版本

`v0.1.0`（首个发布版）→ `v0.2.0`（Web 工作台产品化 + macOS 桌面 App 正式化 + 晨间简报 v2）→ `v0.3.0`（工作台 → 飞书双向写回，真机核实）→ `v0.4.0`（知识线程项目）→ `v0.4.1`（维护加固）→ `v0.4.2`（打包修复）→ `v0.4.3`（P1-07D/P2-01B/P2-02 产品化基线）→ `v0.4.4`（UI/UX 与交付稳定性维护版）→ `v0.4.5`（交付前清理 + 指南重写）→ `v0.4.6`（指南版本标记改为抗漂移，build 20）→ `v0.4.7`（分发版与本机服务日志）→ `v0.4.8`–`v0.4.11`（迭代维护；最新发布为 `v0.4.11`，详见 [CHANGELOG.md](CHANGELOG.md)）→ `v0.5.0`（新版工作库，当前为内部验收包，阶段状态见本文开头）。当前仅保留 `main` 主线；各批次决策见 [docs/decisions/](docs/decisions/)。
