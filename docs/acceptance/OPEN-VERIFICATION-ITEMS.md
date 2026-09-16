# 未验证清单（单一真源）

## 2026-09-16 当前源码候选说明

本轮可靠性候选位于分支 codex/reliability-luna，静态 bundle 的源码身份为 84db2d3，bundle 提交为 dfe6655。源码质量门已取得 1297 passed / 1 skipped、mypy 372 文件、前端完整契约测试、生产构建和三个 native 脚本的证据；唯一跳过项是未设置 WB_PACKAGED_APP 的打包 smoke test。当前 /Applications 中仍是历史安装包，因此以下真机/候选包项目不能由本轮源码测试代替。

> **这是唯一权威的「还没验证什么」清单。** 其他文档（README、验收记录、交接档案、ADR）只描述
> 各自范围内的结论并链接到这里，不再各自维护一份可能漂移的副本。
>
> 维护约定：本文件只记录**尚未取得证据**或**证据不足**的项；取得证据后把该项移入下方
> 「已关闭」并注明证据位置（提交、CI run、测试文件名）。不要在这里写计划或需求。
>
> **怎么验证**：需要真实浏览器执行构建产物的项，逐条可执行提示词见
> [`BROWSER-VERIFICATION-PROMPTS.md`](BROWSER-VERIFICATION-PROMPTS.md)——可直接交给具备
> computer use 能力的 agent 执行。**夹具怎么造、按什么顺序做、每批的通过标准**见
> [`UI-VERIFICATION-BATCHES.md`](UI-VERIFICATION-BATCHES.md)（批 0→7 **已全部跑完**），
> 尚未跑完的收尾项见 [`UI-VERIFICATION-FINAL-PROMPT.md`](UI-VERIFICATION-FINAL-PROMPT.md)。

- 最近更新：2026-09-16
- 当前源码候选基线：`0.4.9`，分支 `codex/reliability-luna`；静态 bundle
  `frontend_build = v2026.09.16-84db2d3-d7ba2132`，bundle 提交 `dfe6655`。
  `/Applications/SummitWorkbench.app` 仍是历史安装包，不因本轮源码测试自动更新。
  下面各轮条目里出现的 `v0.4.7` / build 21 之类是**各自当时**的事实，不回改。
- **当前开放项总账（2026-09-16）**——本文件各处「当前开放项」的措辞只对**各自那一轮**成立，
  容易被读成实时总数（此前就出现过「1 项（F1）」与 §J 里 D/E 两个 `⬜` 并存的矛盾）。
  实时清单以此条为准：
  1. **F1** Developer ID / 公证 / Intel / Windows —— 非缺陷，**明确不做**（见 §F、§H）。
  2. **§J-补验 D / E**：审批预演闭环、导入抽屉的**应用级真实浏览器**验收 —— **仍未验证**。
     ⚠️ 与 §C/§D/§E 组那些同名字母编号**不是一回事**，后者已在 §M/§N 关闭。
  3. **跨端口草稿 / 历史是否迁移** —— 属已写明的产品边界，但**从未实测**（§J「G 仍未回答的子问题」）。
  4. **D1 导入的「软预算 / 部分失败」路径** —— **仍未验证**（§D 注）。
  5. **旧 server 进程偶尔不被回收** —— **未定位机理、未修**（§U.5 第二条）。
     （§U.5 第一条「`/api/sources/read` 空值返回 500 而非 400」**已于 2026-09-14 修复**，见 §U.5。）
  6. **A6 / A7 的现场结论做在 build 28 上**，按「历史 build 验过 ≠ 当前代码验过」的口径属待复跑；
     A6 已量过差异（冲突恢复后端语义未变、11 条 `/api/sync/*` 契约逐字节相同），可缩减为抽查。
  7. **本轮可靠性候选尚未完成打包版/真机矩阵**：待用受控凭据构建候选 App，运行打包 smoke test，
     并实测断网/慢网、退出收尾、自动化失败恢复、会议同步不可用说明和双机远端新鲜度；本地源码质量门不能替代这些验证。
  本轮为**分发给同事**而做：把飞书 app_id / app_secret 作为默认值在构建时内置进包
  （`Contents/Resources/feishu-defaults.json`），并让配置与凭据按「显式配置/Keychain > 内置默认」
  回退，使同事装完点一下「授权飞书」即可，无需任何本机预置。**产品行为与数据格式未改动**；
  安全取舍与构建契约见 [`../RELEASING.md`](../RELEASING.md)「内置飞书凭据」，发布与双机验收证据见
  [`CHANGELOG.md`](../../CHANGELOG.md) 的 `[0.4.7]` 条目「发布」一节。
- **A6（真实双设备冲突恢复）**：**不是"从未验证"，而是"已在历史 build 上验证、待在当前 build 上复跑"**。
  两台机器（Studio + Air）上的冲突恢复**已经做过并留下完整证据**：
  - **build 29 / `0.4.3` / `697c239`（2026-09-07）**：P2-02 双机退出验收通过——详情解读、人工
    `keep-local` 选择、未知视图与 binary 强制 `preserve-both`、临时预检（不写入）、显式确认、
    普通双父提交 `c95b6c1` 与 `af662d5`、脱敏审计 `8a6a543` 与 `ec00260`、`conflict_snapshot_stale`
    与 `current_worktree_dirty` 保护分支、审计失败仍报 `committed`+`recovery_audit_failed`、
    普通 push、Studio 快进到同一 HEAD、双方 clean 且 ahead/behind `0/0`。
    全程见 [`../archive/acceptance/P2-02-BUILD-25-STUDIO-AIR-RUNBOOK.md`](../archive/acceptance/P2-02-BUILD-25-STUDIO-AIR-RUNBOOK.md)，
    结论见 `CHANGELOG.md` `[0.4.3]` 与 [ADR 0043](../decisions/0043-sync-conflict-explanation.md)（`[x]`）。
  - **build 23 / P1-07D**：同一 DMG 的双向同步、Air 离线写入恢复、双端离线分歧进入
    `diverged-protected`（不 force/reset/rebase/stash、不丢数据）；**build 24** 完成覆盖安装与增量冒烟。
  - **因此 A6 当前待办只是"把结论重新锚定到当前 build"**。实测差异（`697c239..HEAD`）：
    冲突恢复的**后端语义未变**——`sync_coordinator.py`、`repositories/git.py`、`git_backend.py`、
    `config/git_credentials.py` 一次都没改；`docs/contracts/web-route-contract.json` 里
    **11 条 `/api/sync/*` 全部逐字节相同**（该契约由 `inspect.getsource` 抽取路由与错误码），
    期间只新增了 9 条无关路由、无删除无变更；`routers/sync.py` 的 +455 行是 Step 6/16 的机械外迁。
    前端只有一处用户可见变化：`ee561f5` 给同步横幅加了**读取失败不静默隐藏**的保护态保留
    （保留「查看冲突详情」入口并显示「同步状态读取失败…（上方为上次成功读取的状态）」），
    其余 `features/sync/*` 都是 Step 1/6 的搬迁。⇒ 复跑可缩减为**差异点抽查**，
    见 [`DUAL-DEVICE-REHEARSAL.md`](DUAL-DEVICE-REHEARSAL.md) §A6。
- **A7（第二台机器的向导接入）本轮新增**：连接向导新增「从另一台 Mac 克隆」旅程（私有 HTTPS
  `remote/stage` → 暂存核对 → `remote/confirm` → 落盘为 secondary + workspace 级 Keychain 凭据）。
  后端 workflow 早已有测试，**HTTP 层此前无覆盖**，本轮补上；但真实两台机器的现场复跑仍待做。
- **ADR 0041 措辞更正**：该 ADR 写「Air『连接已有工作台』向导新增 PAT 输入与 `connect-remote`
  预检流」，与代码不符——历次提交中向导从未有过 PAT 输入（`connect-remote` 只作为 connect-existing
  位置步的预检 flow 存在，见 `f9060a0`）。PAT 输入是本轮才接上的，因此 A7 不是回归而是首次验证。
- **A6 与 A7 已于 2026-09-13 在 Studio + Air 上现场通过**（当前 build `2b534e0` / build 28），
  证据逐条见 §N；A 组至此全部关闭。
- **当时开放项：1 项（F1，非缺陷，明确超出 `INTERNAL-DEV` 交付范围）**（口径限于那一轮，
  实时总账见本文件开头 2026-09-14 一条），另有**本轮复跑发现的
  6 个产品缺陷（**全部已修**，见 §N 与提交 D1 `98fcd84` / D2 `95cc848` / D3 `b5d4a2b` / D4 `2b534e0` / D5 `d2b07bd` / D6 `9ce7205`）**：D1 新工作台不 `git init` / D2 转换后仍用启动快照导致同进程同步必失败 /
  D3 同步失败原因被吞成裸 error / D4 私有 clone 失败被兜底吞掉 / D5 向导草稿收尾不干净 /
  D6 干净工作区没有任何"主动拉取"入口。证据、复现与修法方向见
  [`DUAL-DEVICE-REHEARSAL.md`](DUAL-DEVICE-REHEARSAL.md) 文末「附」。
  **UI 层（B/C/D/E 组）开放项已于第七、八轮全部清零。**
- 判定口径：**「历史某个 build 上验证过」不等于「当前代码已验证」**，见 A 组；但"当前 build 的
  相关代码确实变了吗"要实测，不能只按时间推断——A6 就是先量差异再决定复跑范围。

## A. 真实外部服务回归

| # | 项 | 说明 |
|---|---|---|
| — | **A 组已全部关闭** | A1–A5 见 §L；**A6（双设备冲突恢复）与 A7（第二台机器的向导接入）于 2026-09-13 现场通过，见 §N** |

> **双机历史轮次（都已做过并有记录，供 A6/A7 复用）**
>
> | 轮次 | build / 源码 | 覆盖内容 | 证据位置 |
> |---|---|---|---|
> | P1-07D | build 23 / `0.4.3` | remote preview/apply、schema 迁移、preflight 全 PASS、Studio↔Air 双向同步、Air 离线写入恢复、双端离线分歧进入 `diverged-protected` | `CHANGELOG.md` `[0.4.3]`；[ADR 0041](../archive/decisions/0041-remote-normalization-acceptance.md) |
> | 覆盖安装冒烟 | build 24 / `0.4.3` | 两台设备覆盖安装与增量冒烟（HTTPS remote、preflight、基础同步、secondary profile、简报/周报友好跳过、零写入） | `CHANGELOG.md` `[0.4.3]` |
> | **P2-02（即 A6 本体）** | **build 29 / `697c239`** | **完整冲突恢复退出验收**：人工选择、`preserve-both`、临时预检、双父提交、脱敏审计、两类保护分支、审计失败分支、普通 push 与对端快进 | [P2-02 runbook](../archive/acceptance/P2-02-BUILD-25-STUDIO-AIR-RUNBOOK.md)；[ADR 0043](../decisions/0043-sync-conflict-explanation.md) |
> | 分发版单机 | build 21 / `v0.4.7` | 在**从未安装过**的 Mac 上：装包 → 飞书授权 → DeepSeek → 生成简报（使用者本人执行） | `CHANGELOG.md` `[0.4.7]` |

> **A1–A5 已于 2026-09-11 在真实凭据 / 真实飞书 / 真实远端上复验通过**，当时用真实 vault 与真实
> 模型（未用隔离副本，保护手段是 git 基线与事后回退）。逐项结果、证据与两个修复见 §L，并已登记到
> 下方「已关闭」。
>
> A6 的**代码路径**已由
> `tests/integration/test_acceptance_dual_device.py::test_dual_device_divergence_recovery_converges_with_two_parent_merge`
> 端到端自动化覆盖（双父提交、审计、推送、对端快进），并做过变异测试验证。仍缺的只是真实双设备现场复跑。
>
> **A3 描述更正**：原写的 `wb task` 命令**不存在**——`wb --help` 完整命令集为
> `ask brief diagnose doctor feishu meeting model project review status sync vault version web weekly worker`，
> PRD M4（`wb task` / `wb note`）未实施。该项此前从未被验证过，不是回归。

## B. 原生与无障碍矩阵

| # | 项 | 说明 |
|---|---|---|
| — | **B 组已全部关闭** | B1 / B2 / B3 / B4 均已取得证据，见下方「已关闭」 |

> B1（Chrome 原生 200% 缩放）、B2（浅色主题）、B3（`prefers-reduced-motion`）已于 2026-09-11 由
> 提示词 F 的实测关闭——见下方「已关闭」。验收在候选产物上进行，其 **`source_hash` 与合并后
> main 的产物完全相同（`6e6e0c91…`）**，仅 `git_revision` 不同，故结论直接适用。
> **B4（packaged App / WKWebView 黑盒）已于 2026-09-11 第七轮关闭**——在**临时环境**里跑通了
> 原生 App：设置页显示临时工作区、六页签可达、重启后正常、真实 `runtime.json` 无残留。
> 详见 §M 第七轮。

## C. 审批边界

| # | 项 | 说明 |
|---|---|---|
| — | **C 组已全部关闭** | C1–C4 均已取得证据，见下方「已关闭」 |

> **C1 已于第二轮关闭**（`0/2` vs `1/12` 请求计数）；**C2 已于第二轮关闭**；
> **C4（「新建会议（个人日程）」落点）已于 2026-09-12 第八轮关闭**——在隔离 vault 上跑通
> 真实飞书日历端到端：资格可批准 → 预演零写入 → 写回恰好创建一个事件 → 回读字段一致 →
> 删除后 `status=cancelled`。详见 §M 第八轮。
>
> **C3（部分失败可见）已取得真实证据（2026-09-11，见 §K）**：3 条候选分属 `project-main` /
> `feishu-task` / `feishu-meeting`，其中日历创建当时因 CLI 缺 creator 而失败，结果被如实报成
> `批准写回=2 失败=1`，失败原因写进候选的 `error:`，**没有被包装成整体成功**。

## D. 导入与来源

| # | 项 | 说明 |
|---|---|---|
| D2 | 来源面板异常矩阵（浏览器层） | ✅ **已于 2026-09-11 第四轮关闭** —— 见下方「已关闭」 |
| D3 | 正文截断提示的真实显示 | **已于 2026-09-11 关闭** —— 见下方「已关闭」 |

> **D1 已部分验证（2026-09-11，见 §K）**：成功导入（含项目解析）与**幂等重跑**
> （`待导入 0 场，已跳过 3 场，约 0.0 CNY`，零模型调用）均已取得证据。
> **软预算与部分失败的导入路径仍未验证**；10 MiB 上限原只做在 web/App 层，**已于 2026-09-11
> 下沉到 workflow 层修复（`7e25cd3`）**，见 §K。

## E. 交互细节

| # | 项 | 说明 |
|---|---|---|
| — | **E 组已全部关闭** | E1–E5 均已取得证据，见下方「已关闭」 |

> **E1 / E2 已于 2026-09-11 关闭**；**E3 第三轮关闭**；**E4 已取得实测结果**（跨端口草稿丢失，
> 与「不承诺迁移」的既定边界一致，非缺陷）；**E5（R01–R14 交互断言）已于第七轮全部关闭**——
> 最后一项 R09 拿到了完整的乱序证据。
>
> E5 从第一轮"源码级契约测试不算真实浏览器证据"一路走到全部关闭，**十二轮里没有一项卡在产品
> 逻辑上**：卡点全部是验证基础设施（脚本没自检、时序太短、判据选错一层、环境隔离没做对）。
> 详见 §M 各轮记录。

## F. 发布链路

| # | 项 | 说明 |
|---|---|---|
| F1 | Developer ID / 公证 / Intel / Windows | **明确超出 `INTERNAL-DEV` 交付范围**，非缺陷 |

> tag 触发的 `release.yml` 实跑已于 2026-09-11 关闭，见下方「已关闭」。

## G. 测试覆盖洼地（代码有、测试未走到）

总体覆盖率 82.33%（`v0.4.6` 实测；此前记录的 82.36% 为 build 12 期间的值，测试集变化导致
微小差异，两次均高于 80% 门槛）。以下是仍然偏低的模块；多为薄封装或需要真实外部服务，风险等级不同。

| 模块 | 覆盖率 | 备注 |
|---|---|---|
| `cli/ask.py` | 21% | 主要是真实模型链路 |
| `cli/web.py` | 24% | 拉起服务，需进程级测试 |
| `cli/model.py` | 30% | 需真实模型 |
| `cli/vault.py` | 33% | |
| `config/tls_trust.py` | 33% | TLS/CA 分支 |
| `webapp/routers/settings.py` | 42% | 设置页大量 API 分支 |
| `workflows/threadnotes.py` | 44% | |
| `cli/meeting.py` | 46% | 已由 16% 提升；余下需飞书/模型 |
| `cli/feishu.py` | 48% | 已由 20% 提升；余下需真实 API |
| `webapp/server_entry.py` / `worker_entry.py` | 0% | 由 CI packaged smoke 覆盖，非单测 |

## H. 明确不做（非缺陷，不要计入缺口）

- M3（带上下文启动与会话收尾）、P2-03（组织级云服务）——按 ADR 0044 与产品边界不实施
- 向量数据库 / Embedding / RAG
- 跨动态端口的历史与草稿迁移（需独立持久化设计）
- Intel / Windows / 公网 notarized 发行

## I. 依赖安全评估（dulwich 0.22.8）——已评估，决定暂不升级

**结论：两条开放 advisory 在支持平台与实际用法上均不可达；升级代价经实测为一次真实迁移，
因此暂不升级，转入计划内技术债。** 本节保留完整证据链，便于将来复核。

### 开放告警（Dependabot，4 条 = 2 条 advisory × 2 个清单）

