# SummitWorkbench · Project Description

## 当前可靠性候选

2026-09-16 分支 codex/reliability-luna 已按执行方案完成 8 项可靠性优化。源码质量门为 1297 passed / 1 skipped；静态 bundle 源码身份 84db2d3，bundle 提交 dfe6655。当前尚未替换已安装 App，候选包 smoke、真实凭据、退出故障注入和双机新鲜度矩阵仍需发布前验证。

## 项目元信息

| 字段 | 内容 |
|---|---|
| 项目名称 | SummitWorkbench |
| 产品定位 | 外置执行管理层 + 第二大脑；作为工作知识库的**唯一写入方**（看板、采集、审批、源数据处理），**高级语义检索归属 SummitKnowledge** |
| 当前阶段 | 交付包仍为 `v0.4.7`；本轮为 `v0.4.9` 可靠性优化候选（分支 `codex/reliability-luna`），8 项失败收尾与状态可见性优化已完成，源码质量门通过；候选安装包与真机复验尚未完成。M3 与 P2-03 均不实施。 |
| MVP 主机 | Mac Studio |
| MVP 用户 | 单用户，项目发起人本人 |
| 主记录载体 | 独立 Obsidian 工作 vault |
| 外部系统 | 飞书 OpenAPI、可配置云端模型 API、私有 Git remote |
| 交互入口 | **原生 macOS 桌面 App**（自包含 bundle + WKWebView，正式入口，见 `docs/DESKTOP_APP.md`）、本地 Web 工作台 `wb web`（SPA：今日/审批/项目/设置；问答与指南页签已于 2026-09-16 下线，语义问答归 SummitKnowledge）、`wb` CLI（自动化与深度操作）、Obsidian 待确认页与每日笔记 |
| 权威规格 | `docs/product/PRD.md` v1.3 |
| 检索契约 | `docs/contracts/WORK-KB-RETRIEVAL-CONTRACT.md`（与 SummitKnowledge 共享的引用/状态/权威顺序契约） |

## Mission

让一个同时负责多条工作线的人，不再依靠记忆维持执行连续性。系统应主动收集可验证的工作信号和会议材料，把它们沉淀成可追溯的知识，再以有限、清晰、可确认的方式推动下一步行动。

## 核心问题

1. 项目状态分散，某条产品线可能在没有明确告警的情况下停摆。
2. 会议逐字稿存在，但没有稳定进入工作知识库，也没有转化为可审核的决策和行动项。
3. 每次启动 AI 工作会话都要重新选择目录、解释背景，历史上下文无法复利。
4. 大模型可以给建议，但如果事实、推断和写回权限没有分层，就会污染执行系统。

## MVP 能力

- 自动发现本人参加且可读取完整文本的新会议。
- 保存完整逐字稿与结构化会议笔记两个 Markdown 文件。
- 通过可配置云端模型提取事实、决策、明确行动项、未决问题与 AI 建议。
- 通过 Obsidian 集中待确认页批准、拒绝或修改执行性提取结果。
- 使用 `wb ask` 基于本地**块级**检索（SQLite FTS5/trigram + Python BM25 降级 + 多信号融合）生成带 `路径#区块` 来源的回答。
- 生成每日晨间简报和每周跨项目复盘。
- 对项目档案、会议笔记、工作记录和 inbox 做本地检索，并通过 `wb ask` 生成带来源回答；候选条数由路由计划统一决定。
- 通过 `wb task` 与 `wb note` 低摩擦录入承诺和想法。

## 关键产品规则

- PRD 是唯一权威规格；旧思考文档和旧架构图只作历史参考。
- 事实、待确认推断和 AI 建议必须分层保存和展示。
- 会议知识可自动归档，执行系统写回必须经过用户确认。
- 新会议自动处理；历史会议只按显式日期范围补导，默认不生成历史行动候选。
- 云端模型初始调用失败后，使用同一模型最多重试 3 次；耗尽后进入可见错误队列，不自动换模型。
- 模型调用逐次记录 token 与估算费用；月度预算是提醒线，不是新会议停机线。
- 待确认项达到 5 条或最老超过 3 天时才升级 macOS 通知。
- M1 验收全部通过后才能进入 M2。

## 技术方向

开发计划采用 Python 3.12+ 的本地 CLI/批处理架构，原因是它适合文件系统、HTTP API、Markdown、定时任务和测试驱动的集成工作。实现保持端口适配边界：领域逻辑不感知飞书或具体模型供应商，prompt 与输出 schema 不写死模型名称，vault 数据不因换模而迁移。

计划中的主要模块：

