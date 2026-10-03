# W0 冻结记录：共享接口与写入链路盘点

日期：2026-10-03  
源码起点：`73795a8`（契约 v1 与合成一致性样例已在此提交冻结）  
当前核对提交：`04a43b58d4ae5ddf7c7a5587d05819710f45ffae`

本记录只核对 W0 冻结产物与当前入口，不修改工作库。产品目标以 `ONEDRIVE-WORKBENCH-IMPLEMENTATION-PLAN.md` 第 1、4 节为准。用户已确认三个输入入口（记点什么、导入会议、存入文档／产物）、三个审批去处（沉淀知识、更新项目、创建飞书任务）、正式内容版本逐版批准、OneDrive 外部同步、工作库不使用 Git。

## 冻结产物和跨端语义

- 共享契约：[SWB-WORKSPACE-CONTRACT-v1.md](../contracts/SWB-WORKSPACE-CONTRACT-v1.md)，在 `73795a8` 已先于本轮代码修复冻结；包含路径无关 UUID 库身份、兼容版本门槛、批准指纹、可检索资格、排除类型及引用锚点规则。
- 样例：[tests/fixtures/workspace-v1](../../tests/fixtures/workspace-v1/README.md) 使用固定虚构身份与操作 ID，不含真实用户材料。`vectors.json` 给出批准散列输入与期望值；`qualification.json` 覆盖批准会议、归档决策、变更后失效的产物、未批准手记、即使带匹配批准也排除的原件。
- 真库规范交叉核对：旧 `_vault/conventions.md` §9.1 的 `source_id` / `heading` / `anchor`、`#` / `##` 区块边界、原件与逐字稿排除、待审内容排除与当前契约一致。v1 增加显式版本批准证明；不能以旧库 `status` 单独推断新库批准状态。
- 初始化模板：[templates/workspace/conventions.md](../../templates/workspace/conventions.md) 为通用说明，不复制旧库项目清单或绝对路径。

一致性测试：`tests/unit/test_workspace_contract_v1.py`。当前阶段完整单测曾于 build `2026100304` 通过；本轮继续核对时还会针对 W0 样例单独运行。

## 当前写入入口登记

