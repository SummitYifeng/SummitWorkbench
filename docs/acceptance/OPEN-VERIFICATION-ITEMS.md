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
> [`UI-VERIFICATION-BATCHES.md`](UI-VERIFICATION-BATCHES.md)：它把本文件剩下的 11 个 UI 层开放项
> 按「需要什么数据」重新分批（批 0 环境基线 → 批 7 原生 App 黑盒），并逐批给出可执行夹具配方。

- 最近更新：2026-09-11
- 当前基线：`v0.4.4` build 12（前端 `v2026.09.11-e8ed6f7-6e6e0c91`），远端 CI 全绿
- 判定口径：**「历史某个 build 上验证过」不等于「当前代码已验证」**，见 A 组。

## A. 真实外部服务回归

| # | 项 | 说明 |
|---|---|---|
| A6 | 真实双设备上的冲突恢复提交 | 需要第二台机器（MacBook Air） |

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
| B4 | packaged App / WKWebView 黑盒 | CI 的 packaged smoke 只覆盖打包后的 server 与构建身份，**不覆盖原生 UI**。2026-09-11 首次尝试时 App 绑定真实工作区而主动停止；**隔离配方已查明（临时 `HOME`，不能用 `WORK_ROOT`）**，见 `UI-VERIFICATION-BATCHES.md` §9 |

> B1（Chrome 原生 200% 缩放）、B2（浅色主题）、B3（`prefers-reduced-motion`）已于 2026-09-11 由
> 提示词 F 的实测关闭——见下方「已关闭」。验收在候选产物上进行，其 **`source_hash` 与合并后
> main 的产物完全相同（`6e6e0c91…`）**，仅 `git_revision` 不同，故结论直接适用。

## C. 审批边界

| # | 项 | 说明 |
|---|---|---|
| C4 | 个人日程（`feishu-meeting`）落点的浏览器证据 | **部分**：`global-inbox` / `project-inbox` 可批准、缺依据候选 `disabled`（含 title 理由）已验证；**「新建会议（个人日程）」仍需飞书授权**（提示词已设为条件执行） |

> **C1（`0/1/100/101` 完整矩阵）已于 2026-09-11 关闭** —— 见下方「已关闭」和第二轮 §M。
> **C2（一次点击一次请求）已于 2026-09-11 关闭** —— 见下方「已关闭」。
>
> **C3（部分失败可见）已取得真实证据（2026-09-11，见 §K）**：3 条候选分属 `project-main` /
> `feishu-task` / `feishu-meeting`，其中日历创建当时因 CLI 缺 creator 而失败，结果被如实报成
> `批准写回=2 失败=1`，失败原因写进候选的 `error:`，**没有被包装成整体成功**。

## D. 导入与来源

| # | 项 | 说明 |
|---|---|---|
| D2 | 来源面板异常矩阵（浏览器层） | **HTTP 矩阵已完成**（415 / 200+truncated / 413 / 400×4 / 404，见 §M 第三轮），且**非 UTF-8 返回 415 而非 500，第一轮缺陷已确认真实修复**。**剩余**：① 逐个从「来源」入口打开并记录**面板显示的文字**（此前是直接 fetch，没看界面）；② **第二个 workspace 的同名文件隔离** |
| D3 | 正文截断提示的真实显示 | **已于 2026-09-11 关闭** —— 见下方「已关闭」 |

> **D1 已部分验证（2026-09-11，见 §K）**：成功导入（含项目解析）与**幂等重跑**
> （`待导入 0 场，已跳过 3 场，约 0.0 CNY`，零模型调用）均已取得证据。
> **软预算与部分失败的导入路径仍未验证**；10 MiB 上限原只做在 web/App 层，**已于 2026-09-11
> 下沉到 workflow 层修复（`7e25cd3`）**，见 §K。

## E. 交互细节

| # | 项 | 说明 |
|---|---|---|
| E3 | 项目可移动滚动位置恢复 | ✅ **已于 2026-09-11 第三轮关闭** —— 见下方「已关闭」 |
| E5 | R01–R14 交互断言在真实页面复验 | **剩余 4 条**：R04 / R05 / R07 / R09。R01 已于第三轮关闭。**R04 / R09 经查都不需要真实凭据**（R04 保存路径不校验密钥、R09 可造本地 outbox 行），只有 C4 需要飞书。R02/R03/R06/R08/R10/R11/R12/R13/R14 已关闭 |

> **E1 / E2 已于 2026-09-11 关闭**；**E4 已取得实测结果**（跨端口草稿丢失，与「不承诺迁移」的
> 既定边界一致，非缺陷）——均见下方「已关闭」。
>
> E5 的剩余 5 条有个共同点：**都不需要新产品夹具，只需要在 DevTools 里做请求拦截/计时**，
> 是下一轮成本最低的一批。第二轮又验证了这一点：**基础设施问题**（CDP 没暴露 page target）
> 是唯一的拦路石，而不是产品复杂度。现已把两个脚本改成自愈版并实测通过，
> 见 [`UI-VERIFICATION-FINAL-PROMPT.md`](UI-VERIFICATION-FINAL-PROMPT.md)。

## F. 发布链路

| # | 项 | 说明 |
|---|---|---|
| F1 | Developer ID / 公证 / Intel / Windows | **明确超出 `INTERNAL-DEV` 交付范围**，非缺陷 |

> tag 触发的 `release.yml` 实跑已于 2026-09-11 关闭，见下方「已关闭」。

## G. 测试覆盖洼地（代码有、测试未走到）

总体覆盖率 82.36%。以下是仍然偏低的模块；多为薄封装或需要真实外部服务，风险等级不同。

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

**尚未重建的交付物**：本次只更新了仓库内的前端产物；已安装的 build 9 App 与历史 DMG 仍带旧前端。
若要让装机版本包含新前端，需按 `docs/RELEASING.md` 重新打包。

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

- **A6**：真实双设备冲突恢复需要第二台机器（MacBook Air）。
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
