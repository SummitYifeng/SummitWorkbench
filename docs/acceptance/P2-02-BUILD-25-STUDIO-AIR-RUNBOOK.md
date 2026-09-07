# P2-02 build 29 · Studio + Air 一次性真实验收流程

状态：build 25/26 分别因分叉详情读取和选择校验缺陷退出；build 27 因远端单边副本重复路径边界退出；build 28 现场暴露 dual-write 主返回 Markdown 漏提交，build 29 已修复并重新打包；退出门仍需补齐事件/已登记视图和现场保护分支证据。
范围：仅 P2-02。P2-03 不在本流程内，也不因本流程获得授权。

## 1. 候选包与证据

本次内部包从干净的 `main` 工作树构建；9 份既有文档更新提交前已核对 `main` 与
`origin/main` 同步，随后 build 25 包含该本地文档提交。为遵守“不 push”，构建后的 `main`
保留一个本地 ahead 提交；没有改写远端。包位于仓库内的相对产物目录，不把本机绝对路径写入
验收记录。

| 项目 | 值 |
|---|---|
| 产品 | `com.summitworkbench.panel` |
| 版本 / build | `0.4.3` / `29` |
| 架构 / 分发 | `arm64` / `INTERNAL-DEV` |
| 源码 revision | `697c239` |
| 前端 build identity | `v2026.09.07-697c239-6b225c82` |
| DMG | `dist/releases-build29/0.4.3/arm64/SummitWorkbench-0.4.3-arm64-INTERNAL-DEV.dmg` |
| DMG 大小 | `50,066,803` bytes |
| DMG SHA-256 | `53bc3f4d32658e80d39347d6374e8e68f1d36c69c07817da150d4a012b368a8a` |

接收设备必须安装这一个 build 29 DMG；不得重新构建、替换公开 release、创建 tag 或发布稳定版。
安装前在两台设备上各自核对 DMG 大小和 SHA-256。凭据只在系统 Keychain/PAT 提示处输入，
不得粘贴进终端参数、截图、诊断包、Git 或聊天。

build 25 的现场失败原因：Dulwich 共同祖先计算误传 object store，导致进入真实分叉详情时抛出内部错误；build 26 已修复并增加回归测试。build 26 的现场失败原因：选择校验请求误带接口禁止的 `confirmed` 字段；build 27 已分离选择校验与恢复确认请求，并增加浏览器契约测试。build 27 的现场发现远端单边保留副本会在再次恢复时产生重复 `.remote` 路径；build 28 已改为原样接收远端单边副本，并增加回归测试。build 28 的现场追加 dual-write 又发现主返回 Markdown 漏提交；build 29 已在本地事务入口兜底并增加 Dulwich 回归测试。

已自动通过的门：

- build 28 生成时 `825 passed, 1 skipped`；2026-09-07 独立复核为 `826 passed, 1 skipped`；
  ruff、format、mypy、前端契约/build、脚本语法、依赖锁和 secret scan 均通过；
- packaged App/worker 集成 smoke（1 passed），含 `--tls-diagnostic`；
- bundle CA 存在、`CERT_REQUIRED`、hostname 校验开启、Dulwich transport 正常；
- App/DMG strict codesign、动态端口 server smoke、build manifest、DMG checksum。

## 2. 一次性真实双机流程

以下 `STUDIO_VAULT`、`AIR_VAULT`、`TEST_WORKSPACE` 和 `REMOTE_ALIAS` 都是现场替换的本地
占位符。记录中只保留短 revision、计数、状态码和脱敏路径，不保留真实远端完整地址、真实
正文、Keychain 值或本机绝对路径。

### A. 安装与共同基线

1. 在 Studio 和 Air 都安装同一个 build 29 DMG，打开 App，连接同一个专用验收 vault 和
   同一个 HTTPS Git remote；两台设备使用同一个 `workspace_id`，设备 ID 必须不同。不要
   使用日常 vault 或真实会议正文。
2. 在两台设备的同步状态中确认：分支为 `main`、远端方案为 HTTPS、工作树 clean、ahead/behind
   为 `0/0`，Studio 是 `automation-primary`，Air 是 `secondary`。若需要 Keychain/PAT，
   由用户在系统提示处完成，验收记录只写“凭据可用”。
3. 保存共同基线的短 revision `BASE`。导出一次 `/api/sync/export` 或 UI“导出本机副本”，
   只检查它不含 token、Authorization、远端完整地址、本机绝对路径和正文；不上传导出物。

### B. 构造三类分叉