| 入口／动作 | 代码入口 | 写入／副作用 | W0 判定与后续包 |
| --- | --- | --- | --- |
| 随手输入 | `routers/capture.py::api_capture` | 写收件箱；无模型 | 保留为主入口，W2/W3 迁移为本地操作账本与统一结果模型 |
| 日常手记／工作思考 | `routers/journal.py` | 正式 Markdown、项目活动字段 | 必须逐版本批准；W2/W3 覆盖并发、恢复与写入资格 |
| 会议导入／重试／后台处理 | `routers/meetings.py`、`webapp/meeting_import.py` | 保存不可变逐字稿、作业状态、模型结果与审批候选 | 明确导入动作才调用模型；W2/W3/W4 迁移任务状态与审批语义 |
| 文档／产物 | `routers/threads.py`、`repositories/thread_notes.py`、`workflows/selective_import.py` | 来源全文、派生产物、当前项目档案 | 全文保留；保存来源不等于批准产物；W3/W4/W6 收口 |
| 收件箱建议／提升 | `routers/inbox.py` | 显式建议调用模型；提升到项目、思考或飞书任务 | 目标由用户选；任务仍经 outbox；W2/W3/W4 统一卡片与回执 |
| 项目新建／改名／状态／归档 | `routers/projects.py`、`repositories/project_registry.py`、`note_status.py` | 建页、改元数据和状态 | 项目语义变化需重新批准；归档生命周期独立；W1/W2/W4 |
| 内容批准 | `routers/review.py::api_review_content_approve` | 对当前页原子记录 `approval` 并改 status | 用户手动批准；正文/语义字段变化后旧证明失效；现已接入 UI |
| 会议候选决定／编辑／应用 | `routers/review.py`、`routers/review_apply.py`、`workflows/review_apply.py` | 审批记录、知识/项目写回、飞书 outbox 外部动作 | 三个业务去处保留；结果逐项展示；W2/W4 |
| 飞书既有任务／会议操作 | `routers/capture.py` 的 task / meeting 更新端点 | 直接更新或完成远端记录 | 属已有任务操作，不是审批第四去处；按 W0 盘点保留并验证账户与幂等 |
| 简报／周复盘 | `routers/brief.py`、`workflows/brief/`、`workflows/weekly/`、CLI 与 launchd | 本机展示文件、使用统计；可能读取模型和飞书 | 保留展示功能；只用已批准正式内容；取消后台无人值守库写入；W2/W5 |
| 草稿／本机设置／授权 | `routers/drafts.py`、`routers/settings.py`、`routers/settings_connections.py` | 本机草稿、profile、Keychain / OAuth 状态 | 秘密不入库；切库前排空任务；W1/W2 |
| Git 同步／冲突／恢复／迁移 | `routers/sync*.py`、`workflows/sync*`、`workflows/workspace_migration.py` | 工作库 fetch / commit / push / merge / remote 迁移 | 产品中退役。W5 必须删除后台调用链及误导状态，不可只删界面；源码 Git 与发布 Git 保留 |
| CLI 写入 | `cli/meeting.py`、`cli/review.py`、`cli/project.py`、`cli/import_markdown.py`、`cli/brief.py`、`cli/weekly.py`、`cli/feishu.py`、`cli/sync.py` | 内容导入、写回、外部动作、摘要与 Git 同步 | 必须按单一批准和本地 mutation 规则迁移；Git 工作库命令退役并提示替代流程 |
| 其他计划任务 | `scripts/install-launchd.sh`、`cli/brief.py`、`cli/weekly.py`、`cli/status.py` | 定时简报、周复盘、通知或统计 | W5 取消关闭 App 后仍运行的写者；若保留，必须绑定活动 App 与库身份 |
| 原生壳 | `native/SummitWorkbench/`、onboarding 与目录选择 | 选目录、启动／退出本地服务、应用安装与升级 | W1 保留目录选择；默认关闭 GitHub 自动检查／下载；W7 只交付本地 arm64 DMG |

现有统一写入基础：`MutationRuntime.run` → `run_local_mutation` → `workspace_lock` 与本地变更日志；Markdown／JSON 单文件落盘复用 `repositories/_atomic.py`；飞书创建复用 `external_action_outbox.py` 与 `create_task_through_outbox`。后续包继续复用它们，禁止另造第二套落盘、锁或 outbox。

## 本轮冻结的处置表

- 入口保留：三个主入口、日常手记与工作思考快捷模板、项目上下文编辑。
- 审批去处：沉淀知识、更新项目、创建飞书任务。内容版本批准与外部飞书动作彼此独立；一次内容批准不构成创建任务的授权。
- 输入保存、列表、打开卡片和预览不调用模型。模型只由用户明确的整理按钮触发；已有模型结果在跨设备账本中可复用。
- 外部动作：沿用已存在的飞书 outbox、稳定候选 ID 和未知结果不重 POST 规则。自动测试仅用替身，不创建真实飞书任务。
- 同步：OneDrive 客户端是唯一同步执行者。SWB 只报告本机文件状态，不显示 Git ready / 云端已同步等误导信息。
- Git：仅源码仓库、依赖与安装包发布流程可用 Git；工作库启动、写入、CLI、定时任务均须无 Git 依赖。同步／冲突／撤销页面移除必须晚于完整调用链盘点。
- SK：第一阶段冻结共同输入与样例；不得连接旧 SK、索引真实新库或触发嵌入。SK 实现仅第四阶段执行。

## W0 结论与门槛

W0 冻结接口和样例已具备；本记录补全当前 Web／CLI／后台写入入口及退役边界。W0 不代表 W1–W8 已完成。下一包 W1 的范围仅限库初始化、身份／兼容性、目录切换、凭据本机保存及恢复，不混入 W2–W5 的大规模写入和界面重构。
