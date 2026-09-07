# P2-02 build 26 · Studio + Air 一次性真实验收流程

状态：build 25 因 Dulwich 分叉详情读取缺陷退出；build 26 候选包与自动化质量门已完成，真实双机退出门待执行。  
范围：仅 P2-02。P2-03 不在本流程内，也不因本流程获得授权。

## 1. 候选包与证据

本次内部包从干净的 `main` 工作树构建；9 份既有文档更新提交前已核对 `main` 与
`origin/main` 同步，随后 build 25 包含该本地文档提交。为遵守“不 push”，构建后的 `main`
保留一个本地 ahead 提交；没有改写远端。包位于仓库内的相对产物目录，不把本机绝对路径写入
验收记录。

| 项目 | 值 |
|---|---|
| 产品 | `com.summitworkbench.panel` |
| 版本 / build | `0.4.3` / `26` |
| 架构 / 分发 | `arm64` / `INTERNAL-DEV` |
| 源码 revision | `58837495015e067c997c38e82482b28e11960933` |
| 前端 build identity | `v2026.09.07-5883749-d8336e88` |
| DMG | `dist/p202-build26/0.4.3/arm64/SummitWorkbench-0.4.3-arm64-INTERNAL-DEV.dmg` |
| DMG 大小 | `50,064,419` bytes |
| DMG SHA-256 | `3af3284696efdfc7c4752a424871128facd3d1bc8e3e9e2f5239b8af9f12bccb` |

接收设备必须安装这一个 build 26 DMG；不得重新构建、替换公开 release、创建 tag 或发布稳定版。
安装前在两台设备上各自核对 DMG 大小和 SHA-256。凭据只在系统 Keychain/PAT 提示处输入，
不得粘贴进终端参数、截图、诊断包、Git 或聊天。

build 25 的现场失败原因：Dulwich 共同祖先计算误传 object store，导致进入真实分叉详情时抛出内部错误；build 26 已修复并增加回归测试。

已自动通过的门：

- `825 passed, 1 skipped`；ruff、format、mypy、前端 build/verify-build、脚本语法和 secret scan；
- packaged App/worker 集成 smoke（1 passed），含 `--tls-diagnostic`；
- bundle CA 存在、`CERT_REQUIRED`、hostname 校验开启、Dulwich transport 正常；
- App/DMG strict codesign、动态端口 server smoke、build manifest、DMG checksum。

## 2. 一次性真实双机流程

以下 `STUDIO_VAULT`、`AIR_VAULT`、`TEST_WORKSPACE` 和 `REMOTE_ALIAS` 都是现场替换的本地
占位符。记录中只保留短 revision、计数、状态码和脱敏路径，不保留真实远端完整地址、真实
正文、Keychain 值或本机绝对路径。

### A. 安装与共同基线

1. 在 Studio 和 Air 都安装同一个 build 26 DMG，打开 App，连接同一个专用验收 vault 和
   同一个 HTTPS Git remote；两台设备使用同一个 `workspace_id`，设备 ID 必须不同。不要
   使用日常 vault 或真实会议正文。
2. 在两台设备的同步状态中确认：分支为 `main`、远端方案为 HTTPS、工作树 clean、ahead/behind
   为 `0/0`，Studio 是 `automation-primary`，Air 是 `secondary`。若需要 Keychain/PAT，
   由用户在系统提示处完成，验收记录只写“凭据可用”。
3. 保存共同基线的短 revision `BASE`。导出一次 `/api/sync/export` 或 UI“导出本机副本”，
   只检查它不含 token、Authorization、远端完整地址、本机绝对路径和正文；不上传导出物。

### B. 构造三类分叉

1. 在 Studio 断开同步写入（可暂时关闭网络或只不点击同步），通过工作台追加一条**合成的
   thread activity 事件**，再让工作台生成已登记的 `_views/thread-activity.json`。确认事件
   计数增加，但不要把事件 payload 或 Markdown 正文复制到报告。
2. 在 Air 保持离线，在同一个合成的 `P2-02-manual.md` 上写入与 Studio 不同的人工 Markdown；
   再创建一个合成的未知派生视图 `_views/p2-02-unknown.json`，以及一个合成的未知/二进制
   文件（例如 `p2-02-binary.bin`）。这些文件只使用固定测试标记，不使用真实正文。
3. 两边都用普通、显式路径的本地提交保存 fixture；不要 force-push、reset、rebase、stash，
   不要改任何 `feature/uiux-experience-refine` 分支。先不要让 Air push。
4. 恢复 Studio 网络，先在 Studio 点击一次普通同步/推送。然后在 Air 点击普通同步；预期
   Air 进入 `diverged-protected`，不会覆盖 Air 的人工 Markdown、未知视图或二进制文件。

