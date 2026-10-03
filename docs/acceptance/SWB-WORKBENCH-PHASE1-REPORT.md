# SWB 工作台第一阶段验收报告

日期：2026-10-03（W1 收口、W7 重打包与 W8 交接复核）
范围：`ONEDRIVE-WORKBENCH-IMPLEMENTATION-PLAN.md` 第一阶段 W0–W8
判定：**W0–W8 通过。最终源码已重建 arm64 包并通过包级隔离 smoke；W8 UI 操作记录见下文，UI 实操来自 build `2026100302`，最终 build `2026100305` 另通过 W1 单测与打包服务 smoke。**

## 源码与安装包身份

| 项目 | 值 |
| --- | --- |
| 开始时 HEAD（本轮 W1） | `18e7435` |
| 安装包源码提交 | `b70669177a33a76c1ffe08539075728329fe62e6` |
| 本轮源码修复提交 | `b70669177a33a76c1ffe08539075728329fe62e6` |
| 交付版本 / build | `0.5.0 / 2026100305` |
| 架构 / 分发 | arm64 / `INTERNAL-DEV` ad-hoc |
| 前端 build identity | `v2026.10.03-4084a225` |
| 前端完整源码哈希 | `4084a225c0cea6fb6b4a9a5165c86110e933262432bf0c5282d0ac863ac31013` |
| App SHA-256 | `69ca8da98f32dfeac84caeec093fd9c5b40ace67606decffba497068fcc5a6e5` |
| DMG SHA-256 | `b929852a1bfed65a8d2d968576f601af500265da1ce3deeff337c218ae1f5a6d` |
| 飞书凭据包内完整性 | `build-manifest.json` 报告 `complete=true`；凭据值未写入仓库、报告或诊断 |
| 更新 feed | 空；本地内部包不启用自动更新 |

安装包：[/tmp/swb-phase1-final-release-20261003/0.5.0/arm64/SummitWorkbench-0.5.0-arm64-INTERNAL-DEV.dmg](/tmp/swb-phase1-final-release-20261003/0.5.0/arm64/SummitWorkbench-0.5.0-arm64-INTERNAL-DEV.dmg)（build `2026100305`）
产物目录：[/tmp/swb-phase1-final-release-20261003/0.5.0/arm64](/tmp/swb-phase1-final-release-20261003/0.5.0/arm64)（含 App、DMG、`SHA256SUMS`、`release-metadata.json`、`SBOM.json`、`test-manifest.json` 和 notary 摘要）。

前端身份由 build 日期和完整源码哈希确定，`release-metadata.json` 记录安装包源码提交。包内 `build-meta.json` 的 `git_revision` 为空；前端溯源以完整 `source_hash`（`4084a225c0cea6fb6b4a9a5165c86110e933262432bf0c5282d0ac863ac31013`）和 `frontend_build` 为准。安装包源码 commit、版本/build 与 App/DMG 散列均可在元数据复核。

## 工作包结果

| 工作包 | 结果 | 证据与实现 |
| --- | --- | --- |
| W0 冻结 | 通过 | [SWB-WORKBENCH-VNEXT.md](../product/SWB-WORKBENCH-VNEXT.md)、[SWB-WORKSPACE-CONTRACT-v1.md](../contracts/SWB-WORKSPACE-CONTRACT-v1.md)、[入口与副作用清单](SWB-WORKBENCH-ENTRY-INVENTORY.md)、共享模板和 `tests/fixtures/workspace-v1/` 样例/资格/批准向量。冻结三个入口、三个审批去处、逐版本批准及无工作库 Git。 |
| W1 初始化 | 通过 | 普通本地目录身份、兼容连接、损坏/不兼容拒绝；切库会排空活动 mutation 与会议 worker。build `2026100305` 的包级 smoke 在临时 HOME 与测试目录创建工作库，验证契约和 conventions 文件存在且无 `.git`。 |
| W2 写入与恢复 | 通过 | 原子本地文件写、工作区锁、操作回执和中断记录；回归断言覆盖已完成路径、不重放及中断后可检查。运行时没有自动 Git commit/push 调用点。 |
| W3 入口整理 | 通过 | capture、journal、会议导入/处理、收件箱提升、完整文档产物复用现有写入器；没有保存/列表/预览隐式模型调用的路径守卫。 |
| W4 审批与动作 | 通过 | 三个去处默认不选；批准证明绑定当前语义内容版本；Feishu task 经既有 outbox。自动测试只使用替身，没有创建真实飞书任务。 |
| W5 Git 退役 | 通过 | 工作台隐藏旧同步/冲突/撤销控制，停止打包后台 worker 和 launchd 安装；自动提交/推送出口无调用方。保留的旧同步模块为未注册的遗留源码。 |
| W6 选择性导入 | 通过 | 哈希绑定只读预览、显式选择写入、改源拒绝、保留原件、未知内容待整理、重复导入幂等及不继承旧批准的测试通过。 |
| W7 回归与打包 | 通过 | 本机 arm64 App 和 DMG 构建、ad-hoc 严格校验、包内凭据结构检查、动态端口服务 smoke、真实打包服务在隔离目录创建普通工作库的集成 smoke 均通过。 |
| W8 单机使用 | 通过 | 2026-10-02 完成快速捕获、工作思考、全文文档导入、项目页提升和知识沉淀提升的 UI 实操；2026-10-03 在新隔离库中通过 UI 导入合成会议、查看逐字稿来源、逐条批准决策与飞书任务候选、打开只读预演并点击“确认应用”。结果显示 2 项应用、0 拒绝、0 失败；飞书请求由 localhost 替身承接。未访问真实飞书。 |

