# SWB 工作台第一阶段验收报告

日期：2026-10-02
范围：`ONEDRIVE-WORKBENCH-IMPLEMENTATION-PLAN.md` 第一阶段 W0–W8
判定：**W0–W7 通过；W8 人工单机验收部分通过；第一阶段尚未通过阶段门。**

## 源码与安装包身份

| 项目 | 值 |
| --- | --- |
| 开始时 HEAD | `c89677cc8f73ec9bc6f7f5b297f44f9f4db66d1e` |
| 安装包源码提交 | `20d1f2172bbcf02760e5fe555eb92e7ba8eacbb2` |
| 交付版本 / build | `0.5.0 / 2026100202` |
| 架构 / 分发 | arm64 / `INTERNAL-DEV` ad-hoc |
| 前端 build identity | `v2026.10.02-49bc6d84` |
| 前端完整源码哈希 | `49bc6d842b6441cc1bec74e31c9a23588dcf39ab62dbeff04c9874f30caacda6` |
| App SHA-256 | `214b63e0d940d049f0a6dec7c5c8b05fac4f95b5f4349ebccce33831e99b47b1` |
| DMG SHA-256 | `86df00ffe7c0a517bfa1dc2478884ccbfad2ec1871494a7b074ffb3f03c18fd5` |
| 飞书凭据包内完整性 | `build-manifest.json` 报告 `complete=true`；凭据值未写入仓库、报告或诊断 |
| 更新 feed | 空；本地内部包不启用自动更新 |

安装包：[SummitWorkbench-0.5.0-arm64-INTERNAL-DEV.dmg](../../dist/releases/0.5.0/arm64/SummitWorkbench-0.5.0-arm64-INTERNAL-DEV.dmg)
产物目录：[dist/releases/0.5.0/arm64](../../dist/releases/0.5.0/arm64)（含 App、DMG、`SHA256SUMS`、`release-metadata.json`、`SBOM.json`、`test-manifest.json` 和 notary 摘要）。

前端身份由 build 日期和完整源码哈希确定，`release-metadata.json` 记录安装包源码提交。该包内 `build-meta.json` 的 `git_revision` 为空；因此前端溯源以完整 `source_hash` 和可复核的 `frontend_build` 为准。版本/build 与两项产物散列可在目录内的 `release-metadata.json` 重核。

## 工作包结果

| 工作包 | 结果 | 证据与实现 |
| --- | --- | --- |
| W0 冻结 | 通过 | [SWB-WORKBENCH-VNEXT.md](../product/SWB-WORKBENCH-VNEXT.md)、[SWB-WORKSPACE-CONTRACT-v1.md](../contracts/SWB-WORKSPACE-CONTRACT-v1.md)、[入口与副作用清单](SWB-WORKBENCH-ENTRY-INVENTORY.md)、共享模板和 `tests/fixtures/workspace-v1/` 样例/资格/批准向量。冻结三个入口、三个审批去处、逐版本批准及无工作库 Git。 |
| W1 初始化 | 通过 | 普通本地目录身份、兼容连接、损坏/不兼容拒绝；包级 smoke 在临时 HOME 与测试目录创建工作库，验证契约和 conventions 文件存在且无 `.git`。 |
| W2 写入与恢复 | 通过 | 原子本地文件写、工作区锁、操作回执和中断记录；回归断言覆盖已完成路径、不重放及中断后可检查。运行时没有自动 Git commit/push 调用点。 |
| W3 入口整理 | 通过 | capture、journal、会议导入/处理、收件箱提升、完整文档产物复用现有写入器；没有保存/列表/预览隐式模型调用的路径守卫。 |
| W4 审批与动作 | 通过 | 三个去处默认不选；批准证明绑定当前语义内容版本；Feishu task 经既有 outbox。自动测试只使用替身，没有创建真实飞书任务。 |
| W5 Git 退役 | 通过 | 工作台隐藏旧同步/冲突/撤销控制，停止打包后台 worker 和 launchd 安装；自动提交/推送出口无调用方。保留的旧同步模块为未注册的遗留源码。 |
| W6 选择性导入 | 通过 | 哈希绑定只读预览、显式选择写入、改源拒绝、保留原件、未知内容待整理、重复导入幂等及不继承旧批准的测试通过。 |
| W7 回归与打包 | 通过 | 本机 arm64 App 和 DMG 构建、ad-hoc 严格校验、包内凭据结构检查、动态端口服务 smoke、真实打包服务在隔离目录创建普通工作库的集成 smoke 均通过。 |
| W8 单机使用 | **部分通过** | 2026-10-02 在 arm64 Mac 通过 UI 实操快速捕获、工作思考、全文文档导入、项目页提升和知识沉淀提升；飞书任务表单已检查但没有提交；会议逐字稿已选择并归档，因隔离 HOME 没有模型配置而未结构化。现场证据与缺口见下文。 |

## 检查结果