- `config`：分层配置、路径解析、Keychain 凭据引用，以及工作区级跨进程锁（`locking.py`，序列化并发触发源的 git 写序列与飞书 token 轮换，见 ADR 0016）。
- `domain`：会议、证据、审批项、项目、信号、模型用量等稳定类型与规则。
- `providers`：飞书 OpenAPI 和云端模型 API 适配。
- `repositories`：vault Markdown、幂等状态、错误队列、用量账本。
- `workflows`：会议、审批、问答、简报、周复盘、同步的编排；M3 交互式会话不在当前交付范围。
- `observability`：`wb status`、运行心跳与定时任务健康度、macOS 通知、预算和积压告警。
- `webapp`：可选本地 Web 工作台（FastAPI 提供 `/api/*` JSON 端点 + 静态托管；前端为 Vite + 原生 TS 构建的 SPA「今日工作台」，构建产物随包分发；未构建时回退服务端渲染，SSR 视图保留）。

定时触发由 `deploy/launchd/` 的 plist + `scripts/install-launchd.sh` 承担，不实现常驻服务，故无独立 `scheduling` 模块。

具体库与版本在首次代码批次中通过最小技术验证后锁定，不在本次无代码基线中添加依赖。

## 非目标

- 云端服务端、常驻守护进程或多用户部署。（后加入的 `wb web` 本地面板与原生 macOS 桌面 App 是**纯本地、按需启动**的可选便利层，复用同一套领域逻辑，不引入服务端、不改变数据边界——`.app` 双击启动 bundle 内 server + WKWebView 面板。）
- 本地模型、敏感会议分流或多模型自动切换。
- 在 SWB 内建向量数据库、Embedding、精排或语义 RAG。高级语义检索（多库切换 + 云端精排 + 多步生成问答）唯一归属 `SummitKnowledge`，工作库对 SK **只读**；SWB 只做块级本地检索与强制引用，并保证自动沉淀的 Markdown 满足共享检索契约。
- 下载飞书会议录像。
- 编排 WorkBuddy、读取飞书消息、通用云文档或多维表格。
- MVP 阶段在 Mac Air 部署自动任务。

## 开发者 / Agent 读取顺序

1. `docs/product/PRD.md`
2. `docs/archive/plans/DEVELOPMENT_PLAN.md`（历史实施计划，仅用于理解原始顺序）
3. 本文件
4. 与当前工作包直接相关的架构决策记录

不得从 `docs/archive/background/THINKING_DOC.md` 或当前旧版 `docs/archive/architecture/ARCHITECTURE.html` 恢复已被 PRD 推翻的设计。

## 当前交付边界（v0.4.7 build 34）

已交付可安装的 Python 工程、`wb` CLI、本地 Web 工作台与原生 macOS 桌面 App。M0 / M1 / M2、P1-07D、P2-01B、P2-02、v0.4.4 UI/UX 维护、v0.4.5 交付前清理、v0.4.6 指南版本标记修正与 v0.4.7 分发版（build 34）均完成并经真实数据/真机或本地交互验证；当前只保留 `main` 主线：

- **v0.4.7 build 34（交付包）**：修掉三项真机未决项并补上两项使用缺口。
  **D9**：dulwich 的 `can_fast_forward` 用 commit_time 剪枝挑公共祖先，跨机时钟偏差下会把真快进误判成分叉（冲突恢复成功但 push 报 non-fast-forward）；现在改为不看时间戳的图可达性复核，只在确认真快进时对该分支单 refspec 强推一次，**绝不无条件 force**。
  **D10**：`connect-local` 与 remote clone 过去无条件写 `device_role=secondary`，导致 marker 指定的主设备上定时自动化也不跑；现在按 vault 内 `automation-primary.json` 决定角色（别的设备持有则保持 secondary，绝不抢占）。
  **G1**：「设置 → 高级与维护」新增**定时自动化主设备**区块（本机 device id / 当前主设备与 generation / 本机角色），支持显式勾选 + `expected_generation` 的接管与**降级为备用设备**；声明成功后同步本机 profile 角色。
  **G2**：没有任何远端的工作台新增**首次发布到远端**（只接受空 HTTPS 仓库，先校验凭据与可推送，再 add origin → 首次 push → 写 Keychain；失败回到“没有远端”，绝不 force），不再需要手工 `git remote add`。
  **G3**：同步/推送失败落盘到独立服务日志 `~/Library/Logs/summitworkbench-server.log`（JSONL、0600、5 MiB 轮转），只写稳定原因码、计数与异常类名，绝不写 URL/主机/路径/凭据/正文，也绝不写进 vault。

- **v0.4.3 产品化基线 · P1-07D（ADR 0041）**：生产同步限定 HTTPS remote，提供可预览/回滚的 SSH → HTTPS 转换、只读 acceptance preflight 与双设备自动验收。候选包 build 23 已在 Mac Studio 与 MacBook Air 安装同一 DMG 并完成完整双机闭环，build 24 已完成双机增量冒烟，P1-07D 正式通过。