## 检查结果

- 全量 Python（含 W1）：`./.venv/bin/python -m pytest -q` → **1373 passed, 1 skipped**；覆盖率 **82.08%**（门槛 80%）。跳过项是未设置包路径时的打包集成测试；发布脚本对 build `2026100305` 实际 App 执行该集成 smoke 并通过（1 passed）。
- 发布脚本质量门：ruff lint、ruff format、mypy（229 源文件）、`tests/unit`（1275 passed）、Web 路由契约（2 passed）、全部前端契约和打包集成 smoke（1 passed）。
- 前端：`npm --prefix web run test:frontend` 全部通过；`npm --prefix web run build` 成功，最终包的 build identity 与本报告所列一致。
- 凭据与包内容：`verify-macos-release.sh` 检查通过，包内完整标记为真，测试清单 13 项均为 passed。凭据来自本机已安装的可信内部包，临时 env 权限为 `0600`，构建结束删除；凭据没有传输到飞书。
- 包机：Mac `Mac16,12`，macOS `27.0.1`，arm64。本轮只对 localhost 和 `/tmp` 隔离目录发起打包服务 smoke；飞书凭据仅检查包内完整性，未登录飞书、未连 OneDrive、未连接旧 SK、未调用嵌入接口。
- 旧 `_vault`：未写入、未提交、未推送；实施提交当时未包含用户提供的四阶段计划。

> 后续现场补充：build `2026100305` 已安装并启动；用户完成 DeepSeek key 验证，在线健康检查无失败项，并人工确认 OneDrive 样板同步完成。详细记录见 [Phase 2 报告](SWB-WORKBENCH-PHASE2-REPORT.md)。本报告中“未连接 OneDrive／未安装覆盖”的描述是构建验收时的历史状态。

## W8 单机 UI 验收记录

