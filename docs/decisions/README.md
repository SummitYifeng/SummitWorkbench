# 架构决策记录（ADR）索引

按工作包记录关键决策与真机验证结论。文件名带里程碑标识；编号顺序按落地时间，
不严格等于里程碑顺序（M0-6 先于 M0-5 落地）。

| ADR | 里程碑 | 主题 |
|---|---|---|
| [0001](0001-m0-1-tech-stack.md) | M0-1 | 工程与质量技术栈（uv / Typer / Pydantic / httpx / pytest / ruff / mypy）|
| [0002](0002-m0-2-project-migration.md) | M0-2 | 工作目录与 4 项目迁移（iCloud 边界、状态校验）|
| [0003](0003-m0-3-vault.md) | M0-3 | 工作 vault 结构、frontmatter schema、私有远端 |
| [0004](0004-m0-4-feishu-identity.md) | M0-4 | 飞书身份授权、最小权限、refresh token 轮换 |
| [0005](0005-m0-6-cloud-model.md) | M0-6 | 供应商无关云端模型、结构化输出、用量费用账本 |
| [0006](0006-m0-5-work-sync.md) | M0-5 | work-sync 非破坏性批量同步 |
| [0007](0007-m0-10-meeting-note.md) | M0-10 | 会议纪要拉取（会议号 → note_id → 逐字稿），tenant token |
| [0008](0008-m1-1-schema-state-machine.md) | M1-1 | 会议链路稳定 schema、处理状态机、幂等键、审批候选与路由 |
| [0009](0009-m1-2-discovery-archive.md) | M1-2 | 会议发现与原文归档：状态账本、证据层落盘、幂等编排、`wb meeting` |
| [0010](0010-m1-3-structured-processing.md) | M1-3 | token 预算分段、证据约束、结构化笔记、错误队列与失败恢复 |
| [0011](0011-m1-4-review-writeback.md) | M1-4 | 稳定候选、集中审批、dry-run 写回、项目别名解析、未匹配零摩擦捕获（`wb project`/`wb meeting import`）、审计与双层幂等 |
| [0012](0012-m1-5-status-budget-backlog.md) | M1-5 | `wb status` 聚合、月度软预算告警、待确认积压阈值与去重通知 |
| [0013](0013-m1-6-second-brain-qa.md) | M1-6 | `wb ask`：本地召回、只引用进上下文来源、事实/建议分区、冲突并列、qa-insight |
| [0014](0014-m1-7-historical-backfill.md) | M1-7 | `wb meeting backfill`：本地逐字稿补导、费用预估+跨预算再确认、幂等续跑、historical 候选 |
| [0015](0015-m2-morning-brief.md) | M2 | 晨间简报全链路 + launchd 定时提交 + 周复盘 |
| [0016](0016-workspace-lock.md) | 韧性加固 | 工作区级跨进程锁（`config/locking.py`）：飞书 refresh_token 轮换与 git 写序列互斥（LHF #1）|
| [0017](0017-jsonl-tolerant-read.md) | 韧性加固 | JSONL 日志容错读 + Pydantic 逐行兜底（`repositories/_jsonl.py`）：半截行/缺键行跳过+隔离，不再整本崩溃（LHF #2）|
| [0018](0018-feishu-retry.md) | 韧性加固 | 飞书 HTTP 复用公共退避重试 + 尊重 Retry-After（`providers/_resilient.py`）：瞬时抖动自动重试、半开连接防护（LHF #3）|
| [0019](0019-schema-versioning.md) | 正式使用前加固 | 持久化状态 schema 版本号（`repositories/_schema.py` 中央登记表）：机器状态落盘打 `schema_version`，为未来演进留迁移锚点（加固 #1）|
| [0020](0020-run-heartbeat-health.md) | 正式使用前加固 | 运行心跳 + 定时任务健康度（`_signals/run-heartbeat/` + `domain/run_health.py`）：连续失败≥3 去重告警，`wb status` 可见（加固 #2）|
| [0021](0021-doctor-preflight.md) | 正式使用前加固 | 统一预检 `wb doctor`：底座/vault/飞书/模型/launchd 端到端就绪表，默认离线无副作用（加固 #3）|
| [0022](0022-feishu-reauth-visibility.md) | 正式使用前加固 | 飞书 token 失效降级 + 可见性（`_signals/feishu-auth.json`）：失效醒目提示 `wb feishu login`，简报仍降级照出（加固 #4）|
| [0023](0023-workbench-project-curation.md) | v0.2.0 Web 工作台 | 首页「项目推进」精选清单 + 「全部项目」页（`_vault/projects/*.md` 建档 status 驱动，解决百级文件夹平铺）|
| [0024](0024-morning-brief-v2-web-rendering.md) | v0.2.0 晨间简报 v2 | Web 面板简报组件化日程视图（信号快照附加演进下发明细 + 清单合一 AI 注解 + 全局设计令牌换新；vault Markdown 版式不变）|
| [0025](0025-workbench-feishu-bidirectional-writeback.md) | v0.3.0 双向写回 | 工作台 → 飞书写回闭环：一键完成/行内编辑任务与会议、审批新建日历日程（飞书=唯一真源 + 快照镜像；日历写 scope 升级与重授权；完成走官方专用端点）|
| [0026](0026-knowledge-thread-projects.md) | v0.4.0 知识线程项目 | 业务线程 = vault 一等公民（P0–P3）：线程无 Work 文件夹建档入工作台、审批「跟进事项」落点 + 线程 inbox、✎ 日志/存产物（本地文件导入/拖放/一键转当前状态）、线视图（档案区块 + 时间线）、线程信号进简报 + >14 天停滞进周复盘点名、显示名（frontmatter title）、updated 归一 |
| [0027](0027-write-path-hardening-undo-activity.md) | v0.4.1 维护加固 | 写路径并发加固 + 系统写回自动留痕与面板撤销 + 停滞语义修复（P0/P0'/P1）：全库 RMW 加工作区锁与原子写、apply 乐观合并、幂等账本容错读、线程序号防撞；autocommit（wb: 提交）+ /api/undo/* 一键还原（只作用 vault 文件）；updated=实质更新 / activity_at=活动痕迹拆分（>14 天停滞点名不再被机器活动刷失明）|
| [0028](0028-external-action-outbox.md) | v0.4.1 加固 P0-04 | 飞书外部动作 Outbox 与不确定态：prepared/sending/succeeded/failed/unknown/reconciled 状态机、请求指纹、unknown 禁止自动重试、人工核对 |
| [0029](0029-workspace-profile-device.md) | v0.4.1 加固 P0-07 / P0-07C | ✅ 已实现：Workspace/Profile/Device 与 production active-profile 运行时接线 |
| [0030](0030-packaged-git-backend.md) | v0.4.1 加固 P0-09 / P0-09C | ✅ 已实现：双 Git backend、workspace-scoped HTTPS 凭据、remote clone 与 packaged certifi TLS 信任链 |
| [0031](0031-multi-device-sync.md) | v0.4.1 加固 P0-10 / P0-10C | ✅ 已实现：同步持久状态、全写边界与 automation-primary 声明 |
| [0032](0032-macos-distribution.md) | v0.4.1 加固 P0-13 | ✅ M2+ arm64 内部 DMG 与 ad-hoc 发布流水线；真机验收待执行 |
| [0033](0033-app-automation-service.md) | v0.4.1 加固 P1-01 | ✅ App 内自动化 worker、主设备门控与 SMAppService helper |
| [0034](0034-workspace-schema-migration.md) | v0.4.1 加固 P1-02 | ✅ 工作区 schema 迁移、备份、同步就绪门与安全回滚 |
| [0035](0035-webapp-route-service-split.md) | v0.4.1 加固 P1-03 | ✅ Web route contract、显式 AppContext 与兼容拆分边界 |
| [0036](0036-frontend-feature-lifecycle-boundaries.md) | v0.4.1 加固 P1-04 | ✅ 前端 feature 边界、typed API client 与 workspace 生命周期 |
| [0037](0037-diagnostics-privacy-supportability.md) | v0.4.1 加固 P1-05 | ✅ 诊断包、结构化日志、脱敏与本地可支持性 |
| [0038](0038-ci-coverage-release-matrix.md) | v0.4.1 加固 P1-06 | ✅ CI、80% 覆盖率门与 M2+ arm64 发布矩阵 |
| [0039](0039-signed-update-feed.md) | v0.4.1 加固 P1-07C | 🚧 v0.4.2 真机安装/创建 workspace/更新检查通过；Dulwich 修复与双设备同步验收转入 P1-07D |
| [0040](0040-thread-activity-events.md) | P2-01A | ✅ thread activity 事件模型、不可变存储与确定性投影；未迁移其他热点 |
| [0041](0041-remote-normalization-acceptance.md) | P1-07D | ✅ HTTPS remote 规范化、只读 preflight 与双设备验收；候选包 build 23 已在 Studio + Air 同包闭环 |
| [0042](0042-thread-activity-shadow-read-dual-write.md) | P2-01B | ✅ 仅 thread activity 事件切片的 shadow-read → dual-write、一致性报告、诊断与回退开关；不迁移其他热点 |
| [0043](0043-sync-conflict-explanation.md) | P2-02 | 🚧 冲突解释、临时准备、显式本地恢复、脱敏审计与普通 push；未知派生视图人工保留双方回退已接入 |