- **P2-01B（ADR 0042）**：仅针对已有 thread activity 事件切片接入 `shadow-read → dual-write`。保留旧 Markdown 结果为当前用户可见真源，新增事件投影对比、确定性差异诊断、一致性报告和可回退开关；覆盖乱序、重复事件、双设备离线写入、投影失败及新旧结果等价测试。全局 inbox、会议决策和项目正文暂不迁移。

- **P2-02（ADR 0043）**：冲突分类、只读详情/计划/校验、脱敏导出、临时 staging、事件自动收集、已登记 thread activity 视图重建、人工 Markdown/未知格式选择、未知派生视图 `preserve-both`、快照过期与脏工作树保护、显式确认后的普通双父恢复提交、脱敏审计和普通 push 均已实现。build 29 已在 Studio + Air 完成事件收集、已登记视图重建、Markdown/未知视图/binary 的双父恢复、脏工作树拒绝、审计失败可见性、普通 push 与最终同 HEAD，P2-02 已完成。

- **v0.4.4（ADR 0045）**：今日简报置顶、捕捉快捷行、会议导入抽屉、宽窄屏响应式两栏/单列、四张设置卡、高级功能折叠和绿色连接 ✓ 已落地；旧版飞书凭据迁移到 workspace scope，设置页与 OAuth 回调状态一致；过期 runtime record 不再因 PID 复用误报；网页简报生成显式提交本次生成路径，保持 dirty/sync 保护和旧入口兼容。build 9 起的 arm64 `INTERNAL-DEV` DMG 已完成本地门禁与真实工作区交互验收；v0.4.5 build 19 在此基线上只做清理与指南重写，不改产品行为。

- **v0.4.1 · 写路径并发加固 + 撤销 + 停滞语义（ADR 0027，P0/P0'/P1）**：全库「读 → 变换 → 整文件原子重写」RMW 原语（审批页/inbox/档案追加/当日笔记与快照/线程日志产物/项目建档激活归档/清扫）整体放入工作区锁（与 publish_brief / sync 同一把 .wb.lock；锁只包文件临界区，绝不跨 LLM/网络调用）；裸写全量改原子写；审批 apply 收尾乐观合并（并发勾选/编辑不被整页重写吞掉）；幂等账本容错读（坏行隔离 .quarantine）；线程日志/产物序号分配同锁防静默覆盖。系统侧写回成功后自动 git 留痕（显式路径 + `wb:` 前缀，非 git 优雅降级），面板顶栏新增 **「↩ 撤销」**（最近 `wb:` 提交差异预览 → git revert 一键还原；只作用于 vault 文件，飞书侧副作用不可撤销，界面文案明示）。档案 frontmatter `updated` 收窄为实质更新，日志/产物只刷新 **`activity_at`**：首页「最近活跃」读 activity_at，「>14 天未更新」与周复盘停滞点名读 updated，不再被机器高频活动刷失明。质量门 **514 项全绿**（ruff + format + mypy strict + pytest），前端重新构建并重新装机。