| Advisory | 严重度 | 受影响范围 | 攻击面 | 本项目可达 |
|---|---|---|---|---|
| [GHSA-897w-fcg9-f6xj](https://github.com/advisories/GHSA-897w-fcg9-f6xj) | **HIGH** | ≥0.10.0, <1.2.5 | 恶意仓库 clone/checkout 时经 `\` 路径写文件 → RCE | 否：**Windows 专属**（反斜杠语义）；产品为 macOS-only arm64 |
| [GHSA-xrvj-v92f-53gj](https://github.com/advisories/GHSA-xrvj-v92f-53gj) | MEDIUM | ≥0.1.0, <1.2.5 | `receive-pack` 瘦包内存放大 DoS | 否：需 dulwich **服务端**接收 push；本项目纯客户端 |

另有 3 条 CVE（CVE-2026-52726 / 42563 / 47712）的受影响范围分别**从 0.23.2 / 0.24.0 才开始**，
0.22.8 不在范围内（见 [Debian 追踪表](https://security-tracker.debian.org/tracker/source-package/dulwich)）。

代码面核验（全 `src/` grep）：无 `ReceivePackHandler` / `dulwich.server`、无 submodule、
无 `format_patch`、无 merge driver 与 `shell=True`、`dulwich_git.py` 无 SSH。

### 升级代价：实测为一次真实迁移（不是改一行）

在 1.2.14 上实测：

- **16 个运行时测试失败**：双机验收、冲突恢复端到端、git 后端一致性、sync 加固、thread activity 迁移等。
- 根因：**`Repo.do_commit` 在 1.x 被移除**（`dulwich_git.py:211` → `AttributeError`）。
- 另有 **29 个 mypy strict 错误**——1.x 开始自带类型标注，旧的 `type: ignore` 全部过时，
  并暴露出 `Ref` 已成为独立类型、`Tree.add` 要求 `ObjectID` 等更严格的契约。

`dulwich_git.py` 是**写用户 vault 的 git 后端**，因此这次迁移必须在有充分验证的前提下专门做，
不能作为顺带升级。

### 决定与复发防护

- 维持 `dulwich>=0.22,<0.23`。上界同时挡住了上述 3 条 RCE 的受影响范围。
- **4 条告警已 dismiss**（HIGH → `tolerable_risk`，MEDIUM → `not_used`），注释指向本节。
  新出现的 advisory 仍会照常告警。
- **刻意不加 `dependabot.yml` 的 `ignore` 规则来消除 dulwich 升级 PR**：
  官方选项参考把 `ignore` 同时标记了 security-updates 图标（"All options marked with the
  security icon also change how Dependabot creates pull requests for security updates"），
  因此 ignore 会**连安全更新一起抑制**。曾短暂加过 `ignore: semver-major`，除了这个风险之外，
  它还把 Dependabot 从修复版本压到 0.25.2，产生一个**修不了漏洞的 PR**；已撤销。
- 接受 N 代价：Dependabot 会周期性重开 dulwich 升级 PR（每次重开触发一轮 CI）。代价有界
  （约每次 dulwich 发版一轮），远低于失去安全更新通道的代价。
- 本节的审计教训有两条：**不要只依赖单一来源做安全审计**（手工审计漏掉了上面那条 HIGH）；
  **不要把"告警数为 0"当作"扫描完成"**（曾如此误读）。

### 将来升级时的清单

1. 替换 `Repo.do_commit`（1.x 新 API）并处理其余 API 差异。
2. 清理/重写 29 处受影响的 `type: ignore` 与类型标注。
3. 通过：全量 `pytest`、冲突恢复端到端、双机验收、packaged smoke。

## J. 前端依赖 major 升级（已合并；仅剩 D/E 应用级补验）

**已合并进 main**：`6ff10a6`（工具链）+ `2722aa9`（静态产物重建），产物身份
`v2026.09.11-6ff10a6-6e6e0c91`。变更：`vite 6.4.3 → 8.3.0`（Rolldown）、
`typescript 5.9.3 → 7.0.2`、`esbuild 0.25.12 → 0.28.2`。合并后 CI 全绿（879 passed）。
对应的 Dependabot PR #3 / #4 已随之关闭，候选分支 `verify/npm-majors` 已删除。

合并前的真实浏览器验收（隔离临时 HOME/WORK_ROOT，模型与飞书跳过）：

| 场景 | 结论 | 证据摘要 |
|---|---|---|
| A 启动冒烟 | ✅ 通过 | 品牌区 + 六页签 + 主内容渲染；`index.html`/JS/CSS 均 200；Console 日志为空 |
| B 页签与交互 | ✅ 通过 | 六页签可切换并渲染；审批筛选/新会话/项目搜索/指南搜索/设置高级区均可交互；`End→设置`、`ArrowRight→今日`、`Home→今日`；无整页横向溢出 |
| C 弹层焦点与草稿 | ✅ 通过 | **机器测量：main 与候选分支各 3 次——打开前焦点在外部「✎日志」，打开后 3/3 进入弹层内 `INPUT`，`modalContains=true`**；人工仅用键盘确认 Tab 顺序为「文本框 → 保存日志 → 取消 → 关闭 → 回到触发按钮」。两通道一致，**既非既有缺陷也非升级回归** |
| D 审批预演闭环 | ⬜ 未验证 | 属应用级流程，与本次升级无因果关系；手工步骤见下方 §J-补验 |
| E 导入抽屉 | ⬜ 未验证 | 同上 |
| F 响应式/缩放/主题 | ✅ 通过 | `320:305`、`390:375`、`768:753`、`960:945`、`1280:1265`（bodyScrollWidth/innerWidth），五档无整页溢出；200% 原生缩放、浅色主题、`prefers-reduced-motion` 均确认正常 |
| G 资源完整性与动态端口 | ✅ 通过 | 构建资源全 200；`8898→8897` 端口切换后应用可启动、API 均 200、构建版本正确、线程与日志历史可见 |

**C 那次冲突为何值得记下来（方法论）**：根因是把两个不同指标混为一谈——机器读
`document.activeElement`（焦点**归属**），人眼找焦点环（**视觉反馈**），而浏览器对程序化 focus
默认不渲染焦点环（`:focus-visible` 只对键盘交互生效）。修正后的方法是：机器通道先做**检测器自检**
（打开前后各读一次，确认能区分两个状态）再测 3 次；人工通道只用键盘，并分别回答「焦点环画在哪个
元素」与「Tab 能到哪些元素」。这条方法已固化进提示词 C。

**G 的口径修正（由本次验收发现，已修正提示词）**：原标准写「确认没有任何 404」，在纯静态环境下
不可能成立——SPA 必然探测 `/api/*`，浏览器必然请求 `favicon.ico`。现标准为「**构建资源**零 404」，
静态环境的 API 与辅助请求 404 需单独列出但不计失败。**这是验收提示词自身的缺陷，不是测试操作问题。**

**G 仍未回答的子问题**：端口切换时未刻意留下未保存草稿，因此「跨端口草稿/历史是否迁移」
**仍未验证**（`localStorage`/`sessionStorage` 在两端口下均为空）。指南已写明「动态 loopback 端口
变化不承诺迁移」，故属已知边界，但从未实测。

### §J-补验：剩下的 D / E（应用级，与打包器无关）

1. **D 审批闭环**：先在真实工作区只做「检查并写回」的零写入预演（不点确认）；再挑一条
   **本地落点**（项目主笔记 / 跟进事项 / 项目 inbox / 全局 inbox）的候选走完整写回，验证结果
   区分 applied/rejected/failed、落盘到项目线视图、顶栏「↩ 撤销」可还原、重跑幂等。
   **避开落点为「飞书任务 / 新建会议」的候选**——那会真写飞书且不可撤销。
2. **E 导入抽屉**：备 `.txt`（正常）、`.csv`（类型不支持）、空文件、>10 MiB 文件；验证每个文件
   独立回执、失败原因明确、关闭重开与切页签均保留、焦点归还、重复导入幂等。
   已配模型的工作区会真的调用模型计费，失败路径建议在未配模型的工作区验证。

**附带发现（已修复并合入 main `f8b40c7`）**：`web/scripts/` 下 6 个测试脚本直接
`import { build } from 'esbuild'`，但 `web/package.json` **从未声明 esbuild**——一直靠 Vite 提升的
幽灵依赖。Vite 8 改用 Rolldown 后 esbuild 被移除，这 6 个脚本全部 `ERR_MODULE_NOT_FOUND`。
已显式声明 `esbuild`，并新增契约测试
`test_frontend_scripts_only_import_declared_packages` 防止复发。

**版本耦合（升级时必须一起做）**：Vite 8 声明 `peerOptional esbuild ^0.27 || ^0.28`，因此
**esbuild 版本必须随 Vite 大版本同步抬升**；只改 Vite 会被 npm ERESOLVE 拒绝。

**尚未重建的交付物（本节为 §J 升级当时的状态）**：当时只更新了仓库内的前端产物；已安装的 build 9
App 与历史 DMG 仍带旧前端。**该状态已于 v0.4.5 消除**：build 19 的 DMG 已重新打包、发布并装机，
装机器件（`/Applications/SummitWorkbench.app`）现在带的是新前端
（`v2026.09.12-749eeef-0bc00d2c`）。历史 build 9 的产物身份不变。

## K. D/E 真实写回验收（2026-09-11）

环境：build 11（`v2026.09.11-1abcebe-6e6e0c91`）已装机并运行；真实 vault；**真实模型与真实飞书**
（产品所有者已明确授权，含不可撤销的飞书任务/日程写回）。测试前 vault HEAD `8dba623d`，工作树干净。

### 取得证据的环节

| 环节 | 结果 |
|---|---|
| 导入 3 个有效文件 | ✅ 处理 3、生成候选 3；项目解析正确（2 条落 `demo-project`） |
| 导入**幂等重跑** | ✅ `待导入 0 场（已存在跳过 3 场）`，`约 0.0 CNY`，**零模型调用** |
| 审批**零写入预演** | ✅ `DRY-RUN（零写入）`、`批准写回=0`、逐条列出落点、vault 无改动 |
| 写回 `project-main` | ✅ 写入 `projects/demo-project.md`「决策记录」，带 `<!-- wb-candidate: … -->` 溯源注释 |
| 写回 `feishu-task` | ✅ outbox `succeeded`、`remote_id 60509fe…`；⚠ 该任务**不出现在用户任务列表**（见下） |
| 写回 `feishu-meeting` | ❌→✅ 首次因 CLI 缺陷失败；修复后 `succeeded`、`external_id f9b1bf86…`，`wb feishu calendar --date 2026-09-18` **回读可见**（15:00 CST） |
| **部分失败可见性** | ✅ 报为 `批准写回=2 失败=1`，失败原因写进候选 `error:`，未被包装成整体成功 |

### 本轮发现的两个缺陷

1. **CLI 未注入 meeting creator（已修复 `8f822e1`）**：`wb review apply` 只传 `task_creator`，
   而面板传 `task_creator` + `meeting_creator`，导致 `feishu-meeting` 落点在 CLI 下必然失败
   （`缺少飞书日历会议创建器`），同一份审批页只能在面板应用。已补齐并加回归测试
   （`test_review_apply_injects_both_task_and_meeting_creators`，经 TDD 验证）。

2. **10 MiB 上限只在 web/App 层（已修复 `7e25cd3`）**：`legacy_app.py` 有 `max_upload_bytes`，
   而 CLI 的 `scan_for_import` / `scan_local_transcripts` 只判断「非空」。本次一个 12 MiB 文件
   因此被真实送进模型，预估 **419 万 input token（约 4.24 CNY）**。

   修复：`MAX_TRANSCRIPT_BYTES` 上移到 workflow 层作为单一真源，两个扫描函数都执行该上限，
   web 上传路径改为复用同一常量（数值不会再分裂）；新增 `oversized_transcripts()` 让 CLI
   **显式列出被跳过的文件**，而不是静默丢弃。

   真实验证（同一目录含 1 个 12 MiB + 1 个正常文件）：

   | | 预估 input token | 预估费用 |
   |---|---|---|
   | 修复前 | 4,194,541 | ~4.24 CNY |
   | 修复后 | **12** | ~0.016 CNY |

   CLI 输出：`⚠ 已跳过 1 个超过 10 MiB 的逐字稿（未送模型）：2026-09-11-超大.txt（12.0 MiB）`。
   边界为「超过才拦」：等于上限的文件仍放行，有测试锁定。

### 由人工飞书复核确认并已修复的问题

**审批创建的任务没有负责人 → 进不了自己的工作台清单（已修复 `7b20002`）**

人工复核发现：任务在飞书「全部任务」里可见，但**没有负责人**。根因与影响：

- 飞书只把调用者记为 `creator`，**不会**据此设为 `assignee`；`assignee` 必须通过请求体的
  `members[{id, type, role:"assignee"}]` 显式设置
  （[官方文档](https://open.feishu.cn/document/task-v2/task/create?lang=zh-CN)：members 是
  「任务的负责人和关注人」，`role` 必填，取 `assignee` 或 `follower`）。
- 而今日简报的任务清单来自 `list_tasks(completed=False)`，即**当前用户的任务**。
  两者叠加 → **审批批准 → 建了飞书任务 → 它永远不出现在用户自己的简报里**，闭环在最后一步断掉。

修复：`create_task` 增加 `assignee_open_id`；CLI 与面板两处调用点都用 `user_info` 解析当前授权
用户并传入；加契约测试锁住请求体形状（有身份→带 members，无身份→不带，不做伪造指派）。

真实验证（前后对照，均对真实飞书）：

| | 「我的任务」条数 |
|---|---|
| 创建前 | 3 |
| 带 assignee 创建后 | **4**，新任务 `82060d6b…` 出现且标题/截止正确 |
| 对照组：修复前建的 `605009fe…` | **仍不在列表** |

> 两条测试任务（修复前的 `605009fe…` 与修复后的 `82060d6b…`）已于 2026-09-11 从飞书删除，
> 用户任务列表回到原来的 3 条。**飞书日历上 2026-09-18 的测试日程未删除**（不在当时授权范围）。

### 本轮未覆盖

- **App 抽屉 UI 层**：多文件回执、关闭重开保留、焦点归还（本轮走 CLI，未驱动界面）
- 落点 `project-followup` / `project-inbox` 未实测（`global-inbox` 未单独实测）
- 导入的**部分失败 / 软预算**路径
- C1（`0/1/100/101` 矩阵）、C2（一次点击一次请求网络计数）
- ~~合成数据尚未清理~~ → **已于 2026-09-11 清理完毕**：vault 回退到 `8dba623d`，工作树与未跟踪
  文件均为 0，`_swb-import-test/` 素材目录已删除。
- 注意：清理只作用于本地 vault；**飞书上已建的任务与日程不会随之消失**

## L. A 组真实外部服务复验（2026-09-11）

环境：本机真实凭据（5 个模型能力均配 `deepseek-v4-flash`、飞书授权有效）、真实 vault、
真实飞书。测试前 vault HEAD `8dba623d`，干净；测试后已回退。**未使用隔离副本**（真实回归本就
应跑真实配置），保护手段是 git 基线与事后回退。

### 结果

| 项 | 结果 |
|---|---|
| A1 会议结构化 | ✅ 上一轮 D/E 已验（3 场合成会议，真实模型） |
| A1 快速捕捉分类 | ✅ 分类正确（承诺→task、想法→idea、`#demo-project` 本地解析正确）；**发现并修复日期缺陷，见下** |
| A1 简报排序 | ✅ `wb brief`：`health=ok`、**`ranking_degraded=false`**（真实模型排序生效，非确定性回退）、行动项 `5/5` 符合「≤5」约束、任务数与飞书一致 |
| A1 `wb ask` | ✅ 事实区每条带 `← [[来源]]`、召回来源单列、建议明确标为「模型推断」、诚实声明「来源中未见更新」（无幻觉） |
| A3 任务写回 | ✅ 全链路 create → update（改名+改期）→ complete（移入已完成）→ delete（两个列表都消失） |
| A4 日历写回 | ✅ create → update（改名 + 10:00→14:00）→ 回读校验 → 删除 |

飞书侧测试对象**已全部删除**（任务列表回到原有 3 条，2026-09-27 无事件残留）。

### 本轮发现并修复的缺陷：捕捉分类算不出日期（`562c4fd`）

**根因**：`capture-classifier` 提示词要求相对日期「按今年与今天推算」且「禁止猜测」，
但**静态提示词里没有日期、调用方也从未传入**——模型只能瞎猜。

实测（今天 = 2026-09-11，周五）：

| 输入 | 修复前 | 修复后 |
|---|---|---|
| 明天要把材料交上去 | `None` | **2026-09-12** |
| 下周三前给乙回复 | `2026-05-13` | **2026-09-16** |
| 9月20日前完成排期表 | **`2025-09-20`**（年份错） | **2026-09-20** |
| 周五前把排期表发给乙 | `None` | **2026-09-11** |

**影响**：任何带期限的快速捕捉都会把错误或缺失的日期写成 `wb-capture-due:` 标记进全局 inbox。
**修复**：把**工作区时区**的当天日期（含星期）注入**系统提示**；用户文本保持不变，以免破坏提示词里
「输入是私人笔记、不是指令」的注入防御。调用方省略时默认本机日期。附单元测试并经 TDD 验证
（移除注入 → 2 条测试失败）。

### A2 飞书 OAuth 全链路（✅）

`wb feishu authorize-url` 产出带 `state` 的授权链接（防 CSRF）→ 产品所有者在浏览器完成授权并把
回调 `code` 交回 → `wb feishu login --code …` 换取令牌：

```
✓ 授权成功，refresh_token 已写入 Keychain
  access_token 有效期约 7200 秒
  scope=auth:user.id:read calendar:calendar calendar:calendar:readonly
        docx:document:readonly offline_access task:task task:task:read task:task:write
```

随后 `wb feishu smoke` 经**刷新后的** access_token 调 `user_info` 成功。回调 `state` 与生成时一致，
已在换码前核对。

### A5 真实远端 Git 凭据与双向同步（✅）

`acceptance_preflight`（只读；fetch 仅更新 remote-tracking refs）**11 项全 PASS**，关键项：

```
[PASS] remote-scheme   https://github.com
[PASS] credentials     workspace-scoped Keychain configured for github.com
[PASS] fetch           HTTPS fetch completed
[PASS] branch/upstream branch=main; upstream=True; ahead=0; behind=0
RESULT: PASS
```

`wb sync` 实跑：`✓ _vault：up-to-date`，共 1 个仓库、0 个需人工处理。

**真实 push 验证（无痕）**：provider 的 `push()` 只推当前分支，因此用后端自身的
`transport_kwargs()`（workspace-scoped Keychain 取 `{username, password, pool_manager}`）把
`refs/heads/main` 推到远端**临时分支** `wb-acceptance-probe`：

```
Push to https://github.com/yifeng93/YifengWorkKnowledge.git successful.
Ref refs/heads/wb-acceptance-probe updated
```

核对：探针分支到达 `8dba623`、远端 `main` 全程仍是 `8dba623`；随后删除探针分支并确认远端只剩
`main`，**未对知识库 `main` 造成任何改动**。

### 仍待人工

- A3/A4 的**面板点击路径**（一键完成、行内编辑、会议行内编辑）由产品所有者复核；本轮已验证其
  底层 PATCH/创建在真实飞书上正确工作。

## M. UI 分批真实验收（2026-09-11）

按 [`UI-VERIFICATION-BATCHES.md`](UI-VERIFICATION-BATCHES.md) 的批次 0→7 执行了一轮
（`frontend_build=v2026.09.11-6ff10a6-6e6e0c91`，全程临时 workspace，未连真实模型/飞书）。

### 关闭 10 项

| 项 | 实测证据 |
|---|---|
| C2 一次点击一次请求 | 单击 `/api/review/apply` 计数 = 1（`200 OK`）；快速双击时按钮在途 `disabled`，最终计数仍 = 1（`2.04 s`） |
| R08 一键拒绝过期项范围 | 0 条时按钮原生 `disabled`，title 明确「不受当前筛选影响……（当前 0 条）」 |
| D3 正文截断提示 | `big.md` 显示「正文已截断」，`pre.source-reader.textContent.length === 100000` |
| E1 冲突包导出下载 | Chrome 原生下载记录 `summitworkbench-sync-recovery.zip · 979 B · 完成` |
| E2 确认框关闭后焦点 | 原生确认框「当前弹层里有未保存内容……」→ 取消后焦点回到冲突选择框 |
| R06 同步横幅读取失败 | 停服后刷新：保留 `diverged-protected` 与上次同步信息 + 「同步状态读取失败：TypeError: Failed to fetch（上方为上次成功读取的状态）」 |
| E4 跨端口同源边界 | **已取得实测结果**：端口 A 的未保存草稿在端口 B 丢失（`0/10` 会话、输入框空）。与指南「动态 loopback 端口变化不承诺迁移」一致，**记为既定边界而非缺陷** |
| R03 撤销弹层语义与焦点 | `role=dialog` + `aria-modal` + 关闭按钮；关闭后 `document.activeElement.id === "btn-undo"` |
| R10 长文本本地拦截 | 100001 字符 → 「内容超过 10 万字上限（当前 100001 字），请拆分后重试」，未发请求 |
| R11 重复提交 | `/api/threads/logs` 计数 = 1（`200 OK`，`2.02 s`），保存按钮在途 `disabled` |

### 本轮发现并修复的缺陷：非 UTF-8 来源导致 500（无信息兜底）

- **现象**：打开一个非 UTF-8 的 `.md` 来源，界面显示 `ApiError: 服务内部错误，请稍后重试 [internal_error]`。
- **关键区分**：那串文案**不是服务端写的**，而是前端 `normalizeApiError` **解析响应失败后的兜底**；
  真正发生的是未捕获的 `UnicodeDecodeError`。
- **根因**：`repositories/vault.py::load_note()` 直接 `read_text(encoding="utf-8")`，
  非 UTF-8 抛 `UnicodeDecodeError`；`/api/sources/read` 只检查了 `note.parse_error`（frontmatter 错误）。
- **影响面**：`load_note` 有 **23 个调用点**（项目扫描、问答检索、周报、审批扫描、批量校验…），
  一个坏文件会让多个功能一起 500，不只是来源面板。
- **修复**：把解码失败并入既有的 `parse_error` 通道。这不是语义变更——**全部 23 个调用点本来就都
  检查 `note.parse_error`**（`thread_notes.py` 甚至为此抛 ValueError），`check_vault` 也因此把它
  汇总成一条问题而不是崩溃。`/api/review/source` 另加同样的保护。
- **测试**：`tests/unit/test_vault_repo.py::test_load_note_reports_non_utf8_instead_of_raising`、
  `tests/unit/test_webapi.py::test_api_sources_read_rejects_non_utf8_file_instead_of_internal_error`；
  **两处都做了变异检查**（撤掉修复后测试确实失败），避免写出"怎么都通过"的测试。
- **复验要求**：修复后二进制来源应得到 **415 + 明确文案**，且在 Network 里逐项记录 400/404/413。

### 本轮**因配方写错而产生的假失败**（不是缺陷，已更正配方）

E3 的上一版步骤是「打开详情 → 滚动到中部 → 返回 → 重新进入 → 期望 scrollY 恢复」，
实测 `1359 → 0` 被判失败。查源码后确认这是**符合设计**的：`showProjectView()` 进入详情时
**显式** `window.scrollTo({top: 0})`，它保存并还原的是**打开详情之前列表页**的滚动位置。
E3 应验的是「返回列表后列表滚动位置还原」，更正后的步骤见 `UI-VERIFICATION-BATCHES.md` §6.1。

### 本轮未覆盖

- **B4**：直接启动已安装 App 会绑定真实工作区，执行者主动停止（判断正确）。
  隔离配方已查明：**临时 `HOME`**（`home_dir()` = `Path.home()`）；不能用 `WORK_ROOT`——
  `server_entry.py` 明确打包后的 server 永不消费它。
- **C1**：101 条的拦截文案已观察到，但缺「该次批量操作 Network 请求数 = 0」的原始计数。
- **C4**：「新建会议（个人日程）」= `feishu-meeting` 落点需要飞书。
- **E5 剩余 5 条**：R01 / R04 / R05 / R07 / R09——共同点是只需 DevTools 拦截与计时。

### 第二轮（2026-09-11）：关闭 C1，其余 4 项仍未验证

同一套临时环境（端口 18931、`v2026.09.11-6ff10a6-6e6e0c91`、Chrome `152.0.7977.83`）。

**关闭 1 项 —— C1**：101 条时界面提示上限且 DevTools 过滤 `review/batch` 为 `0 / 2 requests`
（**零请求发出**，这正是第一轮缺的证据）；100 条时为 `1 / 12 requests` 且 `POST /api/review/batch`
返回 `200 OK`，页面显示「待确认 0 · 已批准 100」。两项合起来才算把 `0/1/100/101` 矩阵走完。

**4 项仍未验证，其中 2 项是执行侧问题、不是产品问题**：

| 项 | 卡在哪 | 根因归属 |
|---|---|---|
| R01 / R04 / R09 | 拦截脚本报「没有找到 page target」，`/json/list` 返回 `[]` | **提示词缺陷**：脚本没有自检/自愈。已改为自行查找或新建 page target，并在导航前启用拦截；**已实测**（#1 扣住 4s，#2/#3 通行，#1 最后放行，乱序成立） |
| R07 | 未满足"省略 `workspace_id`"的前置条件 | **提示词缺陷，且原前提写错了**：空安装只跑受限控制面、**没有第二大脑页签**，根本测不了问答历史；正常应用里服务端总会带该字段。已改为用**响应改写**脚本，并**已实测**（页面实际收到去掉 `workspace_id` 的响应） |
| E5 · R05 | 隐藏 141 秒，但未取得切回后的精确计数，也无法区分"守卫生效"与"浏览器节流" | 方法问题：已改为 Console 里 `performance.getEntriesByType('resource')` 计数 + 埋一个 60 秒探针做归因（探针跑了→守卫确实生效；探针没跑→**必须写"无法区分"**） |
| E3 | AX 已显示列表从 `(showing 0-100 of 216 items)` 变为 `(showing 116-216 of 216 items)` | **判断正确**：与"位置被恢复"一致，但缺 `window.scrollY` 数值，不足以排除其他重渲染原因。只差 3 个数字，见提示词任务 0 |

**D2 / C4 / B4 本轮未尝试**（时间用完 / 无飞书授权 / 未纳入本提示词）。

> 值得记一笔：第二轮再次印证了 E5 剩余项的性质——**没有一项卡在产品复杂度上，全部卡在
> 验证基础设施**。两次失败都出在"脚本没自检"这类地方，所以提示词 v2 把
> **先自检、失败就报原始输出**写成了硬要求。

### 第三轮（2026-09-11）：关闭 E3 与 R01，纠正一条**误判**

同一套临时环境（端口 18931、`v2026.09.11-6ff10a6-6e6e0c91`、Chrome `152.0.7977.83`）。

**关闭 2 项**：

- **E3**：夹具自证有效（`scrollHeight=4548 > innerHeight=919`），列表 `Y1=1814` → 详情 `0`
  → 返回 `Y2=1814`，查询/筛选保留。延续两轮的"夹具不可滚动"问题就此终结。
- **R01**：提示词 v2 的自愈脚本一次跑通，真实乱序成立（`#2` 于 `46.524` 先放行，
  `#1` 直到 `52.376` 才放行），最终显示最后点开的项目、焦点在返回按钮上。
  **这直接证明第二轮 R01 没跑成是脚本缺陷而非产品缺陷。**

**⚠️ 一条被误判为失败的项 —— R07（不是缺陷）**

第三轮把 R07 报为「失败」：剥离 `workspace_id` 后问答会话从 `2/10` 变成 `0/10`。
**这是误判，责任在我的通过标准**：会话建在真实 workspace 键下，而字段被剥离后客户端切到了
回退键 `'unknown'` 的存储——**那是另一个存储键，为空是正常的**，切 workspace 时清空是
有意设计（代码注释："旧工作区的预演/在途写回标记不得带入新工作区"）。

R07 真正要验的是「省略字段时本地历史**仍被载入一次**」。看修复提交 `ee561f5` 的 diff 即可确认：

```diff
-let loadedAskWorkspace = 'unknown';
+let loadedAskWorkspace: string | null = null;
```

修复前初值是 `'unknown'`，而回退值也是 `'unknown'`，守卫 `'unknown' !== 'unknown'` **恒为假**
→ `loadAskStore()` 永不被调用（这正是那个 bug）。修复后 `null !== 'unknown'` → 进入重置块并
调用 `loadAskStore()`（`legacy-main.ts:558-559`）。该修复另有源码契约测试锁定
（`test-browser-contract.mjs:140`）。

**正确判据**：在字段被剥离的状态下新建会话，**刷新后仍应存在**（修复前会丢）。
已据此更正提示词。

**两项被我的配方挡住（已修，且都不需要真实凭据）**：

| 项 | 上一轮卡点 | 更正 |
|---|---|---|
| R04 | 「无模型凭据，未执行真实保存」 | **不需要凭据**：`POST /api/settings/provider` 走 `update_provider_settings(...)`，**不校验**密钥（校验是另一个 `/verify` 路由）。用假密钥即可制造"保存后状态" |
| R09 | 「外部写回列表为空，无新旧数据可比较」 | **不需要飞书**：`/api/external-actions` 读本地账本 `_vault/_signals/external-actions/log.jsonl`，直接造行即可（`kind`/`state` 枚举与 `workspace_id` 归属已写入提示词） |

**其余未验证**：R05（未执行真实隐藏 ≥130 秒）、D2（HTTP 矩阵已拿到，缺界面文案与第二
workspace 隔离）、C4（无飞书授权，**唯一真正需要用户凭据的一项**）。

> 第三轮的教训与前两轮同类，但方向相反：前两轮是"脚本没自检"，这一轮是**我的判据本身写错**，
> 导致一个**正常工作的修复被报成失败**。写判据前应当先确认"这个现象在设计上应该是什么样"——
> 尤其是涉及分键存储（workspace/profile）的行为。

### 第四轮（2026-09-11）：关闭 R07 与 D2，并再次更正两条配方

同一套临时环境（端口 18931、`v2026.09.11-6ff10a6-6e6e0c91`、Chrome `152.0.7977.83`）。

**关闭 2 项**：

- **R07**：按更正后的判据一次通过——剥离 `workspace_id` 后新建会话 `2/10`，**连续刷新两次仍是
  `2/10`**，`localStorage` 为 `["wb.ask.threads.v1.unknown"]`。这条证据同时确认了两件事：
  回退键存储确实被使用，且 `loadAskStore()` 确实被调用（修复前它永不被调用）。
- **D2**：逐项经**「来源」入口**观察面板文案，8 个用例全部可见且可区分；非 UTF-8 显示
  「来源暂时不可读 / 来源不是可读取的 Markdown 笔记」（**415**，第一轮缺陷在此确认真实修复）；
  双 workspace 隔离用不同内容验证通过。**第一轮以来的 D2 至此完整闭合。**

**两条配方又被证明是错的（都由我造成）**：

| 项 | 我上一轮的说法 | 实际 | 更正 |
|---|---|---|---|
| R04 | "用假密钥即可，保存路径不校验" | ❌ **错两处**：① `saveModel` 里有 `if (!secret) { toast('请先粘贴 DeepSeek API Key'); return; }`，**表单拒绝无密钥提交**；② `update_provider_settings` 会 `security add-generic-password` **写登录钥匙串**——而钥匙串**不受临时 `HOME` 隔离**，ACL 不含调用方时会弹 GUI 授权框阻塞，这正是执行者观察到的"请求 10 秒未返回"。我上一轮只读到 `settings_provider` 那一层就下了结论，**没往下读 `update_provider_settings` 与 `config/secrets.py`** | 改为**无凭据**方案：只验 `settingsRenderSequence` 守卫本身——扣住 `/api/settings/profiles` 的 #1，改**临时 `HOME` 内** registry 的 `display_name`，切页签触发 #2 渲染新值，再放行 #1，断言不被覆盖回旧值 |
| R09 | "本地造 outbox 行即可"（这一半是对的） | 数据造出来了，但**旧脚本只扣 6 秒**，执行者来不及在其间触发第二次读取，于是 `#2` 在 `#1` 放行**之后**才到达，严格乱序不成立 | 改为**闸门式**：扣住 #1 直到 `touch` 一个文件为止，时序完全由执行者掌控。**已实测**（#1 扣住期间 #2–#5 正常通行，`touch` 后 #1 才放行） |

> 第四轮的教训最具体：**R04 那次我只读了一层就宣布"不需要凭据"**。上一轮我刚写下"写判据前
> 要先确认设计意图"，这一轮就犯了"读代码只读到调用的那一层"。涉及凭据/钥匙串这类**跨出临时
> 环境边界**的副作用，必须追到真正落盘/落 Keychain 的那一行。

**仍未验证**：R04（配方已改）、R05（未真的隐藏 130 秒）、R09（配方已改）、C4（待飞书授权）、
B4（临时 `HOME` 隔离配方已查明，未执行）。

### 第五轮（2026-09-11）：关闭 R04；B4 出现一条**判据错误**

同一套临时环境（端口 18931、`v2026.09.11-6ff10a6-6e6e0c91`、Chrome `152.0.7977.83`）。

**关闭 1 项 —— R04**：改用**无凭据**配方后一次通过。时间线很有说服力：
`/api/settings/profiles` 的 #1 于 `23:14:46.314` 被扣住，其间把临时 `HOME` 内 registry 的
`display_name` 从 `work` 改为 `work 【已更新】`，#2 于 `23:15:18.711` 放行并渲染出新值，
#1 直到 `23:15:48.268` 才放行——**放行后页面仍显示 `work 【已更新】`**，即过期响应被
`settingsRenderSequence` 丢弃。这同时回避了上一轮那个必然阻塞的路径（写登录钥匙串）。

**⚠️ B4 的"未隔离"结论很可能是误判 —— 判据选错了**

执行者看到子进程参数含 `--work-root /Users/<真实用户>/Documents/Work`，据此判定原生 App
未按临时环境隔离并停止。停止本身是稳妥的，但**那个参数不是判据**：

- `webapp/server_entry.py:112` 是 `resolve_active_workspace(allow_env_fallback=False)` ——
  打包服务**根本不消费 `--work-root`**，工作区只从 profile registry 解析
  （`Path.home()` 派生，即受 `$HOME` 影响）。
- 而原生层**确实读环境变量**：`native/SummitWorkbench/Models.swift:124`
  `let workRoot = environment["WORK_ROOT"] ?? (NSHomeDirectory() + "/Documents/Work")`。
  上一轮**只设了 `HOME`、没设 `WORK_ROOT`**，所以它按 `NSHomeDirectory()` 回退到了真实家目录；
  那个被打印出来的参数正是这次回退的产物，而它随后被服务端忽略。

**附带纠正我自己的错误**：我在 `UI-VERIFICATION-BATCHES.md` §9 与上一版提示词里写过
"**不能用 `WORK_ROOT` 隔离**"——**这句话是错的**，原生层就是读它的。正确做法是
**`HOME` 与 `WORK_ROOT` 同时设**，并且**按界面显示的工作区**判断隔离是否成立。

**其余两项的卡点（都是时序/触发方式，不是产品问题）**：

| 项 | 卡点 | 更正 |
|---|---|---|
| R09 | `#2` 已先到达并渲染 2 条，但放行 `#1` 时报 `Invalid InterceptionId`——**被扣住的旧请求已被页面取消**（切页签导致），"旧响应返回"这一步没有真正发生 | 改为**页内点「批准」**触发第二次读取（`decide` → `refreshReview()` → `refreshExternalActions()`，不离开页面）；脚本新增**取消计数**，非 0 即判本次不成立。（dry-run 的「检查并写回」不触发 `refreshReview`，已注明） |
| R05 | **连续三轮**未真正隐藏 ≥130 秒 | 改为 `visibilityState` 覆盖 + 派发 `visibilitychange`：不用真隐藏，且页面始终可见 ⇒ **定时器不被节流**，再用 5 秒探针（`tick`）证明这点，于是"没有发请求"就是守卫生效，**彻底消除"无法区分"** |

> 第五轮的教训是关于**判据的选择**：同一个现象（进程参数里出现真实路径）既可能意味着"没隔离"，
> 也可能只是"参数被传了但会被忽略"。**判据必须落在真正决定行为的那一层**——这里是服务端的
> `resolve_active_workspace`，以及界面上显示的工作区，而不是子进程的 argv。

### 第六轮（2026-09-11）：关闭 R05；查明 B4 卡在启动页的根因

同一套临时环境（端口 18931、`v2026.09.11-6ff10a6-6e6e0c91`、Chrome `152.0.7977.83`）。

**关闭 1 项 —— R05**：`base={version:3,sync:3}` → `after={version:4,sync:4}`，**各恰好 +1**；
`tick=14`（70 秒 ÷ 5 秒探针）证明**隐藏期间定时器确实在运行**，因此"没有发出请求"只能解释为
可见性守卫生效，而不是浏览器节流。**连续三轮悬而未决后，用 `visibilityState` 覆盖 +
派发 `visibilitychange` 的办法一次通过**——关键是它顺带消掉了归因歧义。

**B4 卡在「正在启动 SummitWorkbench…」的根因（不是产品缺陷）**

执行者按 v5 配方启动后，App 永久停在启动页，且报告"两个日志目录都没有输出"。查证后：

1. **日志位置找错了**。真实日志在 **`~/Library/Logs/summitworkbench-panel.log`**——这是一个
   **文件**（`ServiceSupervisor.swift:163` 用 `NSHomeDirectory()` 拼的），
   不是 `~/Library/Logs/SummitWorkbench/` 目录。
2. 日志显示稳定的失败循环：`service_spawned` → 13 秒后
   `service_exited reason="readiness_timeout"` → 指数退避重启（1s/2s/4s/8s），周而复始。
3. **根因是就绪握手的两侧路径不一致**：App 用 **`NSHomeDirectory()`**（不认 `$HOME`）读
   `<真实家目录>/…/SummitWorkbench/runtime.json`；服务用
   `active_workspace.runtime_dir or active_workspace.application_support`（来自
   **`Path.home()`**，认 `$HOME`）写。设了临时 `HOME` 之后，**服务写进临时家目录、
   App 去真实家目录找** → 端口永远拿不到。
4. 直接运行打包服务可确认**服务本身完全正常**（进程存活、绑定端口、`/api/version` 返回 401
   属缺令牌的正常行为）。

**修法（已实测）**：显式传 `WB_RUNTIME_RECORD`。服务端支持该变量
（`server_entry.py:88`），且子进程继承 App 的环境（`ServiceSupervisor.swift:151`）。
实测结果：记录被写到 App 会读的那个真实路径，**临时 `HOME` 下不写任何东西**，
且记录里 `workspace_id: null`——**证明确实是空安装、没有指向真实工作区**。

**副作用与前置条件（已写进提示词）**：该记录会落在**真实** app-support 目录，所以必须先确认
**真实 App 未运行**且 `runtime.json` **本来就不存在**；收尾时确认它已被清理。
（本次核查时两者均满足，验证后已复原。）

**R09 只差最后一步**：这一轮拿到了放行**前**的 2 条（`#1` 于 `23:32:18` 扣住、`#2` 于
`23:32:52` 放行渲染 2 条、`#1` 于 `23:33:15` 放行），但**没人记录放行之后**列表的状态，
而脚本汇总行也没打出来，所以只能判未验证。提示词已把"放行 #1 后再读一次列表"明确成独立步骤，
并把汇总行改成**正常退出 / Ctrl-C / 异常退出都会打印**。

**另修一处运行环境问题**：上一轮有临时夹具脚本被种进了**仓库目录**——原因是跨命令用
`$(cat /tmp/xxx 2>&1)` 取临时路径，文件不存在时 `cat` 的**报错文本**变成了路径值，
而脚本里的 `Path(...)` 是相对路径。已清理该目录，并在提示词里加了
`ISO`/`WORK_ROOT` 非空断言与明确警告。

### 第七轮（2026-09-11）：关闭 R09 与 B4 —— **UI 层开放项清零**

**关闭 2 项，也是最后 2 项 UI 层开放项**：

- **R09**：`/api/external-actions` 的 `#1` 于 `00:27:52.519` 被扣住，**在审批页内点「批准」**
  触发 `#2` 于 `00:28:34.332` 放行并渲染 2 条，`#1` 于 `00:28:40.555` 才放行。
  **放行前与放行后的列表逐字一致（均为「旧的一条」+「新的一条」）**，脚本汇总
  `拦截 2 次，放行失败 0 次`——即旧响应**确实返回过并被丢弃**，不是"从没返回"。
  这条把上一轮缺的那一步补上了。
- **B4**：按第六轮查明的配方（临时 `HOME` + `WORK_ROOT` + **`WB_RUNTIME_RECORD`**）启动原生 App，
  **成功进入设置页**并显示工作区 `work` / `/tmp/swb-app-v5-6ib3gW/work/_vault`
  ——**临时路径，不是真实工作区**，隔离成立。六页签（今日/审批/第二大脑/项目/指南/设置）全部可达；
  重启后显示「界面 v2026.09.11-6e6e0c91 · 服务 0.4.4 · 已同步」；收尾后真实 `runtime.json`
  为 `absent`、临时目录已删除。**第六轮那个 `WB_RUNTIME_RECORD` 修法被真机证实有效。**

**至此 UI 层（B/C/D/E 组）开放项全部关闭。** 仍在清单上的只剩：

| 项 | 性质 |
|---|---|
| A6 真实双设备冲突恢复 | 需第二台机器（MacBook Air 现场复跑）；**代码路径已有端到端自动化 + 变异测试覆盖** |
| F1 Developer ID / 公证 / Intel / Windows | **明确超出 `INTERNAL-DEV` 交付范围，非缺陷** |

> **一个可选的产品加固（尚未采纳，记录备查）**：原生层从不向子进程传 `--runtime-record`，
> 而是各自推导——App 用 `NSHomeDirectory()`（不认 `$HOME`），服务用 `Path.home()`（认 `$HOME`）。
> 也就是说产品**隐式假设「`NSHomeDirectory()` == `$HOME`」**。正常使用下两者一致，**不是缺陷**；
> 但若用户从终端以不同的 `HOME` 启动，打包 App 会正好复现第六轮那个 `readiness_timeout` 卡死。
> 彻底的修法是让原生层显式传 `--runtime-record`（约一行），从而不必依赖该假设。
> 因属超出本次验收范围的产品代码变更，**未擅自修改**。

> **上述加固已于 2026-09-12 采纳**（用户明确批准）：`ServiceSupervisor.swift` 现在显式设置
> `WB_RUNTIME_RECORD`，并新增契约测试锁定；原生源码 `swiftc -typecheck` 通过、变异检查有效。
> **仍待重新打包 App** 才会在产物中生效。

### 第八轮（2026-09-12）：关闭 C4 —— **UI 层开放项最终清零**

**关闭 1 项**：C4「新建会议（个人日程）」落点。在**隔离 vault**（临时 vault + 真实
`workspace_id` 以命中 Keychain + **无远端**）上跑通真实飞书日历端到端：

| 环节 | 证据 |
|---|---|
| 资格 | 卡片 `目标：unresolved · 落点：新建会议`；「✓ 批准 → 新建会议」`disabled=false`（**目标项目豁免在真实页面成立**） |
| 批准 | `待确认 0 · 已批准 1`，toast「仅标记，点「应用（写回）」才真正写回/建任务」 |
| 预演 | `预演计划（未写入）` / `DRY-RUN（零写入）` / `批准写回=0 拒绝归档=0 失败=0`；**日历仍为空** |
| 写回 | `批准写回=1 拒绝归档=0 失败=0`，并写出审计文件 |
| 回读 | 事件 `444bb8ea-7462-4c20-be51-6f6480420a30_0`，标题与候选一致，`start=1789264800` / `end=1789268400`（Asia/Shanghai ⇒ 10:00–11:00，与 `start_at`/`end_at` 一致） |
| 删除 | 该事件 `status=cancelled`；`2026-09-13` 时间窗内**无活动事件** |

**收尾**：真实 profile 已按备份逐字节复原（哈希一致、路径指回真实 vault、remote 恢复）；
真实 vault 干净且 HEAD 仍为 `8dba623`，`review/meetings.md` 哈希与原始一致；临时目录全部删除；
无残留服务进程。

**本轮查明两条重要机制（对以后所有"真实写回"验收都适用）**

1. **Web 写操作会自动 commit 并 push。** `legacy_app.py` 的 `_run_web_mutation` 是**所有** web
   写操作的公共入口，它**总是**传 `push_after_commit`。因此在**带远端的真实 vault** 上做写回，
   会把提交**推送到真实远端**——而远端历史**无法用本地 `reset` 收回**（产品设计绝不 force-push）。
   结论：**任何会产生真实写回的验收都必须在无远端的隔离 vault 上做**，否则测试数据会永久留在
   知识库远端。
2. **`HOME` 隔离会同时切断 Keychain 访问。** `security` CLI 按 `$HOME` 解析钥匙串，
   临时 `HOME` 下没有 `login.keychain-db`，于是 workspace 凭据一律"找不到"（本轮第一次尝试的
   失败原因：`未在 Keychain 找到 refresh_token`）。**这与第六轮 runtime 记录路径问题同源**——
   都是"以为 `HOME` 能隔离一切"。因此要在隔离环境里用真实凭据，必须**保留真实 `HOME`**，
   只把 `vault_dir` 指到临时 vault。

> 第八轮的教训是**验收环境的边界**：`HOME` 不是一道干净的隔离墙（runtime 记录、Keychain 都
> 按它解析），而真实 vault 的写回会**自动外发**。两个机制叠加，决定了"真实外部服务的写回类
> 验收"唯一的正确形态是：**真实 `HOME` + 隔离 vault + 无远端 + 真实凭据**。

## 已关闭（保留证据指针）

| 项 | 关闭日期 | 证据 |
|---|---|---|
| A1 真实云端模型四项未复跑 | 2026-09-11 | 会议结构化 3 场；捕捉分类（含日期缺陷修复 `562c4fd`）；`wb brief` 真实排序 `ranking_degraded=false`、行动项 5/5；`wb ask` 事实带来源、无幻觉。详见 §L |
| A3 飞书任务写回 | 2026-09-11 | 真实飞书 `create→update→complete→delete` 全链路通过，测试对象已删除。详见 §L |
| A4 飞书日历写回 | 2026-09-11 | 真实飞书 `create→update（改名+改时间）→delete` 通过并回读校验。详见 §L |
| A2 飞书 OAuth 全链路未复跑 | 2026-09-11 | authorize-url（state 核对）→ 浏览器授权 → `login` 写入 refresh_token → `smoke` 经刷新令牌通过；scope 含 `calendar:calendar` 与 `task:task:write`。详见 §L |
| A5 真实远端 Git 未复跑 | 2026-09-11 | `acceptance_preflight` 11 项全 PASS（HTTPS scheme / workspace Keychain 凭据 / HTTPS fetch）；`wb sync` up-to-date；真实 push 到远端临时分支成功并删除，`main` 未变。详见 §L |
| 快速捕捉分类算不出日期（相对/绝对日期均错） | 2026-09-11 | `562c4fd`：把工作区时区的当天日期注入系统提示；实测「9月20日前」由 2025-09-20 修正为 2026-09-20、「下周三前」由 2026-05-13 修正为 2026-09-16。详见 §L |
| 10 MiB 逐字稿上限未覆盖 CLI 路径 | 2026-09-11 | `7e25cd3`：上限下沉到 workflow 层（`MAX_TRANSCRIPT_BYTES`），两个扫描函数都执行，CLI 显式列出被跳过文件；真实对比 419 万 → 12 input token。详见 §K |
| 审批创建的飞书任务缺少负责人 | 2026-09-11 | `7b20002`：`create_task` 带 `members[{role:"assignee"}]`，CLI 与面板两处接入；真实验证「我的任务」3→4 条，修复前那条仍不在列表。详见 §K |
| 远端 CI 从未真正运行 | 2026-09-11 | 仓库迁移到 `SummitYifeng/SummitWorkbench`；quality-gate + arm64/x86_64 矩阵 + workflow lint 全绿 |
| `packaged App smoke` 从未纳入 CI | 2026-09-11 | `ci.yml` arm64 构建矩阵 `WB_PACKAGED_APP` 步骤 |
| macOS framework Python 下 runtime record 身份误判 | 2026-09-11 | `src/summit_workbench/webapp/runtime.py` + `tests/unit/test_runtime_record.py` 回归测试 |
| 冲突恢复提交无自动化端到端覆盖（A6 的代码路径部分） | 2026-09-11 | `tests/integration/test_acceptance_dual_device.py`（变异测试验证有效） |
| Node 20 弃用告警 | 2026-09-11 | action 升级到 node24 大版本，告警清零 |
| 「本地绿、CI 红」反复发生 | 2026-09-11 | `scripts/pre-push-gate.sh` + `scripts/check-action-refs.sh` + pre-push hook |
| `release.yml`（tag 触发）从未在组织下实跑 | 2026-09-11 | `v0.4.4-rc.1` 运行成功：签名 DMG + `update-feed.json` + SBOM + SHA256SUMS 全部产出，作为 **prerelease** 发布到公开 Updates 仓库；`latest` 仍为 `v0.4.2`，rc 未污染 stable 通道；证明最小权限 `contents: read` 与升级后的 action 在发布路径同样可用 |
| 冲突恢复无法在 CI 中验证 | 2026-09-11 | `test_dual_device_divergence_recovery_converges_with_two_parent_merge` 随全量测试在 CI 运行 |
| 依赖漏洞无人监控（CVE 可能静默存在） | 2026-09-11 | 开启 Dependabot **alerts** + **security updates**（`automated-security-fixes.enabled = true`）；依赖图 122 个包；扫描完成后报出 4 条告警，均为不可达 advisory，逐条评估见 §I |
| 前端工具链 major 升级（Vite 8 / TS 7） | 2026-09-11 | 真实浏览器验收 A/B/C/F/G 全过后合并：`6ff10a6` + `2722aa9`（产物 `v2026.09.11-6ff10a6-6e6e0c91`）；详见 §J |
| 前端脚本的幽灵依赖（`esbuild` 未声明） | 2026-09-11 | `f8b40c7` 显式声明 + 契约测试 `test_frontend_scripts_only_import_declared_packages` |
| Chrome 原生 200% 缩放（B1） | 2026-09-11 | 提示词 F 在候选产物上人工确认正常 |
| 浅色主题（B2） | 2026-09-11 | 提示词 F 人工确认文字对比度与状态徽标可读 |
| 系统 `prefers-reduced-motion`（B3） | 2026-09-11 | 提示词 F 确认动画被抑制 |
| `v0.4.4-rc.1` 测试产物遗留在公开渠道 | 2026-09-11 | 已删除 prerelease 与本地/远程 tag；`latest` 保持 `v0.4.2` |
| C2「一次点击一次请求」网络计数 | 2026-09-11 | 真实浏览器 Network 计数：单击 `apply` = 1；双击时在途 `disabled` 且最终仍 = 1（`2.04 s`）。详见 §M |
| R08「一键拒绝过期项」范围与禁用 | 2026-09-11 | 0 条时原生 `disabled`，title 说明范围不受当前筛选影响。详见 §M |
| D3 正文截断提示的真实显示 | 2026-09-11 | `big.md` 显示「正文已截断」，`textContent.length === 100000`。详见 §M |
| E1 冲突包导出下载的确定性证据 | 2026-09-11 | Chrome 原生下载记录 `summitworkbench-sync-recovery.zip · 979 B · 完成`；上一轮"观测不到"是 In-app Browser 通道限制。详见 §M |
| E2 确认框关闭后的稳定返回焦点 | 2026-09-11 | 原生确认框出现并可取消，焦点实际回到冲突选择框。详见 §M |
| E4 动态 loopback 端口同源边界 | 2026-09-11 | 实测端口 A 草稿在端口 B 丢失（`0/10`、输入框空），与指南「不承诺迁移」一致，**既定边界非缺陷**。详见 §M |
| R03 撤销弹层语义与焦点归还 | 2026-09-11 | `role=dialog` + `aria-modal` + 关闭按钮；关闭后 `activeElement.id === "btn-undo"`。详见 §M |
| R06 同步横幅读取失败的表现 | 2026-09-11 | 失败时保留上次状态并标注「同步状态读取失败……（上方为上次成功读取的状态）」。详见 §M |
| R10 长文本上限的本地拦截 | 2026-09-11 | 100001 字符被本地拦截并提示上限，未发请求。详见 §M |
| R11 双击重复提交 | 2026-09-11 | `/api/threads/logs` 计数 = 1（`2.02 s`），按钮在途 `disabled`。详见 §M |
| 非 UTF-8 来源打开返回 500（前端显示无信息兜底） | 2026-09-11 | `load_note` 把解码失败并入 `parse_error` 通道（23 个调用点本就都检查它），`/api/review/source` 同样加保护；两个回归测试均通过变异检查。详见 §M |
| C1 `0/1/100/101` 完整矩阵 | 2026-09-11 | 第二轮真实浏览器 Network 计数：101 条为 `0 / 2 requests`（界面提示上限、**零请求发出**）；100 条为 `1 / 12 requests` 且 `POST /api/review/batch` 返回 `200 OK`，页面显示「待确认 0 · 已批准 100」。详见 §M 第二轮 |
| E3 项目可移动滚动位置恢复 | 2026-09-11 | 第三轮真实数值：夹具 `scrollHeight=4548 > innerHeight=919` 自证有效；列表 `Y1=1814` → 打开详情 `0`（设计如此）→ 返回 `Y2=1814`，查询框 `""`、筛选 `"all"` 保留。详见 §M 第三轮 |
| R01 项目详情过期响应的交互复验 | 2026-09-11 | 第三轮真实乱序：`/api/projects/view` 的 `#1` 在 `13:05:46.373` 到达并被扣 6000ms，`#2` 于 `13:05:46.524` 立即放行，`#1` 于 `13:05:52.376` 才放行；最终显示**最后点开**的 `synthetic-project-01`，`document.activeElement` 为「← 返回项目列表」按钮。详见 §M 第三轮 |
| R07 省略 `workspace_id` 时问答历史仍载入一次 | 2026-09-11 | 第四轮：剥离 `workspace_id` 后新建会话 `2/10`，**连续刷新两次仍是 `2/10`**，`localStorage` 为 `["wb.ask.threads.v1.unknown"]`——证明本地历史确实按回退键载入。第三轮曾误判为失败（见 §M 第三轮） |
| D2 来源面板异常矩阵（浏览器层） | 2026-09-11 | 第四轮逐项经「来源」入口观察面板文案：非 UTF-8 →「来源暂时不可读 / 来源不是可读取的 Markdown 笔记」（**415，第一轮缺陷确认真实修复**）；`big.md` →「正文已截断」且 `pre.source-reader.textContent.length=100000`；`huge.md` → 413 文案；路径穿越 / 软链越界 / `_signals/` / `notes/` → 400 文案；缺失 → 404 文案。**双 workspace 隔离**：第一 workspace 读到 `# Demo Project`，第二 workspace 读到 `# Second Workspace Demo` + `SECOND-WORKSPACE-CONTENT`。详见 §M 第四轮 |
| R04 设置页不被过期读取覆盖 | 2026-09-11 | 第五轮（改用**无凭据**配方，见 §M 第五轮）：`/api/settings/profiles` 的 #1 于 `23:14:46.314` 被扣住，#2 于 `23:15:18.711` 放行并渲染出新值 `work 【已更新】`，#1 于 `23:15:48.268` 才放行，**放行后页面仍显示 `work 【已更新】`** —— 证明 `settingsRenderSequence` 守卫生效 |
| R05 隐藏页暂停 + 回到前台补一次 | 2026-09-11 | 第六轮：把 `visibilityState` 做成可控并派发 `visibilitychange`。`base={version:3,sync:3}` → `after={version:4,sync:4}`（**各恰好 +1**），且 `tick=14`（70 秒 ÷ 5 秒探针）**证明隐藏期间定时器确实在跑、未被节流** → "没有发出请求"只能是可见性守卫生效。详见 §M 第六轮 |
| R09 外部写回列表不被旧响应覆盖 | 2026-09-11 | 第七轮：`/api/external-actions` 的 `#1` 于 `00:27:52.519` 扣住，**页内点「批准」**触发 `#2` 于 `00:28:34.332` 放行并渲染 2 条，`#1` 于 `00:28:40.555` 才放行；**放行前与放行后列表逐字一致（均为 2 条）**，脚本汇总 `拦截 2 次，放行失败 0 次`（旧响应确实返回过）。详见 §M 第七轮 |
| B4 packaged App / WKWebView 黑盒 | 2026-09-11 | 第七轮：临时 `HOME` + `WORK_ROOT` + `WB_RUNTIME_RECORD` 启动原生 App，设置页显示工作区 `work` / `/tmp/swb-app-v5-6ib3gW/work/_vault`（**临时路径，非真实工作区**）；六页签（今日/审批/第二大脑/项目/指南/设置）全部可达；重启后显示「界面 v2026.09.11-6e6e0c91 · 服务 0.4.4 · 已同步」；收尾后真实 `runtime.json` 为 `absent`。详见 §M 第七轮 |
| C4「新建会议（个人日程）」落点 | 2026-09-12 | 第八轮，真实飞书日历端到端（隔离 vault，真实 workspace_id 以命中 Keychain，无远端）：候选 `目标：unresolved · 落点：新建会议`，「✓ 批准 → 新建会议」**可用**；预演 `DRY-RUN（零写入）` 且日历仍为空；写回 `批准写回=1 失败=0`；回读事件 `444bb8ea-…` 标题与候选一致、`start=1789264800 / end=1789268400`（Asia/Shanghai，即 10:00–11:00）；删除后该事件 `status=cancelled`、当日时间窗无活动事件。详见 §M 第八轮 |
| 原生层未显式传 runtime 记录路径（隐式假设 `NSHomeDirectory() == $HOME`） | 2026-09-12 | `ServiceSupervisor.swift` 子进程环境新增 `environment["WB_RUNTIME_RECORD"] = RuntimeRecord.url.path`，消除该假设；服务端本就支持该变量（`server_entry.py:88`）且子进程继承 App 环境。新增契约测试 `test_service_supervisor_pins_runtime_record_path_for_the_child`（**变异检查**：删掉该行即失败），原生源码 `swiftc -typecheck` 通过。**需重新打包 App 才在产物中生效** |

## N. A6 / A7 双机现场复跑（2026-09-13，build 28 / `2b534e0`）

> build 29 上的逐条复核（D1/D2/D5/D6 的判据）、第二轮冲突恢复与 D7/D8 的现场发现、以及收尾收敛状态，
> 见下面的 **§O**。

两台机器：Studio（automation-primary）+ Air（secondary，全新空安装），装**同一个** DMG
（`SummitWorkbench-0.4.7-arm64-INTERNAL-DEV.dmg`，build 28，SHA-256
`1b8e9815023ee7f5abe3292cb464ab54abbc1f35228229f90ad5ea1bd8c2d953`）。
演练用一次性私有仓库 `SummitYifeng/summitworkbench-rehearsal` 与工作台 `~/Documents/Rehearsal`，
**全程未触真实 vault**（两台的真实 profile 目录在演练期间改名存放，事后原样恢复）。
操作步骤与铁律见 [`DUAL-DEVICE-REHEARSAL.md`](DUAL-DEVICE-REHEARSAL.md)。

### A7 · 第二台机器「从另一台 Mac 克隆」首次现场通过

| # | 证据 | 结果 |
|---|---|---|
| 1 | Air profile：`workspace_id` 与 Studio 相同（`5ead7279-…`）、**`device_role = "secondary"`**、`git_username` 与 `git_remote_url` 已回填 | ✅ |
| 2 | Air 界面可见 Studio 先前捕捉的那条（实际输入为 `测试的`，即 `a21c8e5` 提交；克隆确实带过来了） | ✅ |
| 3 | workspace 级 Keychain 凭据存在（`com.summitworkbench.credentials.5ead7279-…` / 账户 `git:github.com:Yifeng93`，值为 `github_pat_…`） | ✅ |
| 4 | 草稿文件**不含任何秘密**（`grep -c github_pat` = 0；字段白名单由 `OnboardingDraft` 的 `extra="forbid"` 保证） | ✅ |
| 5 | 仓库历史**不含 PAT**（`git log -p \| grep -c github_pat_` = 0） | ✅ |

### A6 · 冲突恢复端到端闭环（当前 build）

以下均为**远端权威取证**（`gh api` 读远端提交与树），不是本地推断：

| 项 | 证据 |
|---|---|
| 分歧与保护态 | Air 离线捕捉 → Studio 联网捕捉并推送 `8bcb710` → Air 重试进入 `diverged-protected`，Air 的本地提交 `13eaeb8` 未被改写 |
| 人工选择 | 弹层显示三方短码（base `a21c8e5` / local `13eaeb8` / remote `8bcb710`）与需选择的 `inbox.md`，选择 **`preserve-both`**；临时预检（不写入）通过后才可确认 |
| 双父恢复提交 | **`39611ca`，`parents=2`**，消息 `wb: sync recovery events=0 views=0 paths=1` |
| 脱敏审计提交 | **`1c06e43`**（`wb: sync recovery audit`）；`_signals/sync-conflict-recovery/log.jsonl` 仅含 revision / 计数 / 选择（`selections: {"inbox.md":"preserve-both"}`、`status: committed`），**无任何正文** |
| preserve-both 落地 | `inbox.md` 保留本机内容（`离线-B`）、`inbox.md.remote` 存远端内容（`离线A` + `测试的`）——**两侧内容都在** |
| 普通 push 与对端收敛 | 两个提交都在远端；Studio 由 `8bcb710` **快进**到 `1c06e43`（没有第二个冲突提交），两台同 HEAD、工作树 clean、`ahead/behind 0/0` |
| 横幅读取失败守卫 | 无法用"关 Wi-Fi"触发（`/api/sync/status` 只读本地内存快照 + 本地文件，**不联网**）⇒ 改为自动化行为测试（非 ready 时保留横幅 + 说明行 + 「重新读取」；ready 时保持隐藏），提交 `78c514f`，变异验证通过 |

> build 29 / `697c239` 的完整口径（未知视图与二进制 `preserve-both`、`conflict_snapshot_stale`、
> `current_worktree_dirty`、审计失败分支）仍见
> [`../archive/acceptance/P2-02-BUILD-25-STUDIO-AIR-RUNBOOK.md`](../archive/acceptance/P2-02-BUILD-25-STUDIO-AIR-RUNBOOK.md)；
> 本轮是"差异点抽查 + 一条端到端闭环"，把结论落在当前 build 上。

### 本轮发现的产品缺陷（D1–D8 **已修**，D9 待修）

> 后续：D9 已在 **build 34** 修复，见 §R。

修复提交：D1 `98fcd84` / D2 `95cc848` / D3 `b5d4a2b` / D4 `2b534e0` / D5 `d2b07bd` / D6 `9ce7205` /
D7 `fd19603` / D8 `fd19603`。其中 D6 是用户可见的新增能力（顶部栏「⇅ 立即同步」+ 空闲自动拉取），
其余是缺陷修复；D4 随 build 28，D1/D2/D3/D5/D6 随 **build 29** 出包。
**D7/D8 是收尾阶段发现的，只以源码 + 单元/契约测试 + 变异验证收口，尚未打进任何 DMG**
（前端静态资源已重建为 `v2026.09.13-fd19603-c7517c5a`，下一次打包自然带上；真实 UI 复验需要
build 30 或更高；复现步骤已写进排练文档的文末说明）。

见 [`DUAL-DEVICE-REHEARSAL.md`](DUAL-DEVICE-REHEARSAL.md) 文末「附」：D1 新工作台不 `git init`
（预览 500 + 写回留痕静默失效）、D2「确认并转换」后仍用启动快照（同进程同步必失败、重启才恢复）、
D3 同步失败原因被吞成裸 `error`、D4 私有 clone 失败被兜底吞掉（同一意图在两层各写了同名守卫）、
D5 向导草稿收尾不干净、D6 干净工作区没有主动拉取入口（`sync_workspace` 只被 `/api/sync/run` 调用，
读路径与 60s 轮询都不 fetch，而该按钮只在横幅可见时存在）、
D7 恢复预检被拒时界面只说"恢复准备未完成"（后端已给 `error_code`，前端丢弃 ⇒ 与 D3 同类的可诊断性缺陷）、
D8 同一路径第二次选「保留双方副本」必然 `preserve_both_path_collision`（恢复对同一文件不可重复执行）。

### 本轮未覆盖 / 后续排期（**不是本轮缺陷**，是已知产品缺口）

这些是复跑过程中顺带确认的**能力缺口**，都能用命令绕过、不阻塞演练，登记在此免得丢失：

| # | 缺口 | 证据 | 影响 |
|---|---|---|---|
| G1 | 界面没有 `automation-primary` 的**显式接管**入口 | `POST /api/sync/primary/claim`（`routers/sync.py:398`）全仓只有后端定义，前端只**显示** `automation_primary_device_id`（`features/sync/banner.ts:35`），没有任何调用点 | 主设备代数变更只能靠命令行/直接调 API；换机或主设备丢失时需要人工介入 |
| G2 | 界面没有把**已有本地工作台首次发布到新远端**的路径 | 设置页的 remote 区块只做**规范化**（preview 要求已存在 `origin` + `upstream`，`routers/settings.py:808`）；向导的 remote 模式只做 **clone**（已有远端 → 本地） | 本地已存在、远端还没建的工作台必须手工 `git init` / `git remote add` / 首次 push（本轮 §A7 第 4 步就是这么绕的） |
| G3 | 同步/面板日志缺少失败细节 | D3 只解决了**状态可读性**（稳定错误码 + 脱敏原因进 `sync-state.json` 与横幅）；`workflows/sync_coordinator.py` 与 `domain/sync.py` 里**没有任何 logger 调用**，`~/Library/Logs/summitworkbench-panel.log` 至今只有 `component: "launcher"` 记录 | 排查"昨晚为什么没同步"只能去翻 API 内存快照或重启 App 触发一次；日志文件本身永远不含同步失败 |

## O. build 29 的 D1–D8 闭环复验与收尾（2026-09-13）

设备与产物：Studio（本机，automation-primary）+ Air（secondary），装同一个 **build 29**
（DMG SHA-256 `bfe7fb504f94afe5803493bf8be8d34b9e554b2c6d6d49cab0c3a44647e1de2b`，源码 `d2b07bd`，
`frontend_build = v2026.09.13-d2b07bd-888c2b62`——运行中进程的 `runtime.json` 与
`/Applications/SummitWorkbench.app/Contents/Resources/web/static/build-meta.json` 都可复核）。
用到两个一次性工作台：

- **Rehearsal**（`5ead7279-ddaa-43b5-a9c3-fda17b6b2566` / `~/Documents/Rehearsal` /
  远端 `SummitYifeng/summitworkbench-rehearsal`）——A6 冲突路径、D3/D6，以及 §N 第一轮恢复。
- **Rehearsal2**（`b10865d4-45c7-4328-9d2f-2d44bd65f28d` / `~/Documents/Rehearsal2` /
  远端 `SummitYifeng/summitworkbench-rehearsal-2`）——D1/D2/D5 的"全新工作台"路径。

> §N 记的是 build 28 的第一轮（`39611ca` + `1c06e43`）；本节是 build 29 的第二轮加 D1–D6 的逐条复核。

### O.1 逐条现场复核

| 缺陷 | 判据与证据 | 结果 |
|---|---|---|
| D1 | Rehearsal2 由向导「新建」产生（`workspace.json.created_at = 2026-09-13T01:07:15Z`，`min_reader/writer_version = 0.4.7`），`git reflog` 首条为 `7e1c275 HEAD@{01:07:15}: commit: wb: onboarding create`，`git rev-parse --abbrev-ref HEAD` = `main`（不是 dulwich 的默认 `master`）。随后设置页在**这个新仓库**上「预览 HTTPS 转换」成功（不再 `500 internal_error`）并落盘 `remote-normalization.json`（`status: applied`） | ✅ |
| D2 | 上一条转换在 **01:16:02Z** 把 `git_username = Yifeng93` 写进 profile；**同一个服务进程内** 01:16:25Z 的 `sync-state.json` 已经是 `state: ready`、`ahead/behind 0/0`、`last_sync_at = 01:16:25Z`（下一次启动是 01:17:26Z，所以这次成功同步发生在重启**之前**）。build 28 的同一动作必然 `error`，只有重启才好（见 §N D2 行） | ✅ |
| D3 | Phase 1–3 现场（Air 侧断网抓取）：横幅给出稳定原因码与中文短句、`detail` 非空，且不含 URL / 主机 / 路径原文 | ✅ 现场观察 |
| D5 | Rehearsal2 走完向导并进入工作台后，其 Application Support（现为 `SummitWorkbench.rehearsal2-bak`）里**没有** `onboarding-draft.json`；对照 build 28 时期建的 Rehearsal 目录，草稿仍残留 `step: "done"`、`work_root: "~/Documents/Rehearsal"`（未展开） | ✅ |
| D6 | ① 按钮确实在包里：`.../web/static/assets/*.js` 中 `btn-sync` 与「立即同步」各命中 1 处（build 29 的 bundle）。② 自动拉取：窗口在 01:29:23Z 被呈现（日志 `reopen_received` + `window_presented`），此后 `/api/sync/status` 的 `last_sync_at` 走到 **01:33:46Z**、`state: ready`、`ahead/behind 0/0`，而本机**没有任何写入** —— 可见时的空闲自动拉取按要求生效 | ✅ |
| D7/D8 | 现场撞到并被 D8 逼成有损选择（下一节）；修完只以测试收口。build 29 的 bundle 里 `RECOVERY_FAILURE_HINTS` **不存在**、「恢复准备未完成」**存在**，可直接复核"这两个修复还没出包" | ✅ 已修（未出包） |

### O.2 第二轮冲突恢复：D7/D8 的现场发现（代价：丢了一条捕捉）

1. Air 离线捕捉 `离线-A2` → 联网 push `f013de6`；Studio 同时捕捉 `离线-B2`（`d5630cd`）。
2. Studio 打开冲突详情后点「预检并写入」→ `conflict_snapshot_stale`（详情打开之后本地 revision 又变了，
   报错本身是对的）。
3. 重新打开详情、对 `inbox.md` 选「**保留双方副本**」→ **被拒**：`preserve_both_path_collision`（D8）。
   根因是 §N 第一轮恢复已经把远端副本落在 `inbox.md.remote`，而恢复不允许覆盖那份唯一副本；
   界面此时只说「恢复准备未完成。」（D7），没有任何可执行信息。
4. 改用「**保留本机**」→ `e049aaa`（**parents = 2**：本地 `d5630cd` + 远端 `f013de6`）+ 审计 `ed820ed`。
   `e049aaa` 的树与本地父 `d5630cd` **完全相同**（`git diff --stat d5630cd e049aaa` 为空），提交信息为
   `wb: sync recovery events=0 views=0 paths=0`。
5. **代价（单独记一笔）**：选「保留本机」意味着远端那条 `离线-A2` 不进工作树——
   `grep -rl 离线-A2`（排除 `.git`）在 Rehearsal 工作台里**找不到**；它只存在于第二父提交 `f013de6`
   （`git log --all -S 离线-A2` 只命中这一条）。也就是说：**D8 把用户从"无损的保留双方"逼到了
   "有损的保留本机"**，唯一的安全网是恢复提交的双父结构本身。这就是 D8 必须修的理由。
6. 修完后的预期行为（源码已改、单元/契约测试与变异验证已覆盖、**尚未出包**）：第二次点「保留双方副本」
   会落到 `inbox.md.remote.<rev7>`，两份内容都在工作树里。

### O.3 收尾收敛状态（2026-09-13T01:35Z）

| 检查 | 结果 |
|---|---|
| Studio 工作台 HEAD | `ed820ed`（`wb: sync recovery audit`） |
| `refs/remotes/origin/main` | `ed820ed` |
| 远端 `main`（`gh api repos/SummitYifeng/summitworkbench-rehearsal`，**远端权威**） | `ed820ed` |
| 工作树 / 状态 | clean，`ahead/behind 0/0`，`state: ready` |
| 最后一次同步 | 01:33:46Z（窗口可见时的自动拉取，未人工点击） |

## P. build 30 的真机复验：D8 通过、D7 对齐、新发现 D9（2026-09-13）

产物：**build 30**（`0.4.7` / arm64 / `INTERNAL-DEV`，源码 `b31c3ac`，
`frontend_build = v2026.09.13-b31c3ac-c7517c5a`，DMG SHA-256
`8a87044ba839ba2c291013a5b6d373b7834e9f1596259da9fa89fda0a131b645`，app SHA-256
`063bab4b569ef2a090de48ea33f70e8df6e508264de645535a87b84a4db552a1`）与
**build 31**（源码 `7bfe40b`，`frontend_build = v2026.09.13-7bfe40b-9517f794`，DMG SHA-256
`0cff5d1c5633d296515203894801beeedfc5183af0fbad25ac5fe211fad36b3c`，app SHA-256
`21be67b9ddd504f49cef8d050a3120949c750cc9f6946dbe166701893e72bf86`）。
装到 Studio 后，运行中进程的 `runtime.json` 与包内 `build-manifest.json` 的 `frontend_build` 一致；
包内 bundle 能搜到提示表文案 `改选「保留本机」或「采用远端」`，而 build 29 的 bundle 里
只有「恢复准备未完成」——"D7/D8 是否进了这个包"可以就地复核。

### P.1 D8 真机复验（**通过**）

在 Rehearsal 工作台重造一个**与现场同形**的分叉：本地 `wb: capture [d8-local-verify]`（`060f33e`）
对远端 `wb: capture [d8-remote-verify]`（`09aebd7`，共同 base `ed820ed`），而 vault 里本来就躺着
第一轮恢复留下的 `inbox.md.remote`（`13bfc790…`）——这正是现场把恢复整次拒掉的那个条件。

| 步骤 | 观察 |
|---|---|
| `POST /api/sync/run` | `state = diverged-protected`；`details`：base `ed820ed`、local `060f33e`、remote `09aebd7`、`manual_path_count = 1`（`inbox.md` 双侧都改） |
| 预检（`selections={"inbox.md":"preserve-both"}`，`confirmed=false`） | `preparation.status = validated`、`ok = true`、`candidate_path_count = 1`、**`error_code = null`** —— build 29 在这一步必然 `rejected` + `preserve_both_path_collision` |
| 写回（`confirmed=true`） | `recovery.status = committed`、`revision = 001df9a`、**`applied_paths = ["inbox.md.remote.09aebd7"]`**、`audit.status = committed` |
| 工作树 | 新增 `inbox.md.remote.09aebd7`（958 B，尾部是远端那条 `D8-远端验证`）；`inbox.md` 保留本机内容（`D8-本机验证`）；**第一轮的 `inbox.md.remote` 哈希仍是 `13bfc790…`，未被覆盖** |

**同一结论又在 UI 里独立复现了一次**（build 30，使用者亲自点的「保留双方副本」＋「确认恢复并创建提交」）：
审计行 `applied_paths: ["inbox.md.remote.ca88ebd"]`、`selections: {"inbox.md":"preserve-both"}`、
`status: committed`，恢复提交 `3c1a8f0` 双父 = `de99557`（本机）+ `ca88ebd`（远端），审计提交 `a597709`；
App 随后 `ready`、`ahead/behind 0/0`，远端 main = 本机 HEAD（**push 成功**——正好反证 §P.3 的 D9，
那次失败只来自客户端时间戳误判，不是远端拒绝）。

### P.2 D7 对齐（前端拿到的是带原因的错误码）

用与现场同形的"快照过期"请求打真实端点（前端的发法就是这样：它手里握着打开详情那一刻的
revision，之后本地又动过一次）：

```json
{"ok": false, "available": true, "state": "diverged-protected",
 "recovery": {"status": "stale", "error_code": "conflict_snapshot_stale"}}
```

build 29 的前端只读 `data.reason`（这个响应里不存在）⇒ 显示「恢复准备未完成。」；
build 30 的前端读 `preparation?.error_code ?? recovery?.error_code` ⇒ 命中提示表，显示
「远端或本机在上次读取之后又变了：请关掉本弹层、重新打开「查看冲突详情」再试。」
渲染本身由 `web/scripts/test-sync-render.mjs` 的断言 + 变异验证兜底。

### P.3 新发现 D9：恢复提交后的 push 被误判为非快进（**未修，待排期** → build 34 已修，见 §R）

真机复验里顺带撞到：`push_after_commit` 报告
`远端已有新提交，需要处理分叉（non-fast-forward）`，但这一对提交其实是**干净快进**。

| 判据 | 结果 |
|---|---|
| `dulwich.graph.can_fast_forward(repo, 09aebd7, f0a51bc)` | **False** |
| `can_fast_forward(repo, 09aebd7, 001df9a)`（直接子提交） | True |
| `git merge-base --is-ancestor 09aebd7 HEAD` | **YES**（图可达性：确实是快进） |
| `porcelain.push` | `DivergedBranches(b'09aebd7…', b'f0a51bc…')` → App 归类 `non-fast-forward` |
| 同一对提交用系统 git（走 127.0.0.1:7890 代理）推送 | **成功**：`09aebd7..f0a51bc` —— 远端接受这次快进 |
| 随后 `POST /api/sync/run` | `ready`，`ahead/behind 0/0` |

- **根因**：dulwich 的 `can_fast_forward` 用 `commit_time` 剪枝（`min_stamp`）找公共祖先，
  不是图可达性。本地恢复提交 `001df9a`（`01:47:21Z`）与审计 `f0a51bc`（`01:47:22Z`）都**早于**
  远端父 `09aebd7`（`01:50:00Z`），于是从 tip 出发的遍历把整条路径剪掉，LCA 找不到。
- **本次的触发条件是我人工造的**（远端提交时间被写晚），但形状在**两台机器时钟有偏差**时天然成立：
  对端"未来"的提交 + 本机按真实时间生成恢复提交 ⇒ 恢复成功、推送被拒、卡在 `diverged-protected`
  （重试恢复也一样，因为恢复提交依旧"更早"）。
- **修法方向**：`DulwichGitBackend.push` 捕获 `porcelain.DivergedBranches` 后，用不依赖时间戳的
  图可达性复核（从本地头沿 parents 走到远端 ref）；只有确认真快进时，才对该 ref 显式
  `force=True` 重推一次，并把"图复核通过"写进状态原因。不做无条件 force。

### P.4 D7 第一版只接了一条路径（真机复验当场发现，**已修** `7bfe40b`）

- **怎么发现的**：build 30 上按 §P.2 复现"快照过期"，弹层显示的却是**裸的
  `conflict_snapshot_stale`**，不是提示表里的人话——说明第一版（`fd19603`）没有覆盖到用户真正走的那条
  路径。事后核对：恢复失败有**三条**路径，第一版只接了第二条。
  1. `/api/sync/conflict/selection/validate` 返回 `{ok:false, selection:{error_code}}` 时**不带**
     `reason`，前端却是 `selection.reason ?? selection.error_code` ⇒ 直接把码当消息显示；
  2. `/api/sync/conflict/recover` 的预检分支（第一版已接）；
  3. apply 分支的 `恢复未提交：<code>`（同样只显示码）。
- **修法**：三条路径统一走 `recoveryFailureMessage(reason, code, fallback)`（`reason` 优先、未知码退化
  为「恢复准备未通过（<code>）：…」），弹层的「临时预检未通过 · 原因：」也显示同一句人话
  （错误码仍留在"复制诊断"里）。
- **回归锚点**：`web/scripts/test-sync-render.mjs` 为 selection 路径补了一个**真实响应形状**的 stub
  （`status: stale` + 无 `reason`）与断言（必须出现「远端或本机在上次读取之后又变了」、必须**不**出现
  `conflict_snapshot_stale` 与「人工选择未通过校验」）。**变异验证**：把这条分支改回裸码形态，渲染结果
  立刻变回 `<div class="msg err">conflict_snapshot_stale</div>`——与真机所见逐字一致。
- **build 31 真机复验（通过）**：装 build 31 后在仍打开的弹层里制造快照过期，使用者看到的是
  「**远端或本机在上次读取之后又变了：请关掉本弹层、重新打开「查看冲突详情」再试。**」
  ——不再是 build 30 上那个裸码。
- **教训**：同一个错误码会在多条路径上露出；只修"我看到的这一条"等于没修。真机复验的价值正在这里：
  单元/契约测试当时是绿的（它们只覆盖了 `recover` 那条），是**人眼在弹层里看到了裸码**才把它揪出来。

### P.4b 日常使用包：build 32（补回内置飞书凭据）

`build 27–31` 都是不带内置飞书凭据的测试包（构建时未导出 `WB_FEISHU_APP_ID` /
`WB_FEISHU_APP_SECRET`），而 `~/.config/summitworkbench/config.toml` 也不存在 ⇒ 复原机器后
**飞书会因拿不到 app_secret 而失败**。既然 Phase 6 要让 Studio 回到日常使用，就用 build 25 包里
那份凭据（`dist/releases-local-v0.4.7-b25/.../Resources/feishu-defaults.json`，仅经环境变量传给
构建脚本，不落仓库、不打印）重打了 **build 32**：

| 项 | 值 |
|---|---|
| 源码 / 前端 | `1bd8572` / `v2026.09.13-1bd8572-9517f794` |
| DMG SHA-256 | `15a57239cc8836d61031f72f6305da43ab43ad62a5b54c761e857f65e2920df5` |
| app SHA-256 | `be11eccb717a757b9921a0380687aa8817e669f6dd1916768293df8533283e64` |
| 内置凭据 | `app_id = cli_aa1e751a…`、`redirect_uri = http://localhost:8765/callback`、secret 就位（与 build 25 同源） |

### P.5 收尾状态（2026-09-13T02:09Z）

第三轮验证完成后由接口收敛（`preserve-both`）：恢复提交 `5675da4`、审计 `18227e8`、
`applied_paths = ["inbox.md.remote.e25dceb"]`、`push.ok = true`；App `state = ready`、`ahead/behind 0/0`、
工作树 clean、HEAD = `origin/main`。工作台里同时留着五份可辨认的文件：
`inbox.md`（本机）+ 四个远端兄弟副本 `inbox.md.remote`（第一轮）、`.remote.09aebd7`、
`.remote.ca88ebd`、`.remote.e25dceb` ——**没有任何一次「保留双方」覆盖过别人**。

## Q. Phase 6 复原 Studio 时发现的问题（2026-09-13）

复原本机（清空 Application Support → 向导「连接已有工作台」→ 指回 `~/Documents/Work/_vault`）时又撞到两条。

### Q.1 D10 · 「连接已有工作台」把设备角色一律写成 secondary（**已定界，未修** → build 34 已修，见 §R）

- **现象**：`_vault` 的 `.summit-workbench/automation-primary.json` 里 `device_id` 正是本机
  （`51885d3d-…`，generation 1），但向导走完后 profile 的 `device_role = "secondary"`。
- **证据链**：`workflows/onboarding.py::connect_workspace()` **没有** `device_role` 形参，
  落到 `_ensure_profile(..., DeviceRole.SECONDARY)` 默认值；对照 `create_workspace()` /
  `upgrade_workspace()` 都收 `device_role` 并在为 primary 时顺带
  `claim_automation_primary()`。全仓**没有任何**更新既有 profile `device_role` 的入口
  （`grep -rn "device_role" src/` 只有 onboarding 写入点与读取点），界面也没有 claim 入口（§N 的 G1）。
- **后果不是显示问题**：`workflows/sync_coordinator.py::automation_gate()` 只在
  `profile.device_role is DeviceRole.AUTOMATION_PRIMARY` 且 claim 设备匹配时返回
  `PRIMARY_OK` ⇒ **定时自动化（简报等 writer）在这台机器上不会跑**，而这台机器正是共享
  marker 指定的主设备。用户按界面操作无法自救。
- **本次的处置（绕行）**：用 App 自己的写入器改 profile（不是手改文本）——
  `load_profile()` → `model_copy(update={"device_role": DeviceRole.AUTOMATION_PRIMARY})` →
  `save_profile()`（`[feishu]` / `[models]` 段原样保留），重启后核验：
  `profile.device_role = automation-primary`、`automation_gate(require_claim=True) = primary-ok`、
  `/api/sync/status` 的 `automation_primary_device_id` 正是本机。
- **修法方向**：connect 流程读 marker——`marker.device_id == 本机 device_id` ⇒ 直接建为
  `automation-primary`（并在 profile 里记下 claim）；否则 secondary。配套把 §N 的 G1（界面无
  claim 入口）一起补上，让角色可改、可解释。

### Q.2 D11 · 已 typed 的远端错误被文本兜底重新分类（**已修** `f560d2e`）

- **现象**：转换 HTTPS/写凭据之前，`/api/sync/status` 给的是
  `"_vault：未分类的同步失败（unclassified）"`，而真实原因是**本机缺 workspace 级 Git 凭据**
  ——正是 D3 想让界面说清楚的那一类。
- **根因（可复现）**：`fetch()`/`push()` 在 `try` 里调用 `transport_kwargs()`，后者抛
  `GitCredentialsUnavailable`；该异常被同一个 `except Exception` 接住并送进
  `_classify_remote()`，而它**只按异常文本匹配**、不检查"是不是已经是我们自己的稳定类型"，
  于是落进兜底 `GitBackendRuntimeError` ⇒ `repo_error_reason()` = `unclassified`。
  复现：`GitRepo(vault, workspace_id=<不存在的 workspace>, username=…)` → `fetch()` →
  `GitBackendRuntimeError` / 原因码 `unclassified`（修好后为 `GitCredentialsUnavailable` /
  `credentials-missing`）。
- **真机复核**：修好后在 `_vault` 上用不存在的 workspace id 复现同一路径 →
  异常类型 `GitCredentialsUnavailable`、原因码 `credentials-missing`、状态 `auth-required`
  （修前是 `GitBackendRuntimeError` / `unclassified` / 裸 `error`）。
- **修法**：`_classify_remote()` 开头 `if isinstance(exc, GitError): return exc`。两个新测试 +
  变异验证（去掉守卫即失败）：typed 错误原样返回且原因码为 `credentials-missing` /
  `AUTH_REQUIRED`；注入会抛 `GitCredentialsUnavailable` 的 resolver 后 `fetch()` 仍是
  `credentials-missing`。
- **同源观察（未修，不是阻塞）**：`_vault` 的 `[remote "origin"]` 有**三条 `url`**
  （SSH 在前 + 两条 HTTPS）。dulwich 的 `config.get(("remote","origin"), "url")` 取**最后**一条
  ⇒ App 认为"已是 HTTPS"，`预览 HTTPS 转换` 因此报 `old_url == new_url` 而不修；而系统
  `git remote -v` 的 fetch 走**第一条**（SSH）。两边各自能用，但"转换成功却什么都没改"这件事
  会误导排查。修法方向：规范化时把多值 `url` 一并处理（或明确拒绝多值并要求先清理），
  并在预览里回报"读到的是哪一条"。

### Q.3 复原后的验收状态（Studio）

| 检查 | 结果 |
|---|---|
| active workspace | `bf22c8d2-ef62-4bd3-9917-e76fdd3f7f0f`（`_vault`），`work_root = ~/Documents/Work` |
| device / 角色 | `51885d3d-…`（与 marker 一致）/ `automation-primary`（Q.1 修正后），`automation_gate = primary-ok` |
| 同步 | `state = ready`、`ahead/behind 0/0`、`remote_host = github.com`、`last_sync_at` 有值 |
| 凭据 | profile `git_username = Yifeng93`、`git_remote_url = https://…/YifengWorkKnowledge.git`；Keychain 有 `git:github.com:Yifeng93` |
| 工作树 | clean、`main`、与 `origin/main` 同步 |
| 模型 / 飞书 | profile `[models.shared]` = deepseek-v4-flash；`[feishu]` app_id/redirect/scopes 就位（build 32/33 内置 app_secret） |
| 日常使用包 | **build 33**（`989ce9c`，`frontend_build = v2026.09.13-989ce9c-9517f794`，DMG SHA-256 `29e3ae3d8b5aeb952200144432bb313e83e11b72be8036f7c9f82afc4cd32a6a`），含 D11 修复与内置飞书凭据；`/Applications` 已是它 |
| `acceptance-preflight`（App 自带 11 项） | **全部 PASS**：app/build 33、production backend=dulwich、`remote-scheme: https://github.com`、`credentials: workspace-scoped Keychain configured`、`fetch: HTTPS fetch completed`、`branch/upstream main a0/b0`、`schema-path → 2`、**`automation-role: automation-primary`**（Q.1 修正已在 App 视角生效） |

### Q.4 Air 按"新设备"重建（secondary，2026-09-13T02:46Z）

Air 的真实 profile 在演练期间已丢失（`SummitWorkbench.real-bak` 根本不存在 ⇒ 当初那条 `mv` 失败，
App 找不到档案就停在向导）；本机 vault 只剩一个空的 `_vault/` 和 9月7 一次未走完的暂存克隆
`.summit-workbench-remote-bd5fjceu/`。经确认"Air 上没有任何重要文档"后，改成**按新设备重来**：

1. 清空 Air 的 `Application Support/SummitWorkbench*`、`~/Documents/Work/{_vault,.summit-workbench-remote-*,.wb.lock}`、
   `~/Documents/Rehearsal`（演练 vault）；
2. 向导「**从另一台 Mac 克隆**」→ `https://github.com/yifeng93/YifengWorkKnowledge.git` +
   目标 `~/Documents/Work/_vault`（先确认不存在）+ 用户名 `Yifeng93` + PAT → 暂存核对 marker
   （`bf22c8d2…`、兼容性 OK）→ 确认；
3. 模型沿用 workspace Keychain 的 `llm:shared:shared`，飞书用 build 33 内置 app_secret。

**核验结果（Air 实测）**：

| 检查 | 结果 |
|---|---|
| active workspace / 角色 | `bf22c8d2-ef62-4bd3-9917-e76fdd3f7f0f` / `device_role = "secondary"`（marker 里的主设备仍是 Studio `51885d3d-…`） |
| 同步 | `state = ready`、`ahead/behind 0/0`、`_vault:ready`、`last_sync_at = 02:46:56Z` |
| 仓库 | HEAD `86cc529 wb: brief 2026-09-12` = `origin/main` = `origin/HEAD`，工作树 clean —— **与 Studio 同 HEAD** |
| 凭据 | workspace Keychain：`git:github.com:Yifeng93`（克隆流程新写入）、`llm:shared:shared`、`feishu:…:refresh_token`（外加旧的小写 `git:github.com:yifeng93`，无害） |
| 包 / 设备 | build 33（`v2026.09.13-989ce9c-9517f794`）；**新 device id `e1b8b735-…`**（≠ Studio `51885d3d-…`），`device_name = YifengAirdeMacBook-Air.local` |
| 残留 | `~/Documents/Work/` 只剩 `_vault`（+ App 正常的 `.wb.lock`）；`Rehearsal` 已清；档案目录只剩 `SummitWorkbench` |

### Q.5 Phase 6 收尾（Studio）

> 当时的保留项（`b25`/`b33`、两个演练仓库）已在 build 34 本轮清理中处理，见 §R.4 / §R.6。

- 保留：`dist/releases-local-v0.4.7-b25/`（内置飞书凭据的原始出处）、`b33/`（当前日常包）；
  两个演练仓库 `SummitYifeng/summitworkbench-rehearsal{,-2}` 按使用者要求暂留。
- 清除：`~/Documents/Rehearsal{,_2}`、`SummitWorkbench.rehearsal-final-bak`、
  `SummitWorkbench.rehearsal2-bak`、`dist/releases-local-v0.4.7-b26…b32`、
  `/Applications/SummitWorkbench.app.previous`、`/tmp` 里的 PAT/会话令牌副本。
- 日常使用包：**build 33**；两台机器分别在 `automation-primary`（Studio）/ `secondary`（Air）角色上运行。

### Q.6 真实双机往返冒烟（2026-09-13T02:50Z，**通过**）

复原完成后在**真实 vault**上做了一次日常用法验证：

1. Air（secondary）输出一条捕捉 `测试`；
2. Studio（automation-primary）点顶部栏「**⇅ 立即同步**」（D6 新增的按钮）。

| 检查 | 结果 |
|---|---|
| 新提交 | `448869b wb: capture [0fb8ca0c-9df4-413e-90a5-23f35ac3f1c2]`，只改 `inbox.md`（+4 行），author `_vault <wb@local>` |
| Studio 落盘内容 | `inbox.md`：`- [ ] 测试` + `<!-- wb-candidate: web-20260913024918465238 -->` + `<!-- wb-capture-kind: idea -->`（候选 id 的时间戳 = Air 本地捕捉时刻） |
| 收敛 | Studio `HEAD = origin/main = 448869b`、工作树 clean、`state = ready`、`ahead/behind 0/0`、`last_sync_at = 02:50:09Z` |
| 路径性质 | **快进**（无冲突、无保护态）——正是 D6 想消灭的"对端推过、本机只能干等/下次写入必然分叉"场景 |

这条同时验证了：Air 的克隆凭据可用、两台共用一个 workspace、D6 的「立即同步」在真实工作台上按预期拉取、
以及同步后内容一致。**多设备同步收官。**

## R. build 34 交付与仓库清理（2026-09-13）

按 `docs/implementation/HANDOFF-NEXT-DELIVERY-AND-CLEANUP.md` 执行（该文档已归档到
`docs/archive/plans/HANDOFF-NEXT-DELIVERY-AND-CLEANUP.md`）。使用者通过选择题对齐的范围：
**D9 + D10 + G1 + G2（中等：绑定已有远端并首次推送）+ G3（独立服务日志）**，并做
**①磁盘产物 + ②过期文档归档 + ③删死代码**的清理；交付包内置飞书凭据、装 Studio，
Air 由使用者 AirDrop，**本轮不再跑双机往返冒烟**。

本轮提交（全部 `[skip ci]`）：

| 提交 | 内容 |
|---|---|
| `ce34c12` | D9：图可达性复核 + 单 refspec 强推 |
| `5ce07cc` | D10：connect/clone 按主设备声明决定角色 |
| `398e717` | G1：接管/降级入口（后端 + 设置页） |
| `fb08798` | G2：首次发布到空远端 |
| `36ebffd` | G3：独立服务日志 |
| `d4f43f8` | 指南/PROJECTDESC 同步 |
| `8b7767d` | 前端构建产物（`frontend_build = v2026.09.13-8b7767d-ae564ff2`） |
| `1ff1f5b` | 清理：文档归档 + 三处死代码 |

### R.1 交付包 build 34

| 项 | 值 |
|---|---|
| 版本 / build / 架构 / 分发 | `0.4.7` / **34** / `arm64` / `INTERNAL-DEV` |
| 源码提交 | `8b7767dcbb7268994ef2a6d1639d0fc9e130e7c8` |
| `frontend_build` | `v2026.09.13-8b7767d-ae564ff2` |
| DMG | `dist/releases-local-v0.4.7-b34/0.4.7/arm64/SummitWorkbench-0.4.7-arm64-INTERNAL-DEV.dmg`（50 306 094 B） |
| DMG SHA-256 | `3ca3aae74577264e2c106e81599bb32d272eddf80725c29264c8cb7a8a4fa73d` |
| `.app` SHA-256 | `fd702441093ba670837a0e26e6dbeffae47461c61a6413b626854be38066a829` |
| 内置飞书凭据 | **有**（`Contents/Resources/feishu-defaults.json`，构建时经 `WB_FEISHU_*` 环境变量从 b25 传入；结构校验 `✓ 内置飞书凭据结构正确`） |
| 出包命令 | `REQUIRE_BUNDLED_FEISHU=true BUILD_NUMBER=34 ARCH=arm64 RELEASE_OUTPUT_DIR=dist/releases-local-v0.4.7-b34 scripts/release-macos.sh`（退出码 0） |
| 附产物 | `release-metadata.json`、`SBOM.json`、`SHA256SUMS`、`test-manifest.json`、`notary-log.json` |

### R.2 Studio 真机核验（build 34，2026-09-13T03:20Z）

安装：`osascript -e 'quit app "SummitWorkbench"'` → `scripts/install-macos-app.sh dist/…/SummitWorkbench.app`。
安装脚本**再次**打印 `✗ App 已安装但服务未在 readiness 窗口内启动`（已知假失败），按配方以
`runtime.json` + 接口探针为准，实际服务正常。

| 检查 | 证据 |
|---|---|
| `runtime.json` | `workspace_id=bf22c8d2-ef62-4bd3-9917-e76fdd3f7f0f`、`device_id=51885d3d-6f75-49ca-8896-9f46288474e8`、`frontend_build=v2026.09.13-8b7767d-ae564ff2`、`pid=71210`、`port=56495`、`server_instance=4a97c25f-…`、`started_at=2026-09-13T03:20:38Z` |
| `GET /api/sync/status` | `state=ready`、`ahead=0`、`behind=0`、`pending_commits=0`、`branch=main`、`remote_host=github.com`、`repo_states=["_vault:ready"]`、`automation_primary_device_id=51885d3d-…`、`automation_primary_generation=1` |
| `POST /api/settings/acceptance-preflight` | **11/11 PASS**：`app/build`（`build=34`、`frontend_build=v2026.09.13-8b7767d-ae564ff2`、`git_revision=8b7767d`、`production backend=dulwich`）、`production-backend`、`remote-scheme`（`https://github.com`）、`credentials`、`dirty-consistency`、`fetch`、`branch/upstream`（`ahead=0;behind=0`）、`ahead-behind`、`schema-path`、`backup-writable`、`automation-role=automation-primary` |
| `POST /api/sync/run` | `ok=true`、`state=ready`、`_vault:ready`（走真实 HTTPS 远端 fetch→ff→push 路径） |
| 真实 vault | 工作树 `clean`，`HEAD=448869b wb: capture […]` |
| 新路由存在 | `POST /api/sync/primary/downgrade`、`POST /api/settings/git/remote/publish` 用 GET 探针得 **405**（存在、方法不符），证明新端点已随包上线 |
| G1 冲突路径（真机） | `POST /api/sync/primary/claim {device_id:"00000000-0000-4000-8000-000000000000", takeover:false}` ⇒ **409 `primary_already_claimed`**；`automation-primary.json` SHA-256 **前后不变**，vault 仍 clean（证明"别的设备不 takeover 绝不抢占"） |
| G2 错误面（真机） | `POST /api/settings/git/remote/publish {candidate_url:"git@github.com:owner/repo.git", pat:"probe-…"}` ⇒ **409 `remote_scheme_unsupported`**，无副作用（证明只接受 HTTPS、且拒绝发生在写 Keychain/远端之前） |
| G3 服务日志（真机） | `~/Library/Logs/summitworkbench-server.log` 存在、`-rw-------`（**0600**）、284 B，首行 `{"component":"server","event":"server_started","app_version":"0.4.7","frontend_build":"v2026.09.13-8b7767d-ae564ff2","has_workspace":true}`，无 URL/路径/凭据 |
| 包内确实带上了新界面 | 对已安装包的 `Contents/Resources/web/static/assets/index-*.js` 逐字 grep：`primary-claim`、`primary-downgrade`、`primary-takeover-ack`、`git-remote-publish`、`定时自动化主设备`、`接管主设备`、`降级为备用设备`、`首次发布到远端`、`昨晚为什么没自动同步`、`summitworkbench-server.log` **全部 PRESENT**（证明 G1/G2 界面与更新后的指南真的进了交付包） |

**Air 侧**：使用者随后在**全新 Air** 上从零配置了同一个 build 34 并完成真机双机冒烟，
证据见 **§R.7**（两台 `frontend_build` 一致）。

### R.3 五项交付的测试与变异验证

| 项 | 行为测试 | 变异验证（去掉修复必须让测试失败） |
|---|---|---|
| **D9** | `tests/unit/test_git_backends.py::test_push_succeeds_when_remote_parent_committer_time_is_newer`（两跳时钟偏差，**前置断言** `can_fast_forward(base, head) is False` 确认落在 dulwich 坏区，再断言 push 成功、远端 ref 前进、`ahead/behind=0/0`）；`::test_push_rejects_true_divergence_even_when_graph_check_runs`（真分叉仍是 `GitNonFastForward` 且远端不动） | 去掉 `_push_confirmed_fast_forward` 调用 ⇒ 前者 `GitNonFastForward` 失败；`_is_ancestor` 恒 `True` ⇒ 后者 DID-NOT-RAISE 失败（远端会被覆盖） |
| **D10** | `test_onboarding.py` 三例（marker 指本机⇒`AUTOMATION_PRIMARY` 且 `automation_gate=PRIMARY_OK`；指别设备⇒`SECONDARY`、声明与 generation 不变、无 takeover 的 claim 得 `primary_already_claimed`；无 marker⇒`SECONDARY` 且不新造声明）；`test_remote_onboarding.py` 两例（clone 确认后角色按声明） | 恒 `SECONDARY` ⇒ 两个"本机变 primary"用例失败；恒 `AUTOMATION_PRIMARY` ⇒ 三个 secondary/无声明用例失败 |
| **G1** | `tests/unit/test_primary_role_api.py` 四例（claim 同步 profile 角色并在响应回传；别设备不改本机角色 + `primary_already_claimed` + generation 冲突；downgrade 只改本机 profile、声明不变、幂等；无 active workspace ⇒ `workspace_not_configured`）；前端 `test-settings-render.mjs`（三种状态渲染、未勾选不发请求、请求体含 `expected_generation`、POST+JSON 头）与 `test-browser-contract.mjs`（入口 + 派发分支锚点） | 去掉 `_sync_local_role` ⇒ 角色用例失败；downgrade 顺带删声明 ⇒ 声明不变用例失败；去掉 `data-generation`/勾选框 ⇒ 前端渲染用例失败；动作不校验勾选 ⇒ 未勾选用例失败 |
| **G2** | `tests/unit/test_remote_publish.py` 六例（成功路径断言"预检真推过一次 + 真 vault 只推一次 + upstream 写入 + PAT 不在任何落盘文件里"；非空远端零副作用；非 HTTPS；已有 origin；dirty/unborn；push 失败回滚 origin/profile/凭据）；`test_remote_publish_api.py` 两例（端点契约与稳定码）；`test_git_backends.py` 新增两后端 `add_remote`/`set_upstream`/`remove_remote` 一致性；前端渲染 + 请求体 + 契约锚点 | 去掉空远端校验 ⇒ 非空用例失败；去掉回滚 ⇒ 回滚用例失败；绕过 HTTPS 校验 ⇒ 6 例失败；前端隐藏区块/清空请求体/删派发分支 ⇒ 对应用例失败 |
| **G3** | `tests/unit/test_server_log.py` 六例（路径 + **0600**；幂等＝同实例 + 单文件；400 B 上限轮转出 `.1`；**含 URL + 凭据 + 用户路径的假异常跑一遍后断言日志文本里没有它们**、而稳定码/类名保留；原因码白名单；真跑一次失败同步后留下 `remote-scheme-unsupported`） | 不做白名单 ⇒ 泄密用例失败；不轮转 ⇒ 轮转用例失败；不接线 `log_sync_outcome` ⇒ 失败同步用例失败；改 0644 ⇒ 权限用例失败 |

> D9 的**真机现场证据**仍是 §P.3（build 30 的 `can_fast_forward=False` / `merge-base=YES` /
> 系统 git 推送成功）；本轮修复的验证方式是"在单测里精确复现同一坏区（两跳、时钟倒挂）+
> 变异验证"。真 vault 本轮不处于该状态，因此没有再造一次真机分叉。

### R.4 清理（等价、不改行为）

**① 磁盘产物与缓存**（全部在 `.gitignore` 内，仓库内容零变化；`git status` 清理前后均 clean）：

- 删除 `dist/` 下 14 个 `releases-local-v0.4.4*`、`releases-local-v0.4.7-b25`（凭据已先留档到
  仓库外）、`releases-local-v0.4.7-b33`、`SummitWorkbench-0.4.6-arm64-INTERNAL-DEV.dmg`；
- 删除 `.coverage`、`htmlcov/`、`.mypy_cache/`、`.pytest_cache/`、`.ruff_cache/`、`.hypothesis/`、
  各处 `__pycache__/`、仓库内 `.DS_Store`；
- 结果：仓库 **2.0 GB → 346 MB**，`dist/` 只剩 build 34（115 MB）。

**② 过期文档归档**（证据：对 `docs/` 下每个非归档文档统计全仓入引用，含 CHANGELOG/README/
PROJECTDESC/ADR/tests/scripts）：

- 唯一"零入引用且已被完全取代"的是**已执行完毕的本轮交接文档**，移到
  `docs/archive/plans/` 并在原路径留一行指针；`docs/archive/README.md` 的 `plans/` 条目同步说明。
- 其余（`LEGACY-APP-SPLIT-PLAN.md`、`LEGACY-MAIN-SPLIT-PLAN.md`、`DELIVERY-CLEANUP-HANDOFF.md`、
  `DELIVERY-CLEANUP-REPORT.md`、`V0-4-4-UX-UI-*.md`、`UI-VERIFICATION-*`、
  `V0-4-4-LOCAL-RELEASE-ACCEPTANCE.md`、`DUAL-DEVICE-REHEARSAL.md`）都有至少一条入引用，
  按铁律**一律不动**（尤其是 `LEGACY-MAIN-SPLIT-PLAN.md` 被 CHANGELOG 与三个测试的注释引用）。
- 本轮**未**拆 `CHANGELOG.md`（对齐时该选项未被选中）。

**③ 冗余代码**（vulture 2.16 经 `uvx` 临时运行，**未加入 `pyproject.toml` 依赖**）：

- `src+tests+scripts --min-confidence 80` 命中 4 条，逐条 `grep -rn`（含 tests/scripts/docs/native/web）
  后删除 3 处：`webapp/legacy_app.py` 不可达的重复 `return app`、
  `webapp/feishu_pool.py::_FeishuClientPool.tenant_client`（全仓仅定义处出现，capture/review_apply
  只用 `user_client`，无 getattr/反射调用）、`tests/contract/test_llm_client.py` 未使用的 `capfd` 形参。
- 保留的假阳性：`config/settings.py` 的 `dotenv_settings` / `file_secret_settings` 是
  pydantic-settings `settings_customise_sources` 的形参，且上游是**按关键字**调用
  （`main.py:442`），改名或删除会直接让配置加载 TypeError；`cli/*` 命令函数、
  `webapp/request_boundary.py` / `app_shell.py` 的嵌套 handler、`domain/*` 的 pydantic validator
  都是装饰器/反射注册，vulture 看不到调用点。
- 前端另查：`web/src/**/index.ts` 的再导出零未使用符号；`tsc` 已开 `noUnusedLocals` /
  `noUnusedParameters`，无新增死代码。
- 清理后门禁全绿 + 打包冒烟通过（见下）。

### R.5 本轮门禁（源码提交后、构建提交前 + 清理后各跑一次）

```
tsc --noEmit -p web/tsconfig.json                         OK
npm --prefix web run test:frontend（14 个脚本）             OK
.venv/bin/python -m pytest --cov -q                        971 passed / 1 skipped，覆盖率 83.54%
ruff check / ruff format --check                           OK（435 files）
mypy                                                        Success: no issues found in 340 source files
python scripts/secret_scan.py                              passed
node web/scripts/verify-build.mjs …                        Build verified: v2026.09.13-d4f43f8-ae564ff2
WB_PACKAGED_APP=/Applications/SummitWorkbench.app \
  pytest tests/integration/test_packaged_app.py -q          1 passed（清理后复跑）
```

远端 CI 见 §R.9（本轮提交全部带 `[skip ci]`，收尾时经使用者同意手动触发一次，对当前 HEAD 全绿）。

### R.7 全新 Air 从零配置 + 真机双机冒烟（2026-09-13T03:34–03:41Z，**通过**）

使用者按"完全清空 → 从第一步配置 → 同步好后做最小冒烟"的方案执行（比对齐时的最小选项更强）。

**Air 侧：从零配置 build 34（全部通过）**

| 检查 | 证据（Air 上采集） |
|---|---|
| 包身份 | `runtime.json.frontend_build = v2026.09.13-8b7767d-ae564ff2`、`api_protocol=2`，与 Studio **完全一致** |
| 同一工作台 | `workspace_id = bf22c8d2-ef62-4bd3-9917-e76fdd3f7f0f`（与 Studio 相同） |
| **角色（D10 真机）** | `profiles/<ws>/config.toml` 的 `device_role = "secondary"`——全新 profile 由克隆流程按 vault 内 marker（指向 Studio）自动判定，**没有抢占** |
| 远端 | `git_remote_url = https://github.com/yifeng93/YifengWorkKnowledge.git`（HTTPS，`require_https_remote` 通过） |
| 克隆前置 | 目标 `~/Documents/Work/_vault` 确实不存在（向导的 `target_exists` / `target_parent_missing` 两道门都过） |
| 向导与预检 | 向导三步（克隆 → 模型 → 飞书，飞书用**包内内置凭据**、本机零预置）全部通过；使用者另跑「预览 HTTPS 转换」成功 |
| **服务日志（G3 真机）** | `~/Library/Logs/summitworkbench-server.log`：`-rw-------`（**0600**）、568 B、**两行 `server_started`、零 `sync_failed`**（首次配置全程没有同步失败）；两行 `app_version=0.4.7`、`frontend_build` 与包一致 |

**真机双机冒烟（真实 vault，两条腿都被覆盖）**

| 检查 | 结果 |
|---|---|
| Air 写 → 远端 | Air 捕捉「测试」：提交 `598a285 wb: capture [b8a7633e-0309-4638-9624-f50982be9fa2]`，作者 `_vault <wb@local>`，**只改 `inbox.md`（+4 行）**，候选标记 `web-20260913033919077798`（时间戳 = Air 本地 03:39:19Z） |
| Studio 拉（自动） | Studio 每分钟自动拉取已生效：`last_sync_at = 03:40:32Z`，HEAD 自动前进到 `598a285` |
| Studio 拉（手动复核） | `POST /api/sync/run` ⇒ `ok=true`、`state=ready`、`_vault:ready` |
| 收敛 | `HEAD == origin/main == 598a285`、`ahead/behind 0/0`、`pending_commits 0`、`detail` 空、vault 工作树 **0** 变更 |
| 路径性质 | 线性快进（新提交的父就是上一轮冒烟的 `448869b`）——**无冲突、无保护态** |
| **未抢占（D10/G1 真机）** | Studio 的 `automation_primary_device_id` 事后仍为自己 `51885d3d-…`、`generation` 仍为 **1** |
| **G3（Studio 真机）** | Studio 服务日志在整轮冒烟后**仍只有 1 行 `server_started`、零 `sync_failed`**（干净同步不写日志，符合设计：只有失败/降级才落盘） |
| 版本一致性 | 两台 `frontend_build` 均为 `v2026.09.13-8b7767d-ae564ff2` |

**这次真机额外证明了什么**

- 分发版承诺（**内置飞书凭据、零预置一键授权**）在一台从零开始的机器上成立；
- **D10 的否定分支**在真机上成立：marker 指向别的设备 ⇒ 全新 profile 落成 `secondary`，
  且主设备归属与 generation 不被改写；
- **G3** 在两台机器上都按设计工作（正常路径安静、失败才落盘）；
- 两台机器的 HTTPS 克隆、upstream、ahead/behind、自动拉取与推送全部走通。

**诚实边界（不夸大）**

- Air 的 `device_id = e1b8b735-2b31-4ae2-9bf1-1dafa9261b76`，与本文件上一轮记录的 Air 设备 id
  **相同**⇒ 这次"清空"清掉的是工作台/本机配置，`device.json` 的设备身份仍在。因此
  **D10 的肯定分支**（marker 指本机 ⇒ `AUTOMATION_PRIMARY`）在这次真机上**没有**被区分验证，
  它目前仍只有 §R.3 的单测 + 变异验证；要真机钉死需要做一次 G1 接管（见 §R.6.7）。
- Air 侧 `/api/sync/status` 与 `acceptance-preflight` 的 curl 输出未采集到（粘贴时 URL 末尾
  多了一个被转义的 `;` ⇒ `/api/sync/status;` ⇒ `{"detail":"Not Found"}`，是粘贴问题而非 App 问题）；
  Air 侧"预检通过"为使用者口头确认，**机器可核验的 Air 侧证据**是本表上半部分的
  `runtime.json` / `config.toml` / 服务日志三项。

### R.8 G1 接管/降级 + 自动化门控的真机闭环（2026-09-13T07:42–07:50Z，**通过**）

承接 §R.7（Air 已作为 `secondary` 接好）。本轮把 G1 的**点击路径**在真机上走完：
Air 接管 → 门控关闭 → 过期 generation 被拒 → 归还 Studio → Air 降级 → 门控再确认。
两台机器：Air `e1b8b735-2b31-4ae2-9bf1-1dafa9261b76`、Studio `51885d3d-6f75-49ca-8896-9f46288474e8`；
归属 generation 走 **1 → 2 → 3**。**全程在 App 界面点击**（无终端探针参与用户侧操作）。

#### 步骤与证据

| # | 操作 | 期望 | 实际 |
|---|---|---|---|
| 1 | **Air** 打开「设置 → 高级与维护 → 定时自动化主设备」 | 本机 device id = Air、当前主设备 = Studio · generation 1、本机角色 = 备用设备、只有「勾选确认 + 接管主设备」（**无**降级按钮） | 角色行由 §R.7 的 `device_role = "secondary"` 支持；**卡片的按钮形态未逐条回报** |
| 2 | **Air** 不勾选直接点「接管主设备」 | 拒绝且什么都不改 | **未逐条回报**（代理侧无此步证据；"未勾选不发请求"另有 §R.3 的前端单测覆盖） |
| 3 | **Air** 勾选 →「接管主设备」→ 系统二次确认 | generation → 2、角色翻转为主设备 | 使用者逐字回报：当前主设备 = `e1b8b735-… · generation **2**`、本机角色 = **主设备（定时自动化在本机运行）**（按钮形态未回报） |
| 4 | **Studio** 同步归属 | Studio 视角看到归属已属 Air | `automation_primary_device_id = e1b8b735-…`、`automation_primary_generation = 2`、`state=ready`；归属提交 `8325639 wb: sync/primary` 由 Air push、Studio 拉取（`HEAD == origin/main`） |
| 5 | **Studio 门控探针 A**（设置页「立即运行」的同一路径：`POST /api/settings/automation/run {job:brief}`） | 非主设备 ⇒ 跳过 | `status="not-primary"`、`detail="本机不是该 workspace 的主设备"` |
| 6 | **Studio 门控探针 B**（`POST /api/run/brief`） | 非主设备 ⇒ 跳过 | `skipped=true`、`code="not_automation_primary"` |
| 7 | **零写入核对**（探针 5/6 之后） | 声明与工作树都不变 | 声明 SHA-256 **前后一致**（`2cae47c8…`）、vault 工作树 **0** 变更 |
| 8 | **Studio** 用**过期** generation 接管（`takeover=true, expected_generation=1`） | 被拒且不写入 | **409 `primary_generation_conflict`**（`takeover 必须基于当前 generation`），声明哈希仍未变 |
| 9 | **Studio** 用当前 generation 接管（`expected_generation=2`） | generation → 3、主设备回 Studio | **200**、`generation=3`、`device_id=51885d3d-…`、`device_role="automation-primary"`、`commit.status="committed"`；提交 `44a2d17 wb: sync/primary` 已 push |
| 10 | **Air** 同步后看卡片 | 当前主设备 = Studio · generation 3 | 使用者逐字回报：当前主设备 = `51885d3d-… · generation **3**`（同步生效） |
| 11 | **Air** 点「降级为备用设备」 | 本机角色回 secondary | 使用者逐字回报：本机角色 = **备用设备**（降级已执行，Air 本机档案与声明归属对齐） |
| 12 | **Air** 点「晨间简报 → 立即运行」（此时已非主设备，**零写入**） | 被门控跳过 | 绿色提示 **`not-primary：本机不是该 workspace 的主设备`** |
| 13 | **决定性反证**（Studio 侧机器可核验）：核对远端在步骤 12 之后有没有被偷偷写入 | 不应出现任何 `wb: brief 2026-09-13` | 远端最近 5 个提交只有 `44a2d17`/`8325639`/`598a285`/`448869b`/`86cc529`，**全仓 `--all --grep="brief 2026-09-13"` 零命中**；`HEAD == origin/main == 44a2d17`、vault 工作树 **0** 变更 |

#### 证据强度说明（哪些是机器核验、哪些是使用者回报、哪些是推断）

- **机器核验（代理侧，不可辩驳）**：步骤 4 的归属拉取、**5/6 两条门控探针**、7 的零写入核对、
  8 的 `primary_generation_conflict`、9 的归还结果与 generation 3、**13 的"没有 `wb: brief` 提交"反证**。
- **使用者逐字回报**：步骤 3 的卡片两行（`generation 2` + 角色"主设备"）、步骤 10 的
  `generation 3`、步骤 11 的"本机角色 = 备用设备"、步骤 12 的绿色
  `not-primary：本机不是该 workspace 的主设备`。
- **仍未逐条回报（保留为推断，不作为硬证据）**：步骤 1 的卡片按钮形态、步骤 2 的
  "不勾选直接点" 拒绝提示。这两步目前只有 §R.3 的前端单测与契约锚点覆盖。
- 方法论备注：步骤 12 的绿色提示**本身**只能证明"点击时 Air 已被门控关掉"，其充分条件是
  声明已指向 Studio（步骤 10 的同步已发生）——它不能单独证明降级按钮被点过，因为声明一旦属于
  Studio，Air 的角色即使是旧的 `automation-primary` 也照样被 `automation_gate` 挡住
  （该项要求"角色为主设备 **且** 声明设备匹配"）。步骤 11 的结论来自使用者对卡片的直接目视确认，
  与本条方法论无关。

#### 这次真机闭环证明了什么

- **D10 肯定分支**（此前只有单测+变异）：marker 指本机 ⇒ profile 真的落成 `automation-primary`，
  且 `automation_gate` 放行；
- **G1 的三条交互语义**在真机成立：**接管路径**（步骤 3 使用者回报 + 步骤 4 机器核验）、
  **`expected_generation` 语义**（步骤 8：过期被拒且零写入）、**降级入口**（步骤 11：
  本机角色回到备用设备）；仅"**必须勾选确认**"（步骤 2 的拒绝提示）仍未逐条回报，
  目前由前端单测 + 契约锚点覆盖；
- **"同一时间只有一台机器跑自动化"**在两个方向上都有机器证据：Air 接管后 Studio 被关掉
  （步骤 5/6，零写入）、归还并降级后 Air 被关掉（步骤 12），且步骤 13 反证了被跳过的那次
  **没有产生任何提交**；
- 归属提交随每次接管写入共享工作台并 push（`8325639`、`44a2d17`），历史保持线性。

#### 记录一个预期内的状态（不是缺陷）

步骤 10 里 Air 的卡片同时显示「当前主设备 = Studio」与「本机角色 = 主设备」：**归属以共享工作台
里的声明为准**，本机角色是本机档案的旧值，两者不一致时门控按声明走（Air 已被正确挡住）。
G1 的「降级为备用设备」就是给这种状态提供对齐入口的（步骤 11 用它对齐）。
另外，`acceptance-preflight` 的 `automation-role` 一项只检查**本机 profile 角色**、不比对声明归属，
因此它在"角色已过时"的机器上仍会 PASS——这是该项的既有定义，本轮未改动；判断"谁在跑自动化"
应以同步状态里的 `automation_primary_device_id` 与门控探针为准。

#### 顺带观察

本次两台机器的系统时钟一致（Air 写声明 `07:42:34Z` vs Studio 当时 `07:44:00Z`），
**未**观察到 D9 前提的跨机时钟偏差；两台机器的时间差可忽略。

### R.9 远端 CI 对当前 HEAD 全绿（2026-09-13T08:03–08:06Z）

本轮所有提交都按要求带 `[skip ci]`（从未自动触发 CI）。收尾时经使用者同意手动触发一次
`workflow_dispatch`，验证"仓库级门禁"这块唯一没被远端验过的表面。

| 项 | 值 |
|---|---|
| run | `34746739863`（workflow_dispatch，branch `main`） |
| 链接 | https://github.com/SummitYifeng/SummitWorkbench/actions/runs/34746739863 |
| HEAD | `70f236e87551c67889a35b92bf115d837b524fd5` |
| 结论 | **success**（2m18s） |

关键步骤（逐条取自 CI 日志）：

- `quality-gate`：**actionlint** 通过；`ruff` / `ruff format --check` 通过；
  `mypy (strict)` = `Success: no issues found in 340 source files`；
  `pytest with coverage gate` = **971 passed / 1 skipped**、覆盖率 **83.55%**（门限 80%）；
  `tsc --noEmit`（unused declaration 检查）与 `npm run test:frontend` 通过；
  `frontend build` + `verify-build` = `Build verified: v2026.09.13-70f236e-ae564ff2`；
  `secret scan passed`；native update 行为测试通过。
- `macOS arm64 contract`：`scripts/build-macos-app.sh` 构建成功，
  `WB_PACKAGED_APP=dist/ci/arm64/SummitWorkbench.app` 的**打包冒烟 1 passed**。
- `macOS x86_64 contract`：按预期走 `Reject unsupported architecture`（仅支持 Apple Silicon）。

说明与边界：

- CI **不引用任何 `secrets.`**（`grep -c 'secrets\.' .github/workflows/ci.yml` = 0），构建用
  `BUILD_NUMBER=github.run_number`、输出到 `dist/ci/`；因此 CI 的包**不带内置飞书凭据**，
  它验证的是仓库门禁与打包结构，**不替代**交付包 build 34（本地以
  `REQUIRE_BUNDLED_FEISHU=true` 产出、已装 Studio/Air 并真机核验）。
- 本轮未改动依赖与构建脚本（`pyproject.toml`/`uv.lock`/`web/package*.json`/`native/`/
  `scripts/build-macos-app.sh` 的 diff 均为空），所以 CI 里 `uv lock --check`、`npm ci`、
  native 测试与上一次绿跑逐字一致；唯一变量是本轮改动的 44 个文件。
- CI 侧前端构建标为 `v2026.09.13-70f236e-ae564ff2`（`source_hash` 同为 `ae564ff2`，
  只是 `git_revision` 取当前提交）；仓库内提交的静态产物仍是 `v2026.09.13-d4f43f8-ae564ff2`
  （产出它的源码提交），两者内容一致。

### R.6 本轮未能完成 / 仍开放

1. ~~两个演练仓库未删除~~：**已闭环（2026-09-13，使用者手动删除）**。代理侧两条凭据路径都无权限
   （`gh` OAuth 令牌 scope 实测为 `gist, read:org, repo, workflow`，缺 `delete_repo` ⇒ 403；
   app 存的细粒度 Git PAT 对这两个 org 仓库 `GET`/`DELETE` 均 404），使用者改在 GitHub 网页上删除，
   代理侧复核 `gh repo view SummitYifeng/summitworkbench-rehearsal{,-2}` 均 **404**（已不存在）。
   本地残留同时清理：`/tmp/device.json.rehearsal-backup`、`/tmp/msg-rehearsal.txt`，以及
   `~/Documents`、`~/Desktop`、`~/Downloads`、`/tmp` 下所有 `.git/config` 与
   `Application Support` 里对 rehearsal 的引用（**零命中**）。
   **顺带发现并清除一处凭据残留**：`/tmp/.t3`–`.t8` 是前几轮探针留下的 **44 字节会话令牌**
   （`-rw-------`），连同 profile 备份 `/tmp/config.toml.before`（无 secret 值）与本次会话
   scratch 一并删除，共 63 项；删除后复查无残留。
2. ~~Air 安装与双机冒烟~~：**已在 §R.7 完成**（全新 Air 从零配置 build 34 + 真机往返冒烟通过）。
3. **G2 未对真实 GitHub 空仓库做端到端——使用者已明确决定本轮不做**（不是遗漏，是接受的开放项）：
   发布流程要使用者自己的 PAT 且会在其账号下**新建**资源，代理未获授权执行。已覆盖：
   单测（成功路径断言"先验证后写入、PAT 不落盘"）+ API 契约测试 + **真机非 HTTPS 拒绝路径**
   （`remote_scheme_unsupported`，零副作用）+ 两后端 `add_remote`/`set_upstream`/`remove_remote`
   一致性。**未覆盖**：真实 GitHub 上"空仓库 → 绑定 → 首次 push 成功"这条**成功**分支。
   需要现场确认时（约 2 分钟）：在 GitHub 新建**空**私有仓库（不勾选 README）→ 设置页
   「首次发布到远端」填 HTTPS / 用户名 / PAT → 应显示「已发布到 …」，随后「⇅ 立即同步」得
   `ready` 且两端 HEAD 一致。
4. **G1 的接管按钮未在真 vault 上点击**（会递增 generation、转移定时自动化归属，属破坏性动作）；
   已用单测 + API 测试 + 真机 `primary_already_claimed` 拒绝路径覆盖。
5. `/Applications/SummitWorkbench.app.previous`（安装脚本自动保留的旧包）仍在，属可选清理，
   不影响使用；需要时 `rm -rf` 即可。
6. 服务日志会按 5 MiB ×（1 + 3 个轮转）自我限制，长期运行无需人工清理；`logs/` 在 vault 内的
   是**工作台内容**，与机器日志无关。
7. ~~G1 接管的真机验证~~：**已在 §R.8 完成**（Air 接管 → 门控关闭 → 过期 generation 被拒 →
   归还 Studio → Air 降级 → 门控再确认，全程 App 界面点击；归属 generation 1→2→3）。

---

## S. 工作知识库重建 + 第二大脑检索改造（2026-09-13，本轮）

> 本轮目标：把工作知识库的结构与规范定对 → 首批真实材料入库 → 把「第二大脑」的**纯文本**检索做深
> （不破「无向量库 / 无 RAG / 不加第三方依赖」硬边界），并用**两个真实问题**做端到端验收。

### S.1 破坏性步骤与备份（已核验）

| 步骤 | 结果 |
| --- | --- |
| 仓库外备份 | `~/Library/Application Support/SummitWorkbench/backup/vault-before-rebuild-20260913/`：`_vault` 目录副本 + `vault-full-history.tar.gz`（696 条目）+ `obsidian-root/.obsidian` + `当前材料` 副本 |
| 备份核验 | 备份内 git 历史 **55 提交**（与源一致）；非 `.git` 文件清单 `diff` **完全一致**；材料 `diff -r` 一致；`workspace_id` / `device_id` / `generation` 与源一致 |
| 清空与重建 | 删除 `_vault` 全部内容与旧 `.git`，保留 `.summit-workbench/`（`bf22c8d2-…`，Studio `51885d3d-…`，generation 3）；`git init -b main`，新历史从 1 个提交开始；**未使用 force/reset/rebase/stash** |
| 作用范围 | 只动 `~/Documents/Work/_vault/`；`~/Documents/Work/.obsidian/` 与其它位置未动（使用者逐条确认） |

### S.2 首批材料入库（实测口径）

- 桌面材料实测为 **9 个文件**（交接文档写的 11 个有误）：和HII的沟通 4 篇 md；和IT相关 5 个
  （3 份 txt + IT 计划 md + 智能纪要 md，**其中 zip 已解压为 md，无 zip 本体**）。
- `罗艺峰的视频会议 (3).txt` 与 `(2).txt` **sha256 完全相同**（字节级重复），按内容哈希去重，**未重复入库**。
- 入库形态（使用者选定 **C 混合**）：原文整篇作 `source` **逐字保留**，另拆原子笔记并回链原文。
- 产物：**105 篇** Markdown（8 篇 source/逐字稿 + 62 篇原子笔记 + 9 篇决策 + 3 篇会议笔记 +
  5 篇项目主页 + 4 篇线索主页 + 索引/规范/README/契约页）。

### S.3 质量门（全部真跑）

| 门 | 结果 |
| --- | --- |
| `wb vault check` | ✓ 105 篇全部通过 schema 校验 |
| 逐字引用机械校验 | ✓ 125 条 `路径` 引用 / 说话人时间点 / 原件比对，**0 问题** |
| 原件逐字保留 | ✓ 8 篇 source/逐字稿与原件**逐字一致**；注入式变异（往原件区插一句）能被抓出 |
| 幂等 / 去重 / 脏数据 | ✓ 三种失败模式真跑：重复入库 0 新增；同内容不同名跳过；同 ref 不同内容 **退出码 2 且不覆盖** |
| 双链解析 | ✓ `wb vault check` + 全库 232 条双链，除文档/模板里的示例占位外全部可解析 |
| 索引 | ✓ 105 篇 / 700+ 块，FTS5+trigram 可用，索引库在 **vault 之外** |
| Workbench 门禁 | ✓ `tsc`、13 个前端脚本、`build`+`verify-build`、`pytest --cov`（**1051 passed**，覆盖率 83.58%）、`ruff check`、`ruff format --check`、`mypy`、`secret_scan.py`、打包 App 冒烟 1 passed |
| 路由契约 | ✓ `docs/contracts/web-route-contract.json` **无 diff**（未新增路由；`/api/sources/read` 只是响应新增 `anchor`/`heading` 两个字段，已同步更新其测试） |

### S.4 两个真实问题的端到端验收（本轮核心）

可重复用例：`scripts/kb_acceptance.py`（真调模型）。证据输出：
`docs/acceptance/evidence/kb-acceptance-run-6.txt`。

**Q1**「根据之前和 HII 的沟通，请告诉我当前我们达成的商标共识规范是什么？」

- 路由 `decision`；**16/16 条事实带 `路径#区块` 出处**（`hii/notes/20260912-trademark-consensus#…`）；
- 追溯链走到证据层：`hii/notes/20260912-trademark-consensus → hii/sources/20260912-hii-hic-ip-overview`；
- 答案内容（登记主体统一为 HII、逐项商标归属、活满/和夫曼之旅分开管理）经人工与原文 §6.1/§6.2/§6.3/§9.2 逐条核对一致。

**Q2**「IT 当前的开发进度是什么，下一个阶段该怎么做？」

- 路由 `point`；**6/6 条事实带 `路径#区块` 出处**；
- 追溯链走到**逐字稿**：`it/it-roadmap → meetings/transcripts/2026-09-07-luo-yifeng-video-meeting-2-transcript`；
- 人工核对：Phase 2 现状与 9–12 月分月 Roadmap 均可在原文对应章节逐字核对。

**验收过程中修正的两处「我这边的错」**（如实记录）：

1. 最初的判据把「追溯」写成必须走到 `meetings/`，导致 Q1 假失败——**HII 侧材料本来就没有会议逐字稿**
   （证据是邮件与汇总文档）。判据改为：证据层 = `type: meeting-transcript` 或 `type: source`（逐字稿或原始材料），
   **会议笔记（派生摘要）不算证据层**。
2. 第一版验收跑不过 Q2 的「下一个阶段」：原因是 `it/it-roadmap` 与分月 Roadmap **之间没有双链**
   （属内容缺口，不是代码缺陷）。补上该双链并让双链扩展**不再按目标类型加权**（链接本身才是信号）后通过。

### S.5 入库时发现的数据质量问题（未自行裁决）

- 接待手册 §11.3 检查表存在**语义相反的错别字**（「私人费用无误混入工作费用」应为「勿/不」）；
- Linda Banes 职务两处不一致（手册 `Coordinator` / 当前来华 `Associate`）；
- Royalty 费率「重新起算」有两个触发条件（首次实际付款 / 每自然年）且交叉情形原文未定义；
- 0.5% 档阈值（201 名起）仅有同事反馈、无邮件证据（原文自认）；Refund Policy 未形成可写入 SOP 的规则；
- Danny 离境日期与航班缺失；Nita / Crystal 培训角色未展开；Sunny / 张凌紫 接待职责未明确。
- 以上均已记入 `hii/notes/20260913-china-visit-doc-errata.md` 与 `hii/hii-loyalty.md` 的 `## 未决问题`，
  **原件未改**（`source` 不可变）。

### S.6 仍开放 / 已知局限

- **打包 App 里尚无新检索代码**：本轮只跑通源码运行路径（`wb ask` / `wb kb`）与打包冒烟；
  要把新检索带进 `/Applications/SummitWorkbench.app` 需重新打包安装（属发布流程，不在本轮范围）。
- `index/projects.md` 的「已暂停 / 已归档」、`index/timeline.md` 的跨期大事记、
  `community/` 与 `hr/` 两条工作线目前是**诚实的占位**（首批材料未覆盖这两条线，不编造）。
- 双机（Studio / Air）：本轮按约定只验同步状态，未重走完整双机配方。

### S.7 粒度修订：C → C-lite（2026-09-13，使用者要求）

**动机**：使用者问「随着会议纪要与工作笔记增多，小文件会不会到几万」。实测结论：例行记录是
**1 份记录 = 1–2 篇**（会议纪要 = 会议笔记 + 逐字稿），不会爆量；但 5 份**汇总型**材料被拆成了
65 篇小文件，占当时 105 篇的 62%，维护成本偏高。且**检索此时已是块级**，原先「整篇为单元答不出问题」
的理由已不成立（那是 `_BODY_CHAR_CAP=4000` 时代的结论）。

**做法**：汇总型材料 = 1 篇 `source`（逐字原文）+ **1 篇分析笔记**（每个 `##` 区块 = 一个结论）；
**决策仍单独成篇**（Q4 的「集中 decisions/」不变）；会议纪要/日志/日报形态不变。

| 指标 | 迁移前 | 迁移后 |
| --- | --- | --- |
| vault 笔记数 | 105 | **45** |
| 分析笔记 | — | 5 篇（16/16/15/9/22 个区块） |
| `wb vault check` | ✓ 105 | ✓ 45 |
| 逐字引用 + 原件比对 | ✓ 125 条 0 问题 | ✓ 125 条 0 问题 |
| 验收 Q1 事实条数 / 块级引用 | 15 / 15 | **11–18 / 11–18**（逐次运行有模型波动，均 100%） |
| 验收 Q2 事实条数 / 块级引用 | 8 / 8 | **10–11 / 10–11**（均 100%） |
| 追溯链（走到逐字稿） | Q2 ✓ | Q1 ✓ / Q2 ✓ |
| 内容丢失 | — | **逐行校验 0 行真实丢失**（7 处差异全部是「内联链接被重定向」或区块标题词） |

证据：`evidence/kb-acceptance-before-clite.txt` / `kb-acceptance-after-clite.txt`。

**迁移中我自己犯的错（已修，留痕）**：
1. 第一版迁移脚本 `split_sections` 只取了第一个 `##` 之前的内容，而老笔记正文都在 `##` 小节里 →
   **大部分结论被写成空区块**。发现后从上一个提交整体恢复（`git checkout <commit> -- .`，未 force/reset），
   修脚本并**加上「逐行无损」硬断言**（内容丢失直接退出）后才重跑。
2. 第二版仍丢掉了 `## 来源` 里的 `（原文 § 四、4.1）` 这类**出处指针**（只保留了 `>` 引用行）→
   改为整段保留证据区。
3. 分析笔记的 `id` 用 `hash()` 生成，**每个进程都不同**（会漂移）→ 改为 `sha1(路径)[:4]`。
4. 迁移脚本一度漏掉 2 条 `source.ref` 指向邮件（而非 vault 笔记）的决策 → 改为显式列出决策清单。

**新增能力**：`[[文件#区块]]` 形式的双链现在会**定位到那一块**（此前只解析到整篇），
因为 C-lite 下「指向某一节」是一等用法；对应 `kb_index.anchor_hints` / `chunk_at` 与融合层的
`hints` 机制，并有测试覆盖。

**粒度政策已写入规范**：`_vault/conventions.md` §13.1（含各类材料的文件数预期与引用方式）。

## T. 攻击性测试收口 · 最后一遍 CI · 对外发布 0.4.8（2026-09-13，本轮）

本轮不新增功能，只做三件事：**攻击上一轮的新代码**、**真跑一遍远端 CI**、**把 0.4.8 发出去**。
前两轮的提交都带 `[skip ci]`，远端从未在它们上跑过，所以「最后一遍 CI」是真跑而非复跑。

### T.1 攻击测试的结论（§A 清单）

| # | 攻击点 | 结论 |
| --- | --- | --- |
| A.1 | 损坏的索引库让问答直接崩 | **真实缺陷，已修**（见下） |
| A.2 | 打包环境是否真支持 FTS5 | **实测支持**；且强制关掉 FTS 的分支在包内也活着 |
| A.3 | `index/people.md` 生成脚本没进仓库 | **已固化**，再生成做到逐字节一致 |
| A.4 | `kb_acceptance.py` 自己没有单测 | **已重构为可测纯函数 + 16 条断言** |
| A.5 | prompt 已 v2 但没有测试锁版本 | **已对齐 + 加版本锁** |
| A.6 | 只有 2 题做回归 | **扩到 8 题**（①回溯/②决策/⑤回顾 + 点查/综合） |
| A.7 | 65→5 迁移未独立复核 | **已复核：1296 行逐行 0 丢失，94 个区块锚点 0 悬空** |

**A.1 的缺陷与修法**。实测复现：索引文件是垃圾内容时 `KnowledgeIndex.__init__` 抛
`sqlite3.DatabaseError: file is not a database`，而模块文档承诺的是「索引缺失/损坏时退化为纯
Python BM25」；`wb ask` 的兜底只捕 `(LLMError, ValueError)`，于是把 sqlite3 的栈直接抛给使用者。
现在三种失败形态分开处理：

- 垃圾文件 → **删掉重建**（索引是纯派生数据，删了不丢任何资产）；
- 旧版本残留 / 表结构不匹配 → **删表重建**（`CREATE TABLE IF NOT EXISTS` 修不了已存在的错表）；
- 库根本建不出来（只读目录、路径不可写）→ 抛 `IndexUnavailableError`，`retrieve_via_index` 外层兜底
  **退回纯 Markdown 子串扫描**，并在 `Trace.degraded` 写明原因（问答页同步渲染）。

额外实测的两条边界（都能安全降级，无栈抛出）：

- 索引文件只读 + vault 已变 → `OperationalError: attempt to write a readonly database` 被外层接住，
  降级结果与子串扫描基线**逐条一致**；
- FTS 影子表被外部改坏 → 查询期退化为自建 BM25，不再抛。

**A.2 的探针**。新增 `SummitWorkbenchServer --kb-diagnostic`（+ `kb_index.runtime_diagnostic()`），
在**已构建的包**里、`env -i`（无仓库 Python、无 PATH）下实测：

```json
{"sqlite_version": "3.53.1", "fts5_trigram": true,
 "fts_hit": ["probe/probe#检索目标"], "chunk_level_ok": true,
 "forced_no_fts_search_is_none": true,
 "forced_no_fts_bm25_hit": ["probe/probe#检索目标"], "bm25_fallback_ok": true}
```

即：包内 SQLite 3.53.1、FTS5+trigram **可用**、命中是**块级**的；并且把 FTS 在同一进程里强制关掉后
`search()` 如实返回 `None`、自建 BM25 仍命中同一块——**「FTS5 不可用」这条分支在真实包里也活着**。
集成测试对两种结果都断言，因此不会因为换机器而静默退化。

**A.3**：`scripts/kb_index_people.py` 固化进仓库，`--check` 可判定页面是否过期。用它再生成真实
`index/people.md` 得到**逐字节一致**的结果（排序＝条目数降序 + 名字升序；前 4 篇预览 + `（共 N 篇）`）。
校验过程中先误改了 vault 页面，已用 `git checkout -- index/people.md` 从 HEAD 恢复并比对确认
（该文件在 vault 仓库里是干净的，未动历史）。

**A.4**：`kb_acceptance.py` 的裁决逻辑抽成 `audit_case` / `evidence_chains` 两个纯函数并补单测。
证据层**只认** `meeting-transcript` 与 `source`：会议笔记是派生摘要，早先版本把它算作证据层，
于是「笔记 → 会议笔记」这条链就能让验收通过，看起来走到了证据、其实停在摘要上。

**A.5**：`prompts/qa-answer.md` 已是 v2 而 `test_ask_workflow.py` 仍写 `Prompt(version=1)`。
已对齐为 v2，并新增断言锁住 `qa-answer@v2` 与 v2 的 `路径#区块标题` 契约、以及 stub 与文件同版本。

**A.6**：回归清单从 2 题扩到 **8 题**，覆盖 ① 回溯 / ② 决策 / ⑤ 回顾，外加点查与综合。断言
「关键证据被召回 + 引用是块级 + ≤2 跳走到证据层」。只有 Q1/Q2 真调模型，其余只验检索，
**不增加 token 成本**。为进 CI，另加 `tests/unit/test_ask_regression_questions.py`：同样 8 题跑在
合成 vault 上，问题清单**直接取自 `kb_acceptance.CASES`** 并有守卫测试防两组清单漂移。
（注意：`_guarantee_link_context` 并不存在——当时验证不了就删掉了，本轮没有引入它。）

**A.7**：独立复核 C-lite 迁移，证据 `evidence/kb-migration-recheck-20260913.txt`：
65 篇被删 → 5 篇分析笔记；**1296 行逐行校验只有 5 处差异，且全部是链接目标重写**
（展示文字一字不差，只把 `[[已删原子笔记]]` 换成 `[[分析笔记#区块]]`）→ **逐字内容 0 丢失**；
全库 310 条双链中 94 条带 `#区块`，**94 条全部可解析、0 悬空**（另 7 条解析不到的都定性为
语法示例 / HTML 注释里的模板，不是真实引用）。

### T.2 本轮本地门禁（全绿，逐条真跑）

| 门禁 | 结果 |
| --- | --- |
| `ruff check` / `ruff format --check` | All checks passed / 462 files already formatted |
| `mypy` | Success: no issues found in 355 source files |
| `pytest --cov` | **1083 passed**, 1 skipped（需 `WB_PACKAGED_APP` 的打包 smoke）, 覆盖率 **83.43%**（门 80%） |
| `tsc --noEmit -p web/tsconfig.json` | 通过 |
| `npm --prefix web run test:frontend` | 15 组前端契约/纯渲染测试全部通过 |
| `npm --prefix web run build` + `verify-build.mjs` | Build verified: `v2026.09.13-67616fd-ae564ff2` |
| `scripts/secret_scan.py` | secret scan passed |
| `scripts/verify-workflows.sh`（actionlint） | 通过 |
| `scripts/check-action-refs.sh` | 通过（pre-push-gate 内） |
| `scripts/pre-push-gate.sh` | ✓ 本地门禁全部通过（push 时钩子又跑了一遍） |

测试数从上一轮 **1051 → 1083**（新增 32 条，全部对应 §A 的攻击点）。

### T.3 远端 CI（手动触发，全绿）

- **run id**：`34750517716`
- **URL**：https://github.com/SummitYifeng/SummitWorkbench/actions/runs/34750517716
- **触发**：`gh workflow run ci.yml --ref main`（`workflow_dispatch`）
- **headSha**：`fbf735b1d145185de34c06b95737186f134c9925`（`conclusion: success`）
- **job 级结果**：`workflow-lint` ✓ 12s ｜ `quality-gate` ✓ 1m58s ｜
  `macOS arm64 contract` ✓ 1m44s ｜ `macOS x86_64 contract` ✓ 47s

说明：push `main` 时的自动 run（`34750511241`）被同一 concurrency 组的手动 run 取消，
因此以手动 run 为准——这也正是使用者的要求（手动触发而不是靠 push）。

### T.4 构建与产物（0.4.8 / build 35）

- 命令：`REQUIRE_BUNDLED_FEISHU=true WB_FEISHU_APP_ID=… WB_FEISHU_APP_SECRET=… BUILD_NUMBER=35 ARCH=arm64 scripts/release-macos.sh`
- 版本定版：`pyproject.toml` `0.4.7 → 0.4.8`；`CHANGELOG.md` 的 `[未发布]` 改为 `[0.4.8] - 2026-09-13`
- 产物目录：`dist/releases/0.4.8/arm64/`

| 项 | 值 |
| --- | --- |
| 版本 / build / 架构 | `0.4.8` / `35` / `arm64`（INTERNAL-DEV，ad-hoc，min macOS 13.0） |
| 构建来源提交 | `455c8977073987ad356d319ccb7798a3609107a6` |
| 前端 build identity | `v2026.09.13-455c897-ae564ff2` |
| DMG | `SummitWorkbench-0.4.8-arm64-INTERNAL-DEV.dmg`（50,449,158 bytes） |
| **DMG SHA-256** | `d707449612bcaaed55f7203ffe917202e0e28be042fa9f2dec81c642bb96c90b` |
| App SHA-256 | `a21d1675e52e579489c1b051ebd850f9a7e55715764c9a5d5cf1b7d4a54ee0da` |
| `scripts/verify-macos-release.sh` | **EXIT 0**（签名/清单/隐私卫生/离线启动全过；内置凭据结构正确，值不打印） |
| 内置飞书凭据 | 已内置（`REQUIRE_BUNDLED_FEISHU=true`），`verify-macos-release.sh` 结构化校验通过 |

密钥从未写入仓库：`git ls-files | grep feishu-defaults` 为空，`secret_scan.py` 通过。
首次构建（`fbf735b`）的产物已改名为 `dist/releases/0.4.8.superseded-fbf735b/` **保留而非删除**，
因为随后给包内探针补了「强制关掉 FTS」的分支，需要按新提交重建。

### T.5 真机验收（已安装 App：0.4.8 / build 35）

安装：`scripts/install-macos-app.sh dist/releases/0.4.8/arm64/SummitWorkbench.app` → ✓
安装后 `/api/version` 回报 `server_version 0.4.8`、`build 35`、`git_revision 455c897`、
`mode production`、`frontend_build v2026.09.13-455c897-ae564ff2`——**装上去的就是新代码**。

**两个真实问题**（逐字保留，未改写）通过已安装 App 自己的 `POST /api/ask`（即「第二大脑」面板
调用的同一路由）提问，脚本 `scripts/kb_acceptance_installed.py`：

| 题 | 路由 | 进入上下文 | 事实引用 | 追溯链 |
| --- | --- | --- | --- | --- |
| Q1 商标共识规范 | `decision` | 6 条 | 4 条 **全部块级** | 18 条，含走到逐字稿 |
| Q2 IT 进度与下一阶段 | `point` | 6 条 | 4 条 **全部块级** | 19 条，含走到逐字稿（本题要求） |

结论 **✓ 2/2 通过**（判定与源码口径完全一致：非 unanswerable、有带出处事实、引用块级且锚点真实
存在、≤2 跳走到证据层、该有逐字稿的题确实走到了逐字稿）。
完整报告（含面板会渲染的 HTML 与「检索轨迹」）：`evidence/kb-gui-installed-build35.txt`。

**引用真的点得开**：用已安装 App 的 `/api/sources/read` 逐条打开问答给出的引用，**6/6 成功**，
且每条都返回了正确的 `anchor` / `heading`（含会议笔记与逐字稿）。

**Obsidian 侧人工核对**：把两题答案的 **21 条主张**逐条对回 `_vault/` 里的原文，
**21/21 命中、0 条编造**（含「尚未确认」项确实在原文标为待确认，没有被写成已定事实）。
证据：`evidence/kb-gui-obsidian-crosscheck-build35.txt`。
⚠️ 本会话拿不到屏幕录制权限（`screencapture` 报 `could not create image from display`），
**没能截 Obsidian / 面板窗口的图**；核对方式是直接读同一批 `.md` 字节（Obsidian 渲染的就是它们）
+ 已安装 App 自己的 API。这是本轮**唯一没有做到的验收形式**，如实记录。

### T.6 本轮额外发现并修掉的缺陷：`install-macos-app.sh` 的 readiness 假失败

装 build 35 时**实测踩到**（旧的已归档文档 §6.2 把它记为「踩过的坑」，但一直没修）：

- 打包 App 的 runtime record 落在 `<app_support>/runtime.json`
  （原生启动器经 `WB_RUNTIME_RECORD` 注入，见 `native/SummitWorkbench/RuntimeRecord.swift:25`），
  而 `wb web` CLI 落在 `<app_support>/profiles/*/runtime/runtime.json`；
- `install-macos-app.sh` **三处**都只查后者，于是：
  1. App 正在运行时**检测不到**，会绕过安全检查直接替换正在运行的 App；
  2. 服务其实已就绪却在 readiness 窗口结束后**误报「服务未启动」**，退出码 1 并把
     `SummitWorkbench.app.previous` 留在原地（实测就发生了）。

修法：加 `runtime_records()` 助手（与 Swift 侧 `RuntimeRecord.candidateURLs` 同口径：先查根、
再查 `profiles/**`），三处统一改用它；readiness 循环遍历所有候选记录，任一端口就绪即成功，
并打印实际使用的 record 路径。修的过程中我自己又踩了一个 bash 坑——`$DEST_APP（` 里的多字节
字符被当作变量名的一部分（`set -u` 下报 `DEST_APP…: unbound variable`），已改成 `${DEST_APP}`；
两处都在真机上复验过：**运行中拒绝安装（EXIT 1）**、**退出后干净安装（EXIT 0 且清理 .previous）**。

注意：该脚本不进 App bundle，因此上面的 DMG 内容不受此修复影响（`git_commit` 仍是 `455c897`），
修复随其后的仓库提交进入版本库。

### T.7 仍未覆盖 / 仍开放

- **没有 GUI 截图**：会话无屏幕录制权限（见 T.5）。GUI 侧的证据是「已安装 App 自己的
  `/api/ask` + `/api/sources/read` + 同一批 vault 字节」，不是鼠标点击的截图。
- **tag 触发的 `release.yml`（往 `yifeng93/SummitWorkbench-Updates` 发更新 feed）**：
  需要 `secrets.UPDATE_REPO_TOKEN` 与受保护的签名私钥；内部 ad-hoc 包按 `RELEASING.md`
  不走在线签名门。tag 是否推送及 release run 结果见 §U。
- `_vault` 的远端推送仍未成功：本地 `~/Documents/Work/_vault` 停在 `7380425`，
  HTTPS 远端（`github.com/yifeng93/WorkKnowledge.git`）当时网络异常（非鉴权问题）。
  本轮的真机验收**只读本地 vault**，不需要它同步，因此按使用者指示未重试。
- `community/`、`hr/` 与 `index/timeline.md` 跨期大事记仍是诚实占位；`index/projects.md` 的
  「已暂停 / 已归档」仍为空。
- 双机（Studio / Air）本轮未重走完整配方。
- `review/_intake/hii-royalty-visits.md` 是否清理仍待使用者决定。

## U. tag 发布 v0.4.8 与之后的实测（2026-09-13，本轮收尾）

### U.1 tag 触发 `release.yml`

`v0.4.8` 打在 `c46aff1203d34bfddf013c9d0a10bc8eeecd9048`（远端 CI run `34751018721`
在该提交上四个 job 全绿之后才打），已推送。

- **run id**：`34751154512`（`push: v0.4.8`）
- **URL**：https://github.com/SummitYifeng/SummitWorkbench/actions/runs/34751154512
- **首次结果：失败**，卡在 `Prepare protected update configuration`。

失败原因**不是代码**：release job 的 `environment: release` 里，仓库变量 `UPDATE_DOWNLOAD_URL`
仍指向 **v0.4.7** 的 DMG，而工作流会断言它必须等于「本次 tag 推导出的 URL」，于是报
`UPDATE_DOWNLOAD_URL must be https://…/download/v0.4.8/SummitWorkbench-0.4.8-arm64-INTERNAL-DEV.dmg`。
这是每次发版都要人工推进的一项受保护配置。

处理：把该环境变量更新为 v0.4.8 的 URL。注意 `PUT`（更新）在本 token 下返回 404，而
`POST`（新建）/`DELETE` 正常，因此采用 **删除后重建**；过程中建的探针变量已删除，环境里
最终只有 `UPDATE_DOWNLOAD_URL` / `UPDATE_FEED_URL` / `WB_FEISHU_APP_ID` 三项（值未打印）。
随后 `gh run rerun --failed`：**全绿**，含
`Build signed internal arm64 DMG`、`Run packaged integration tests`、
`Run P1-07D dual-device acceptance gate`、`Publish complete public update release`。

### U.2 已发布的产物

- 发布页：https://github.com/yifeng93/SummitWorkbench-Updates/releases/tag/v0.4.8
  （`draft: false`、`prerelease: false`，即**稳定**渠道；`latest` feed 随之指向 0.4.8）
- 资产：`SummitWorkbench-0.4.8-arm64-INTERNAL-DEV.dmg`、`update-feed.json`、`SHA256SUMS`、
  `release-metadata.json`、`SBOM.json`、`notary-log.json`、`test-manifest.json`
- **已发布 DMG 的 SHA-256**：`3958d446d5f439e1e8bb6a1d705d930ba4959ed6c38c33d015599cd4605a5815`
  （下载后按已发布的 `SHA256SUMS` 复核：**OK**）
- `update-feed.json` 指向 v0.4.8、`build 22`、`minimum_macos 13.0`，带 Ed25519 签名与公钥
- ⚠️ CI 产物是 **build 22**，本地按 §T.4 构建的是 **build 35**：两者同源（tag 提交）、同一构建脚本，
  但 build number 与 DMG 字节都不同（CI 用 run 号做 BUILD_NUMBER）。本节以下用
  「**已发布包（build 22）**」与「**本地包（build 35）**」区分。

### U.3 已发布包的独立探针（A.2 的迁移验证）

把已发布 DMG 下载、`hdiutil attach`、取出 App 后，在 `env -i`（无仓库 Python、无 PATH）下跑
`SummitWorkbenchServer --kb-diagnostic`：

```json
{"sqlite_version": "3.49.1", "fts5_trigram": true,
 "fts_hit": ["probe/probe#检索目标"], "chunk_level_ok": true,
 "forced_no_fts_search_is_none": true,
 "forced_no_fts_bm25_hit": ["probe/probe#检索目标"], "bm25_fallback_ok": true}
```

**这就是包内探针存在的理由**：同一份源码，CI 冻结出来的 SQLite 是 **3.49.1**，
而开发机 venv 是 **3.53.1** ——不探一下根本不知道分发环境是什么。两者 FTS5+trigram 都可用，
强制关掉 FTS 的兜底分支也都活着。

### U.4 已发布包的真机验收：先被权限挡住，**已闭环**（2026-09-13，同日补做）

装好已发布包（build 22，`/api/version` 回报 `server_version 0.4.8 / build 22 / git_revision c46aff1`）
之后，`/api/ask` 与本机一切**要读 `~/Documents/Work/_vault` 的接口**都**永久挂起**：

| 请求 | 结果 |
| --- | --- |
| `GET /api/version`（不碰 vault） | 200，0.005s |
| `POST /api/ask`（模型 + vault） | 挂起（240s 无响应） |
| `GET /api/state`（读 vault） | 挂起（12s 无响应） |
| `GET /api/sources/read?source_id=../../etc/passwd`（白名单早退） | 400，0.008s |
| `GET /api/sources/read?source_id=it/it-roadmap`（真的读文件） | 挂起 |
| 同一台机器上 CLI 直接读 `_vault/conventions.md` | 正常 |

排查排除项（都实测过）：远端 CI 与 API 可达（5.8s 走完一次真实问答）；workspace 锁未被持有
（外部 `flock LOCK_EX|LOCK_NB` 直接拿到）；Keychain 可读（`security find-generic-password` 秒回）；
服务进程无出站连接、无 `security` 子进程、无 `SecurityAgent`、线程全在 idle；
`flock`/`fcntl` 阻塞栈为空；服务 stdout 落到 `~/Library/Logs/summitworkbench-panel.log`，无异常。

**最可能的原因（推断，未能直接证实）**：`~/Documents` 是 macOS TCC 保护目录，而 ad-hoc 签名**每次
构建都不同**——对新签名的 App，macOS 把首次访问 `~/Documents` 视为新应用的请求，需要一次
「允许访问「文稿」文件夹」。本会话既没有屏幕录制权限（`screencapture` 报
`could not create image from display`），也没有 GUI 自动化权限（System Events 取不到任何窗口），
**无法点掉这个授权框**，于是文件访问在 App 进程里一直等，表现为接口挂起；而 CLI 所在的终端
早已被授权，所以命令行读同一个文件毫无问题（`UserNotificationCenter` 进程确实在跑，
与「有等待中的系统提示」一致）。

**⇒ 闭环**：使用者批准该授权后，App 于 `2026-09-13T13:21:37Z` 重启，同一个已发布包
（build 22）立刻恢复正常 —— `/api/state` **200 / 0.021s**（此前挂起）。于是当场把
已发布包的验收补齐：

| 项 | 结果 |
| --- | --- |
| `POST /api/ask` 两题（真调模型） | **2/2 通过**，路由 `decision` / `point` |
| 事实引用块级比例 | Q1 5/5、Q2 4/4，且锚点全部真实存在 |
| 追溯链 | Q1 18 条、Q2 19 条，均含走到逐字稿（Q2 本题要求） |
| `路径#区块` 经 `/api/sources/read` 打开 | **9/9** 成功，`anchor`/`heading` 均正确 |
| 21 条主张对回 `_vault` 原文 | **21/21 命中、0 条编造** |

证据：`evidence/kb-gui-published-build22.txt`、
`evidence/kb-gui-published-build22-obsidian-crosscheck.txt`。

因此本轮的两题真机验收**同时**覆盖了两个产物：**本地包 build 35**（§T.5）与
**已发布包 build 22**（本节）。仍未做到的只有 GUI 截图（会话无屏幕录制权限），
这一点不因闭环而改变；上面那张「U.4 未能完成」的表仍然保留，因为它是定位过程的一部分。

### U.5 本轮新发现、未修的缺陷

> **2026-09-14 更新**：本节第一条**已修复**（见下），第二条仍未修。标题保留当时的「未修」措辞
> 以免丢失历史，但**别再把第一条当成待办**。

- ~~**`GET /api/sources/read?source_id=`（空值）返回 500，而不是代码意图的 400**~~
  —— **已于 2026-09-14 修复**（`webapp/routers/review.py`）。
  原根因：`Path("")` 得到 `PosixPath('.')`，`''.suffix != '.md'` 于是走
  `Path('.').with_suffix('.md')`，抛 `ValueError: PosixPath('.') has an empty name`，
  而这句排在 `if not raw_id ... return 400` **之前**。
  修法：把「空引用」与「只有 `#区块`、没有路径」的判定提到碰 `Path` 之前（沿用同一段 400 语义）。
  **修复前在已装 build 41 上实测**：空值 → `500`、`source_id=#关键结论` → **也 `500`**；
  对照 `../secret.md` → `400`、正常路径 → `200`。
  ⚠️ 当时只记了「空值」一种，实际**「只有 `#区块`」走同一条根因**——前端拼「路径#区块」时
  路径丢了就会命中，也一并修掉。修复后由
  `tests/unit/test_webapi.py::test_api_sources_read_rejects_empty_and_block_only_ids_instead_of_internal_error`
  锁定为 400（含变异验证：移除守卫即红）。
- 卸载/重启 App 时旧 server 进程偶尔不会被回收（本轮实测一度同时存在 3 个 `SummitWorkbenchServer`）。
  观察到的触发场景是客户端在请求中途被强杀；未定位到确定机理，也未修。

### U.6 本机当前状态

`/Applications/SummitWorkbench.app` = **已发布包 0.4.8 / build 22**
（`CFBundleShortVersionString 0.4.8`、`CFBundleVersion 22`、`codesign --verify --deep --strict` 通过，
构建自 `SummitYifeng/SummitWorkbench` 的 `c46aff1`）。「文稿」文件夹授权已批准，接口正常（见 U.4）。
本地另一份 build 35 产物保留在 `dist/releases/0.4.8/arm64/`，被取代的 `fbf735b` 产物保留在
`dist/releases/0.4.8.superseded-fbf735b/`（均未删除）。

> 顺带澄清一个容易混淆的短哈希：`bb7ab22` **不是**本 App 的构建提交，它在
> `yifeng93/SummitWorkbench-Updates`（更新 feed 仓库）里，是默认分支尖端的
> “publish signed update feed for build 109”（2026-09-06）——那是历史遗留的 feed 提交，
> 与 0.4.8 无关。判断「本机装的是哪一版」只认
> `Contents/Resources/build-manifest.json` 的 `version`/`build`/`frontend_build`
> （其中 `frontend_build` 里的短哈希就是构建提交）。
