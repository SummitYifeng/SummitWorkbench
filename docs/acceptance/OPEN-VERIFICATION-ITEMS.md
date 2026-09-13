# 未验证清单（单一真源）

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

- 最近更新：2026-09-12
- 当前基线：`v0.4.7`（分发版；**已发布**为 build 21，见
  <https://github.com/yifeng93/SummitWorkbench-Updates/releases/tag/v0.4.7>；前端见
  `build-meta.json`），远端 CI 全绿。
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
- **当前开放项：1 项（F1，非缺陷，明确超出 `INTERNAL-DEV` 交付范围）**，另有**本轮复跑发现的
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

### 本轮发现的产品缺陷（D1–D8，**全部已修**）

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