M0/M1/M2 全部完成；PRD L44 严格验收 6/6 真机通过（M1 验收见 ADR 0008–0014）。
底层韧性评审产出 3 条低垂果实，LHF #1（ADR 0016）、#2（ADR 0017）、#3（ADR 0018）已全部落地；
配套的写侧原子写归并（`repositories/_atomic.py`）随 LHF #2 一并完成。
正式使用前再做四项加固（ADR 0019–0022）+ CI 质量门/覆盖率体检，`v0.1.0` 首发；
随后 Web 工作台产品化、macOS 桌面 App 正式化与晨间简报 v2（ADR 0023–0024），`v0.2.0` 发布版；
工作台 → 飞书双向写回与真机核实（ADR 0025），`v0.3.0` 发布版；
知识线程改造 P0–P3（ADR 0026），`v0.4.0` 发布版（M3 仍未开始）。
写路径并发加固 + 系统写回自动留痕与面板撤销 + 停滞语义修复（ADR 0027），`v0.4.1` 维护加固发布（M3 仍未开始）。
多设备与可分发产品化已完成 P1-07D：候选包 build 23 已在 Mac Studio 与 MacBook Air
安装同一 DMG 并完成完整双机验收，进入 P2-01B 的前置门已解除。P2-01B 仅针对已有
thread activity 事件切片接入 `shadow-read → dual-write`，提供确定性投影对比、差异诊断、
一致性报告和可回退开关；暂不迁移全局 inbox、会议决策或项目正文。M3 仍未开始。