### C. 解释、人工选择、临时预检

1. Air 打开“查看冲突详情”。确认页面只显示共同基线、本机/远端短 revision、相对路径、
   类型、动作和必要的事件元数据，不显示正文或 binary bytes：
   - event：`append-only-event` → `auto-collect`；
   - `_views/thread-activity.json`：`generated-view` → `rebuild`；
   - `P2-02-manual.md`：`manual-markdown` → 必须人工选择；
   - `_views/p2-02-unknown.json`：`unknown-generated-view` → 只能 `preserve-both`；
   - `p2-02-binary.bin`：`opaque-binary` → 只能 `preserve-both`。
2. 为人工 Markdown 选择 `keep-local`（如需覆盖分支可在一次独立 fixture 中选择
   `keep-remote`，但本次流程至少要实际完成一个人工选择）。未知视图和 binary 保持
   `preserve-both`；确认 UI 没有为它们提供 keep-local/keep-remote。
3. 点击“临时预检（不写入）”。预期事件自动收集和已登记视图重建通过，候选路径/计数可见；
   此时 Air 的 HEAD、工作树、远端 tracking ref 和原始文件内容都不变，临时目录随后清理。
4. 在预检完成后、显式确认前，由 Studio 添加一个新的合成文件并普通提交/推送。回到 Air
   点击“确认恢复并创建提交”时，预期返回 `conflict_snapshot_stale`，不得创建提交或写回，
   并回到保护态。重新打开详情、重新选择并重新预检后再继续。

### D. 脏工作树与正式恢复

1. 在重新预检前后任选一次，在 Air 创建一个未提交的合成 `P2-02-dirty.md`，再次点击确认。
   预期返回 `current_worktree_dirty`，不写回、不提交、不 push。移除这个合成文件并确认工作树
   回到 clean；不使用 stash 或 reset。
2. 重新读取详情并为全部人工路径完成选择，再执行一次临时预检。预检通过后才点击一次
   系统的明确确认对话框；没有确认就不得产生任何恢复写入。
3. 确认成功后检查：Air 产生一个普通双父提交（父节点数为 2），事件均保留，已登记视图由
   合并后投影重建，人工 Markdown 按选择落地，未知视图与 binary 的远端内容落在确定性的
   `.remote` 副本且本地内容仍在。审计记录只含 revision、计数、相对路径和选择，不含正文。
4. 检查恢复结果中的 audit 状态。若为 `failed`，UI 必须明确显示“提交已创建但脱敏审计未完成”，
   不能伪报成功或无限自动重试；保留提交和保护提示，停止本轮，不要擅自删除或改写审计数据。
   该分支可在专用验收副本中通过把审计目标预先做成安全拒绝的目录来验证；不得在日常 vault
   上注入该故障。自动化质量门已覆盖“提交成功、审计失败”的状态契约。

### E. 普通 push 与另一台设备 fast-forward

1. 在 Air 对恢复提交执行一次普通同步/push。只允许普通 push；若远端再次变化，预期 push
   被拒绝并继续处于保护态，不得 force-push。远端无变化时，预期 remote 与 Air ahead/behind
   都为 `0`。
2. 在 Studio 点击普通同步。预期 Studio 只做 fast-forward 到恢复后的同一 HEAD，不创建第二个
   冲突提交，不覆盖任一侧内容。
3. 在两台设备各自核对并记录：`HEAD` 短 revision 相同、工作树 clean、同步状态 ready、
   ahead/behind `0/0`；逐项确认 event、Markdown、本地未知视图、远端 `.remote` 副本、binary
   和审计 JSONL 均存在且内容未丢失。报告只记录存在性、SHA-256/计数和短 revision，不贴正文。

## 3. 退出判定与暂停点

只有以下条件全部满足，才把 P2-02 和 ADR 0043 改为 `[x]`：

- 同一个 build 25 DMG 在 Studio + Air 完成上述流程；
- 解释、人工选择、`preserve-both`、临时预检、显式确认、普通双父提交、脱敏审计和普通 push
  均有现场证据；
- 远端变化、脏工作树、审计失败保护分支均按预期拒绝或保持可见；
- 两台设备最终 fast-forward/汇合到同一个 HEAD，双方内容均可核对且未丢失；
- 现场记录和导出物通过 secret scan，且不含凭据、完整远端路径、真实正文或本机敏感路径。

执行至此需要用户在另一台设备操作、在 Keychain/PAT 提示处输入凭据，并可能确认测试
fixture 的本地清理。这是本工作包的暂停点；在用户回传脱敏结果前，不进入 P2-03，不修改
P2-02/ADR 0043 为完成，也不开始 M3。
