# 0.5.0 Studio → Air → Studio 验收指路

状态：**尚未开始。** Phase 2 样板验收已于 2026-10-04 由用户确认完成；此页只为之后的 Phase 3 列出适用边界和记录要求，不代表已经安装 Studio 验收包或开始双机操作。

当前 MacBook Air 上的参考包为 `0.5.0 / build 2026100401`，包内源码提交 `1141155`，前端身份 `v2026.10.04-b12c1720`。整理完成后应从最终选定的 0.5.0 源码构建一份验收包；**不能默认参考包就是最终目标包**。未经用户确认，不安装新包或开始本指路中的工作库操作。

## 适用边界

- 0.5.0 工作库由 `.summit-workbench/manifest.json` 标识。库身份跟随 `workspace_id`，不跟随本机绝对路径。
- Studio 和 Air 使用同一 OneDrive 工作库；OneDrive 客户端负责上传、下载。SWB 本地显示写入成功不表示云端已同步。
- 交接前由使用者在 OneDrive 客户端确认前一台 Mac 的变更已同步，再等另一台 Mac 下载完成后打开 SWB。
- SWB 不在工作库初始化 Git、自动 commit/push，也不提供工作库 Git 同步、冲突或撤销。**不要照搬 0.4.x 安装清单或双机 runbook 的 Git 步骤。**
- 旧真实 `_vault` 仅作来源和备份；本次 0.5.0 双机验收对象是已确认的 OneDrive 样板库，不接旧 SummitKnowledge，不触发全量嵌入。真实飞书任务不得作为测试样本。

## 开始前的阶段门

1. 用户确认本轮整理已完成，并明确开始 Phase 3。
2. 选定一个整理后的 0.5.0 验收包。记录安装包版本、build、源码 commit 和前端身份；Studio 与 Air 必须安装同一包。
3. 在两台设备上确认 OneDrive 客户端已登录、样板库完整下载且没有待同步项。切换设备前后都要重新确认。
4. 在两台机器上只读核对 `.summit-workbench/manifest.json` 中的 `workspace_id` 一致。路径可以不同；不要新建第二个工作库来代替连接已有样板。
5. 使用者确认本轮要执行的样板操作与内容。未确认前只做安装身份、连接路径、工作区 ID 与 OneDrive 状态核对。

## Studio → Air → Studio 往返

阶段启动后，按实施计划 Phase 3 的测试矩阵执行；每次换机都先退出当前 SWB，再由使用者确认 OneDrive 同步完成，随后等待另一台设备下载完成。

1. **Studio 起点**：记录 App 的版本、build、源码 commit、前端身份、工作区路径与 `workspace_id`，并记录 OneDrive 客户端无待同步项。只使用本轮明确选定的样板操作。
2. **Studio 交接**：退出 SWB，等待 OneDrive 显示同步完成。记下发生变化的内容和时间；不能仅凭本机回执写“云端已同步”。
3. **Air 接收**：等 OneDrive 完成下载，再打开同一验收包。确认版本身份、`workspace_id`、预期内容与操作回执；检查没有重复内容或重复外部动作。
4. **Air 回写**：只执行已确认的下一项样板操作。退出 SWB 并再次确认 OneDrive 同步完成。
5. **Studio 收尾**：等待下载完成后打开 App，确认相同 `workspace_id`、两端最终内容一致、批准证明仍与当前内容版本匹配，且已完成的飞书动作没有重复创建。

如果内容缺失、状态文件尚未到达、OneDrive 仍在同步、版本身份不同，或外部动作结果未知，应停止该条验收并记录状态；不要重复提交模型处理或飞书创建请求。

## 记录与通过判据

验收报告至少记录：日期、两台设备、同包身份（版本/build/source commit/frontend identity）、两端库路径和 `workspace_id`、OneDrive 同步确认、每一步操作与回执、内容/批准状态对照、外部动作是否发生、发现的问题及恢复方式。

只有完成 Studio → Air → Studio 完整往返，确认库身份一致、内容与回执延续、正式内容版本审批有效且没有重复外部动作，才可报告 Phase 3 通过。网络代理状态及模型、飞书服务的实际结果按实施计划逐项记录；源码检查或单机 smoke 不能代替双机实测。

## 相关文档

- [Phase 2 报告与 2026-10-04 后续确认](SWB-WORKBENCH-PHASE2-REPORT.md)
- [四阶段实施计划 §6](../implementation/ONEDRIVE-WORKBENCH-IMPLEMENTATION-PLAN.md)
- [工作库契约 v1](../contracts/SWB-WORKSPACE-CONTRACT-v1.md)
- [0.5.0 样板库快速说明](../product/ONEDRIVE-SAMPLE-QUICKSTART.md)
- [0.4.x 旧安装清单](FRESH-INSTALL-STUDIO-AIR.md) 和 [0.4.x 旧双机 runbook](DUAL-DEVICE-REHEARSAL.md)：仅供 legacy vault 历史参考
