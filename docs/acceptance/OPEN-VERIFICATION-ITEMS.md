# 未验证清单（单一真源）

> **这是唯一权威的「还没验证什么」清单。** 其他文档（README、验收记录、交接档案、ADR）只描述
> 各自范围内的结论并链接到这里，不再各自维护一份可能漂移的副本。
>
> 维护约定：本文件只记录**尚未取得证据**或**证据不足**的项；取得证据后把该项移入下方
> 「已关闭」并注明证据位置（提交、CI run、测试文件名）。不要在这里写计划或需求。
>
> **怎么验证**：需要真实浏览器执行构建产物的项，逐条可执行提示词见
> [`BROWSER-VERIFICATION-PROMPTS.md`](BROWSER-VERIFICATION-PROMPTS.md)——可直接交给具备
> computer use 能力的 agent 执行。

- 最近更新：2026-09-11
- 当前基线：`v0.4.4` build 9（前端 `v2026.09.10-df4ba1f-1cb9c2eb`），远端 CI 全绿（844→878 passed）
- 判定口径：**「历史某个 build 上验证过」不等于「当前代码已验证」**，见 A 组。

## A. 真实外部服务回归（历史验证过，当前 build 未回归）

这些链路在更早的里程碑真机通过，但 v0.4.4 代码上未重新执行。需要真实凭据，且必须在隔离环境做。

| # | 项 | 历史证据 |
|---|---|---|
| A1 | 真实云端模型调用：会议结构化、快速捕捉分类、简报排序、`wb ask` 回答 | M1/M2 验收 |
| A2 | 飞书 OAuth 全链路（authorize-url → login → token 刷新 → smoke） | M0/M1 |
| A3 | 飞书任务写回（`wb task`、面板一键完成、行内编辑） | 2026-09-03 真机核实 |
| A4 | 飞书日历写回（会议行内编辑、新建日程） | 2026-09-03 真机核实 |
| A5 | 真实远端 Git 凭据与双向同步（HTTPS remote + PAT） | P1-07D 双机验收（v0.4.3） |
| A6 | 真实双设备上的冲突恢复提交 | P2-02 build 29 双机验收 |

> A6 的**代码路径**已于 2026-09-11 由
> `tests/integration/test_acceptance_dual_device.py::test_dual_device_divergence_recovery_converges_with_two_parent_merge`
> 端到端自动化覆盖（双父提交、审计、推送、对端快进），并做过变异测试验证。仍缺的只是真实双设备现场复跑。

## B. 原生与无障碍矩阵

| # | 项 | 说明 |
|---|---|---|
| B4 | packaged App / WKWebView 黑盒 | CI 的 packaged smoke 只覆盖打包后的 server 与构建身份，**不覆盖原生 UI** |

> B1（Chrome 原生 200% 缩放）、B2（浅色主题）、B3（`prefers-reduced-motion`）已于 2026-09-11 由
> 提示词 F 的实测关闭——见下方「已关闭」。验收在候选产物上进行，其 **`source_hash` 与合并后
> main 的产物完全相同（`6e6e0c91…`）**，仅 `git_revision` 不同，故结论直接适用。

## C. 审批边界

| # | 项 | 说明 |
|---|---|---|
| C1 | `0/1/100/101` 条完整矩阵 | 100 条上限目前只有源码级断言 |
| C2 | 「一次点击一次请求」的网络计数证据 | UI 点击观察不能替代网络层计数 |
| C4 | global inbox / 个人日程落点的完整浏览器证据 | 资格与禁用逻辑有纯渲染测试 |

> **C3（部分失败可见）已取得真实证据（2026-09-11，见 §K）**：3 条候选分属 `project-main` /
> `feishu-task` / `feishu-meeting`，其中日历创建当时因 CLI 缺 creator 而失败，结果被如实报成
> `批准写回=2 失败=1`，失败原因写进候选的 `error:`，**没有被包装成整体成功**。

## D. 导入与来源

| # | 项 | 说明 |
|---|---|---|
| D2 | 来源面板异常矩阵（浏览器层） | 404 / 非 Markdown / 超长 / 路径穿越 / 符号链接越界 / workspace 隔离 |
| D3 | 正文截断提示的真实显示 | `truncated` 在 100,000–256 KiB 时的页面表现 |

> **D1 已部分验证（2026-09-11，见 §K）**：成功导入（含项目解析）与**幂等重跑**
> （`待导入 0 场，已跳过 3 场，约 0.0 CNY`，零模型调用）均已取得证据。
> **软预算与部分失败的导入路径仍未验证**；另发现 10 MiB 上限只做在 web/App 层，CLI 路径没有。

## E. 交互细节

| # | 项 | 说明 |
|---|---|---|
| E1 | 冲突包导出下载的确定性证据 | In-app Browser 未观测到 download 事件 |
| E2 | 原生确认框关闭后的稳定返回焦点 | CUA 通道超时，未取得 |
| E3 | 项目可移动滚动位置恢复 | 既有 fixture 高度等于视口，无位移 |
| E4 | 动态 loopback 端口变化后的同源边界 | 跨端口草稿迁移是明确不做的独立事项 |
| E5 | R01–R14 交互断言在真实页面复验 | 源码级契约测试不算真实浏览器证据 |

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

2. **10 MiB 上限只在 web/App 层（未修复）**：`legacy_app.py:2575` 有 `max_upload_bytes`，
   而 CLI 的 `scan_for_import` 只判断「非空」。本次一个 12 MiB 文件因此被真实送进模型，
   预估 **419 万 input token（约 4.24 CNY）**。CLI 是文档化入口，建议把上限下沉到 workflow 层。

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

> 该测试任务标题为「【测试】验证负责人指派（可删除）」，等产品所有者确认后可删除。

### 本轮未覆盖

- **App 抽屉 UI 层**：多文件回执、关闭重开保留、焦点归还（本轮走 CLI，未驱动界面）
- 落点 `project-followup` / `project-inbox` 未实测（`global-inbox` 未单独实测）
- 导入的**部分失败 / 软预算**路径
- C1（`0/1/100/101` 矩阵）、C2（一次点击一次请求网络计数）
- ~~合成数据尚未清理~~ → **已于 2026-09-11 清理完毕**：vault 回退到 `8dba623d`，工作树与未跟踪
  文件均为 0，`_swb-import-test/` 素材目录已删除。
- 注意：清理只作用于本地 vault；**飞书上已建的任务与日程不会随之消失**

## 已关闭（保留证据指针）

| 项 | 关闭日期 | 证据 |
|---|---|---|
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