- **v0.4 · 业务线程 = vault 一等公民（ADR 0026，P0–P3）**：知识线程（FinanceOps / CoachFinance / EnrollmentProduct / ERPExplore 试点）无需 Work 文件夹与 git——`_vault/projects/*.md` 建档即入工作台，registry 全集（文件夹项目 + 线程）统一进首页/项目页/审批下拉；内部目录（下划线前缀）不进项目视野。审批路由扩展：**「跟进事项」落点**（他人行动项 → 主档案 `## 跟进事项` `- [ ] ` 责任记录，人工闭环）+ 线程 inbox（`_vault/inboxes/`）。**✎ 推进日志**（多线程 work-log + AI 摘要，模型不可用只存原文）与**存产物**（thread-doc：阶段总结/PRD/背景包/timeline，本地文件导入 + 拖放，可一键转「当前状态」草案）入库自动刷新档案 `updated`。**线视图** = 档案区块 + 时间线聚合（logs/artifacts/meetings），视图内直接日志/产物/刷新。线程信号（下一步/阻塞/未闭环跟进）进晨间简报；**>14 天无更新且有未决/未闭环跟进 → 周复盘「停滞项目」点名**（`weekly/collect.py::_collect_thread_stalls`，`THREAD_STALL_DAYS=14` 与卡片同口径）。项目显示名 = 档案 frontmatter `title`（`POST /api/projects/rename`）。第二大脑按线程检索（`answer_question(project=...)`）。顺带修复：未加引号 `updated`（YAML date 对象）读取归一（`vault.meta_date_iso`）。质量门 **491 项全绿**；P0/P1/P2 与 P3 第一批真机验收并装机，P3 停滞检测随本版装机后生效。
- **v0.3 · 工作台 → 飞书双向写回（ADR 0025）**：待办任务行尾 **✓ 一键完成**（`PATCH completed_at` 完成形态，真机核实 `update_fields` 白名单不含 `completed`）/ **✎ 行内编辑**（标题/截止，`PATCH summary/due`）；会议行尾 **✎ 行内编辑**（标题/起止时间，日历写 scope `calendar:calendar` 升级并重新授权）；审批候选落点新增 **「新建会议」**（`RouteTarget.FEISHU_MEETING` + 起止时间字段，批准 + 应用即在主日历新建定时日程事件，`MeetingCreator` 注入 + 候选 ID 审计幂等）。飞书 = 任务与日程唯一真源；本地只把当日渲染快照镜像一致（`signal_snapshot.mark_task_completed/mark_task_edited/mark_meeting_edited`），vault 简报 Markdown 一字不动。质量门 458 项全绿；日历/任务写回 2026-09-03 真机核实（建日程/改会议时间/改任务标题截止/一键完成闭环）。
- **M0** 地基：工作目录与 vault、项目档案、飞书身份与最小权限、`wb sync` 非破坏性同步、云端模型与用量账本冒烟。
- **M1** 会议进入第二大脑：会议发现与双文件归档、云端结构化、集中审批与写回（项目别名解析 + 未匹配零摩擦捕获）、`wb status` 状态/费用/积压、`wb ask` 带来源问答、`wb meeting import`/`backfill` 手动与历史补导。PRD L44 严格验收 6/6 真机通过。
- **M2** 晨间简报：`wb brief` 全链路（飞书日历/任务 + 项目扫描 → 模型排序/确定性回退 → 幂等写当日笔记）与 `wb weekly` 周复盘，均由 launchd 定时触发。
- **加固**：工作区跨进程锁、JSONL 容错读、飞书退避重试（ADR 0016–0018）；schema 版本号、运行心跳健康度、`wb doctor` 预检、飞书授权可见性（ADR 0019–0022）；GitHub Actions 质量门（macOS，360 项全绿）。
- **v0.2 · Web 工作台（SPA）**：`wb web` 升级为「今日工作台」——快速捕捉（AI 承诺/想法分类 + `#项目` 本地解析 + 失败兜底）、拖拽导入逐字稿全自动链路、待确认审批卡片、项目推进精选与「项目」页（ADR 0023）、简报与问答、内置「指南」页签；审批页即时批准/拒绝/修改 + 批量操作 + 预演/应用；`wb review sweep` 清理命令；`wb status --notify` 真正投递 macOS 通知。
- **v0.2 · 晨间简报 v2（ADR 0024）**：Web 面板把简报从纯文本清单升级为**组件化日程视图**——会议时间列、任务截止语义色 + 倒计时徽章、AI 选中任务行「分类 · 排名」注解（与待办清单合一）、非任务行动单列、提议/最近完成折叠；前端设计令牌全局换新（Linear 型 zinc + 靛紫，深浅双色）。数据经信号快照**附加演进**下发（`*_list` 明细字段），vault 内简报 Markdown 版式不变，旧快照自动回退旧视图。质量门 433 项全绿。
- **v0.2 · macOS 桌面 App**：自包含 `.app`（PyInstaller bundle server + 原生 Swift/AppKit + 受管 WKWebView），原子构建/安装/自更新、版本握手与构建身份校验（打包说明见 `docs/DESKTOP_APP.md`，历史生命周期方案见 `docs/archive/plans/PANEL_LIFECYCLE_AND_UPDATE_IMPLEMENTATION.md`）。

设计说明见 `docs/product/WEB_WORKBENCH.md`，使用指南见 `docs/product/WEB_USAGE_GUIDE.md`。

P2-01B 已完成，且仍严格限定于 thread activity；inbox、会议决策和项目正文继续沿用现有路径。P2-02 的实现、自动化质量门与 build 29 双机退出验收均已收口，**v0.4.7 build 34 是当前交付基线**（D9/D10/G1/G2/G3 五项收口）。M3（带上下文启动与收尾）和 P2-03（组织级云服务）均按产品所有者明确决定不实施。仓库与远端只保留 `main`，并已迁移到组织 `SummitYifeng/SummitWorkbench`；远端 CI 质量门（含 macOS arm64 构建矩阵与 packaged App smoke）全绿；变更记录见 `CHANGELOG.md`，最新本地验收见 `docs/acceptance/OPEN-VERIFICATION-ITEMS.md`。