1. 本轮已选择“复用 build 29、仅验收时显式启用”（选择 1A），不新增产品设置。完全退出 App
   后，用 macOS 一次性进程环境启动：

   ```sh
   open -n --env WB_THREAD_ACTIVITY_MODE=dual-write /Applications/SummitWorkbench.app
   ```

   该变量只属于这次 App 进程；验收结束后退出并从 Finder 正常打开，即恢复默认 `legacy`。
   不使用 `launchctl setenv` 等持久化方式。追加日志后必须先确认 `_events/**` 已产生，否则停止。
2. 在 Studio 断开同步写入（可暂时关闭网络或只不点击同步），通过工作台追加一条**合成的
   thread activity 事件**。随后在受控 fixture 提交中加入一个过期的
   `_views/thread-activity.json`；日常工作台不会主动写这个派生文件，恢复候选必须根据合并后的
   event 投影确定性重建它。确认 event 计数增加，但不要把 payload 或正文复制到报告。
3. 在 Air 保持离线，在同一个合成的 `P2-02-manual.md` 上写入与 Studio 不同的人工 Markdown；
   再创建一个合成的未知派生视图 `_views/p2-02-unknown.json`，以及一个合成的未知/二进制
   文件（例如 `p2-02-binary.bin`）。这些文件只使用固定测试标记，不使用真实正文。
4. 两边都用普通、显式路径的本地提交保存 fixture；不要 force-push、reset、rebase、stash，
   不要改任何 `feature/uiux-experience-refine` 分支。先不要让 Air push。
5. 恢复 Studio 网络，先在 Studio 点击一次普通同步/推送。然后在 Air 点击普通同步；预期
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

## 3. 2026-09-07 独立复核结果

已从 `main` / `origin/main` 的共同 HEAD `697c239` 复核源码与 build 29 产物。DMG 大小和
SHA-256 与上表一致，bundle identity 为 `0.4.3 (29)`，packaged App smoke、TLS diagnostic、
strict codesign、动态端口启动和 release 验证均通过。受控验收 vault 当前工作树 clean，
本机 HEAD 与 upstream 同为 `ac5df49`；历史中存在两个普通双父恢复提交 `d5f204a`、`babe7ae`，
对应脱敏审计提交均已保留，未知视图和 binary 的本地/`.remote` 副本均存在。

build 29 Studio 现场追加 dual-write 已验证：提交 `cd3d47b` 同时包含
`logs/2026-09-07-005.md` 与 `_events/.../01M1Y2MCP8TDG3XKHF8WXEE8GM.json`，工作树 clean，
本机 HEAD 与 `origin/main` 一致；event payload 仅含日期、来源路径和类型，不含正文或凭据。
Studio 的 build 29 acceptance preflight 全部 PASS（Dulwich、HTTPS、Keychain、双后端 dirty、
fetch、ahead/behind、schema、备份和 automation-primary）。

本次证据尚不足以关闭退出门：两条恢复审计的 `event_count`、`generated_view_count` 和
`rebuilt_view_count` 均为 `0`，现场树中也没有 `_events/**`，因此没有真实覆盖追加事件自动
收集与已登记 `_views/thread-activity.json` 重建。快照过期、脏工作树和审计写入失败有自动化
回归测试，但当前保留的现场记录不足以独立确认三条真机保护分支。P2-02 因此继续保持 `[~]`，
不得仅凭双父提交和最终同 HEAD 改为 `[x]`。

代码复核确认 build 29 的 migration mode 默认安全回退到 `legacy`，现有真机配置也没有持久化
`dual-write` 开关；产品所有者已选择 1A：仅验收时为 App 进程显式启用 `dual-write`，验收结束
恢复默认 `legacy`，不新增图形化设置。

使用 build 29，在合成验收 vault 中补做 event + 已登记视图
分叉，并保存三条保护分支的脱敏状态码/短 revision 证据；随后再次确认双方 clean、HEAD/远端一致。

## 4. 退出判定与暂停点

只有以下条件全部满足，才把 P2-02 和 ADR 0043 改为 `[x]`：

- 同一个 build 29 DMG 在 Studio + Air 完成上述流程；
- 解释、人工选择、`preserve-both`、临时预检、显式确认、普通双父提交、脱敏审计和普通 push
  均有现场证据；
- 远端变化、脏工作树、审计失败保护分支均按预期拒绝或保持可见；
- 两台设备最终 fast-forward/汇合到同一个 HEAD，双方内容均可核对且未丢失；
- 现场记录和导出物通过 secret scan，且不含凭据、完整远端路径、真实正文或本机敏感路径。

执行至此需要用户在另一台设备操作、在 Keychain/PAT 提示处输入凭据，并可能确认测试
fixture 的本地清理。这是本工作包的暂停点；在用户回传脱敏结果前，不进入 P2-03，不修改
P2-02/ADR 0043 为完成，也不开始 M3。
