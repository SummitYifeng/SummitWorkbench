# SWB 工作台第一阶段验收报告

日期：2026-10-02
范围：`ONEDRIVE-WORKBENCH-IMPLEMENTATION-PLAN.md` 第一阶段 W0–W8
判定：**W0–W7 通过；W8 自动化验收通过，人工单机使用验收未完成；第一阶段尚未通过阶段门。**

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
| W8 单机使用 | **未完成** | 已在当前 Mac 启动隔离配置的新版 App 进程，但 CUA 等待 macOS 辅助功能与屏幕录制权限，无法观察/操作界面。尚未逐项实操三入口和三去处，故不把自动测试记作用户可用性通过。 |

## 检查结果

- 全量 Python：`./.venv/bin/python -m pytest -q --cov=src/summit_workbench --cov-report=term --cov-fail-under=80` → **1366 passed, 1 skipped，覆盖率 82.11%**。跳过项是未设置包路径时的打包集成测试；同一测试已由发布脚本对实际 App 执行并通过。
- 发布脚本质量门：ruff lint、ruff format、mypy（228 源文件）、`tests/unit`（1266 passed）、Web 路由契约（2 passed）、全部前端契约和打包集成 smoke（1 passed）。
- 前端：`npm --prefix web run test:frontend` 全部通过；`npm --prefix web run build` 成功，产物身份与本报告所列一致。
- 凭据与包内容：`verify-macos-release.sh` 检查通过，包内完整标记为真，测试清单 13 项均为 passed。凭据来自本机已安装的可信内部包，临时 env 权限为 `0600`，构建结束删除；凭据没有传输到飞书。
- 包机：Mac `Mac16,12`，macOS `27.0.1`，arm64。本轮只对 localhost 和 `/tmp` 隔离目录发起打包服务 smoke；未登录飞书、未连 OneDrive、未连接旧 SK、未调用嵌入接口。
- 旧 `_vault`：未写入、未提交、未推送；用户提供的计划文件保持未跟踪，未纳入实现提交。

## 未通过项与阶段门

W8 人工验收仍需在隔离新工作库中实际操作并记录：

1. “记点什么”：快速输入、journal 手记/思考及待审过程。
2. “导入会议”：选择测试文本、显式处理、审阅并确认内容版本。
3. “存入文档／产物”：导入完整文本、预览、批准保存及重开文件。
4. 审批卡片分别验证“沉淀知识”“更新项目”“创建飞书任务”三个目标的选择/预览/提交状态；飞书动作使用人工确认的测试任务或替身，不把真实任务创建混入自动测试。
5. 检查常见操作不要求用户填写内部类型或理解 Git/remote 状态。

本次屏幕读取失败原因是 macOS Computer Use 所需的辅助功能和屏幕录制权限仍处于待授权状态。没有覆盖安装现有 `/Applications/SummitWorkbench.app`。完成上述实操前，第一阶段保持 **未验收**，不得开始第二阶段的 OneDrive 新库和样板建设。

## 可复制的后续交接提示

> 请继续 `docs/implementation/ONEDRIVE-WORKBENCH-IMPLEMENTATION-PLAN.md` 第一阶段 W8 单机验收，先在隔离测试目录使用 `dist/releases/0.5.0/arm64/SummitWorkbench.app`，按 `docs/acceptance/SWB-WORKBENCH-PHASE1-REPORT.md` 逐项实操三个输入入口和三个审批去处，记录 UI 结果与未通过项。不要连接真实旧 `_vault`、旧 SK 或 OneDrive 生产库；不要触发全量嵌入；自动测试不得创建真实飞书任务。W8 验收通过后再决定是否开始第二阶段。