- 全量 Python：`./.venv/bin/python -m pytest -q --cov=src/summit_workbench --cov-report=term --cov-fail-under=80` → **1366 passed, 1 skipped，覆盖率 82.11%**。跳过项是未设置包路径时的打包集成测试；同一测试已由发布脚本对实际 App 执行并通过。
- 发布脚本质量门：ruff lint、ruff format、mypy（228 源文件）、`tests/unit`（1266 passed）、Web 路由契约（2 passed）、全部前端契约和打包集成 smoke（1 passed）。
- 前端：`npm --prefix web run test:frontend` 全部通过；`npm --prefix web run build` 成功，产物身份与本报告所列一致。
- 凭据与包内容：`verify-macos-release.sh` 检查通过，包内完整标记为真，测试清单 13 项均为 passed。凭据来自本机已安装的可信内部包，临时 env 权限为 `0600`，构建结束删除；凭据没有传输到飞书。
- 包机：Mac `Mac16,12`，macOS `27.0.1`，arm64。本轮只对 localhost 和 `/tmp` 隔离目录发起打包服务 smoke；未登录飞书、未连 OneDrive、未连接旧 SK、未调用嵌入接口。
- 旧 `_vault`：未写入、未提交、未推送；用户提供的计划文件保持未跟踪，未纳入实现提交。

## W8 单机 UI 验收记录

- 运行产物为上表中的 arm64 `INTERNAL-DEV` App，前端身份显示 `v2026.10.02-49bc6d84`。通过 UI 选择新建的 `/tmp/swb-phase1-ui-workspace-20261002`；该库由打包 App 创建，`workspace.json` 标记 reader/writer `0.5.0`，没有 `.git`。App 在 macOS 辅助功能权限获准后可完整读取和操作。
- “记点什么”：输入合成句子并点“记入”，界面显示“已记入收件箱”；刷新后条目出现在收件箱。未调用 AI 建议。
- 工作思考：使用“问题缘起／思考展开／当前结论”表单保存，界面显示文件名。收件箱的“知识沉淀”去处也按三段式保存成功。两篇思考页面都包含 `approval.version`、内容 SHA-256、`approved_at` 与 `operation_id`。
- “更新项目”：在隔离库通过 UI 新建 `phase1-acceptance` 测试项目，把捕获条目提升到“下一步”并移出收件箱；项目页有 `wb-candidate` 幂等标记，操作结果给出目标路径。
- “存入文档／产物”：通过 UI 将完整合成文本保存到该测试项目档案，界面显示“已存入…（保留全文）”。产物文件保留全文，并附 `approval.version: 1`、`content_sha256`、`approved_at` 和 `operation_id`。未勾选同步覆盖项目“当前状态”。
- “导入会议”：用 `/tmp/swb-phase1-meeting-acceptance.txt` 选择真实本地文件。App 将逐字稿保存在隔离库 `meetings/transcripts/` 并记录 `fetched`、`archived` 状态。导入卡明确提示缺少隔离 HOME 的模型配置文件（`[models.meeting]` / `[models.shared]`），所以没有点击继续处理；没有连接外部模型，也没有生成结构化笔记或审批候选。审批页因此显示 0 条候选。
- “创建飞书任务”：打开收件箱提升表单并选择“飞书待办”，确认 UI 展示截止日期与默认同日开始日期，以及“库内只留审计痕迹”的说明。没有提交该动作，因此没有对真实飞书服务发请求或创建任务；这次 UI 检查不能证明飞书写回完成。
- 没有触发简报重新生成、AI 建议、会议结构化、全量嵌入、真实飞书登录或 OneDrive 连接。测试服务只绑定 `127.0.0.1`，退出按钮已关闭隔离 App；没有覆盖 `/Applications/SummitWorkbench.app`。测试库和逐字稿留在 `/tmp` 供人工复核。

## 未通过项与阶段门

第一阶段目前仍为**未验收**，第二阶段 OneDrive 新库与样板建设须等阶段门通过后再开始。剩余 W8 项目：

1. 为会议处理配置一个明确隔离、不会回退到生产端点的模型替身，完成逐字稿结构化、候选预览、来源回看及正式版本批准的 UI 流程；本次只验证了选择文件与本地归档。
2. 用飞书 API 替身或单独明确授权的人工验收目标，完成“创建飞书任务”的确认与写回结果核对；本次只检查了表单和日期字段，未提交外部动作。
3. 复查常见操作不要求用户填写内部类型或理解 Git/remote 状态；本轮已检查的捕获、思考、项目与文档流程均未要求填写 Git 信息。

## 可复制的后续交接提示

> 请继续 `docs/implementation/ONEDRIVE-WORKBENCH-IMPLEMENTATION-PLAN.md` 第一阶段 W8 单机验收，先在隔离测试目录使用 `dist/releases/0.5.0/arm64/SummitWorkbench.app`，按 `docs/acceptance/SWB-WORKBENCH-PHASE1-REPORT.md` 逐项实操三个输入入口和三个审批去处，记录 UI 结果与未通过项。不要连接真实旧 `_vault`、旧 SK 或 OneDrive 生产库；不要触发全量嵌入；自动测试不得创建真实飞书任务。W8 验收通过后再决定是否开始第二阶段。