- 主要输入、审批和最终确认 UI 实操由 build `2026100302` 完成，前端身份 `v2026.10.03-49bc6d84`；build `2026100305` 是其后的 W1 切库与契约改动包，另以隔离测试和最终包 smoke 验证。build `2026100302` 通过 UI 选择新建的 `/tmp/swb-phase1-ui-workspace-20261002`；该库由打包 App 创建，`workspace.json` 标记 reader/writer `0.5.0`，没有 `.git`。App 在 macOS 辅助功能权限获准后可完整读取和操作。
- “记点什么”：输入合成句子并点“记入”，界面显示“已记入收件箱”；刷新后条目出现在收件箱。未调用 AI 建议。
- 工作思考：使用“问题缘起／思考展开／当前结论”表单保存，界面显示文件名。收件箱的“知识沉淀”去处也按三段式保存成功。两篇思考页面都包含 `approval.version`、内容 SHA-256、`approved_at` 与 `operation_id`。
- “更新项目”：在隔离库通过 UI 新建 `phase1-acceptance` 测试项目，把捕获条目提升到“下一步”并移出收件箱；项目页有 `wb-candidate` 幂等标记，操作结果给出目标路径。
- “存入文档／产物”：通过 UI 将完整合成文本保存到该测试项目档案，界面显示“已存入…（保留全文）”。产物文件保留全文，并附 `approval.version: 1`、`content_sha256`、`approved_at` 和 `operation_id`。未勾选同步覆盖项目“当前状态”。
- “导入会议”：2026-10-03 在新隔离库 `/tmp/swb-phase1-w8-ui-confirm` 选择 `/tmp/swb-phase1-meeting-acceptance.txt`。本地模型替身只返回固定合成结构，生成会议笔记与 2 条候选；审批页显示决策与飞书任务候选。点击逐字稿来源后，UI 正确打开 `meetings/transcripts/2026-10-03-swb-phase1-meeting-acceptance-transcript` 并展示原文。此前查出来源链接只有 stem、被来源 allowlist 拒绝；修复为 vault 相对路径，并加入 `test_success_writes_note_usage_and_advances_pending_review` 回归断言。
- 候选审批与飞书任务：在审批 UI 分别批准两条候选；点击“检查并写回”后，预演显示决策写入 `/tmp/swb-phase1-w8-ui-confirm/projects/phase1-acceptance.md`、行动项目标为 `feishu-task`，状态为 `DRY-RUN（零写入）`。随后在 UI 点击“确认应用（写回项目/建任务/归档）”，结果页明确显示“已应用 2 条 · 已拒绝 0 条 · 失败 0 条”。隔离库中的决策页带 `wb-candidate`；`review/archive/20261003T002557298120Z.md` 保留审计。`/tmp/swb-phase1-w8-ui-calls.jsonl` 记录了本地模型请求、模拟用户身份 GET，以及发往 localhost 模拟器的 Task v2 POST；该 POST 包含全天 `start` 与 `due`，日期均为 `2026-10-06`，替身返回假任务 ID。整个测试服务只绑定 `127.0.0.1`，没有连接真实飞书。
- 日期修复：会议审批飞书任务缺少 `start_at` 时，现以 `due_date` 作为全天开始日；没有 `due_date` 时预演不可执行且不会调用外部创建器。outbox 请求指纹和审批审计均使用实际开始日期。新增 `test_feishu_task_defaults_missing_start_date_to_due_date` 与 `test_feishu_task_without_due_date_stays_out_of_external_writeback`，并将 outbox/并发用例样本补上有效日期。
- 最终“确认应用”已在浏览器 UI 实际点击，完成页显示 2 条应用、0 条拒绝、0 条失败；因此报告中的 W8 UI 确认缺口已补齐。
- 没有触发简报重新生成、AI 建议、会议结构化、全量嵌入、真实飞书登录或 OneDrive 连接。测试服务只绑定 `127.0.0.1`，退出按钮已关闭隔离 App；没有覆盖 `/Applications/SummitWorkbench.app`。测试库和逐字稿留在 `/tmp` 供人工复核。

## 阶段门与剩余事项

W0–W8 的隔离服务路径、UI 确认写回和飞书替身调用已通过；最终包 build `2026100305` 的源码与前端身份可复核，W1 单测及包级 smoke 通过。实际飞书账户动作、OneDrive 两机同步与旧库迁移属于后续人工环境验收，第一阶段没有触发。

交接提示：

## 可复制的后续交接提示

> 历史交接文字：下方提示生成于 Phase 1 尚未开始人工环境验收时。当前阶段与人工操作要求以 [Phase 2 报告](SWB-WORKBENCH-PHASE2-REPORT.md) 和 [四阶段实施计划](../implementation/ONEDRIVE-WORKBENCH-IMPLEMENTATION-PLAN.md) 为准。

> 第一阶段 W0–W8 已实现并完成本地隔离验收，接收包 `/tmp/swb-phase1-final-release-20261003/0.5.0/arm64/SummitWorkbench-0.5.0-arm64-INTERNAL-DEV.dmg`（build `2026100305`，源码 `b70669177a33a76c1ffe08539075728329fe62e6`，前端 `v2026.10.03-4084a225`）。测试报告在 `docs/acceptance/SWB-WORKBENCH-PHASE1-REPORT.md`。不要连接真实旧 `_vault`、旧 SK 或 OneDrive 生产库；不要触发全量嵌入；自动测试不得创建真实飞书任务。第二阶段只能在第一阶段阶段门通过后另行开始。
