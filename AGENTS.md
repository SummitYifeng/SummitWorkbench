# AGENTS.md — SummitWorkbench（SWB）

> 给进入本仓库的 agent。**只写你从代码/README 里猜不到、踩过坑才知道的约束**；
> 架构与命令细节看 `README.md`。
> 基线：当前**已发布**源码提交 **`6253d31`**（2026-09-20，即 `0.4.11` / CI build `25` 的来源；
> 上一份已发布 `4e91469` → `0.4.10` / build `24`）。
> 发版走「打 tag → `release.yml`」（细节见「交付产物基线」）。
> 本版已把 2026-09-19 的**代码简化重构**一并打包（模块落点见
> `docs/implementation/LEGACY-*-SPLIT-PLAN.md` 两份 stub 的「收口现状」）；引用路径/行号前先确认
> 它在**交付提交**还是**当前 HEAD** 上成立。
> 若 HEAD 更新，先确认下面的行号与数字是否漂移——**基线的锚是那个源码提交，不是 HEAD**
> （否则「更新基线」这一动作本身会产生新提交，基线永远追不上，参见前端 build 身份的同类教训）。

## 所有权边界（硬约束）

### 下一版架构（Phase 1，2026-10-02）

- 新版 SWB 工作库是用户选择的普通本地目录或 OneDrive 目录，以 `.summit-workbench/manifest.json` 和 `conventions.md` 识别；身份跟随 manifest，不跟随绝对路径。
- 新版工作库写入只使用原子文件操作及库身份锁，不初始化 Git、不自动 commit/push，也不提供工作库 Git 同步、冲突或撤销功能。Git 仅用于 SWB 源码和发布流程。
- OneDrive 客户端负责文件同步；SWB 不把本地写盘描述为云端已同步。切换设备前由用户确认 OneDrive 已完成同步。
- 新版正式内容必须带与当前内容版本匹配的批准证明才可进入检索语料；原件、逐字稿、收件箱及辅助状态始终排除。契约见 `docs/contracts/SWB-WORKSPACE-CONTRACT-v1.md`。
- Phase 1 的代码与自动验收只使用隔离测试库。Phase 2 已获准在新的 OneDrive 样板库进行人工验收；既有真实 `_vault` 仍只作来源与备份，不改写、不提交、不推送。第二至第四阶段按实施计划的验收门顺序推进。

- **SWB 是工作知识库 `_vault` 的唯一写入方**（入库 / 审批 / 写回 / 简报）。
- **`_vault` 的规范单一真源不在本仓库**，而在另一个仓库：
  `~/Documents/Work/_vault/conventions.md`（其 **§9.1** 是 SWB ↔ SK 的接口契约）。
  写与工作库相关的代码前，**先读它**。
- **SK（SummitKnowledge）是唯一检索方**，只读工作库；不要在本仓库实现检索/向量化。

## 旧版写入 API（0.4.x Web 面板 → legacy vault）

以下接口细节记录旧库格式与 0.4.x 行为；0.5.0 起新建工作库按 `SWB-WORKSPACE-CONTRACT-v1.md` 与
当前实现工作，正式内容先按版本批准证明判定，写操作只落本地文件，不接工作库 Git。

- 日常写入入口（2026-09-19 起，契约 §4.10）：
  - **`POST /api/journal/log`** ——「日常手记」五区块形态。入参 `did` / `remaining` /
    `reflection` / `blockers`（**至少填一段**）+ 可选 `projects`；落顶层 `logs/<日期>-<seq>.md`，
    不绑项目写 `project: global`，`status: active`。某段为空不出区块；`## 关联` 恒在
    （无项目写 `- （无）`）；**单块 > 1500 字符拒绝**（超长块会被 SK 切成共享同一锚点的子块）。
  - **`POST /api/journal/thought`** ——`type: long-form-thought`，三段（`problem` / `thinking` /
    `conclusion`）都必填；落 `thinking/<YYYYMMDD>-<slug>.md`（目录按需创建，不放 `.gitkeep`），
    **落盘前**过 schema + 检索就绪 + §2.1 叠加必填；`id`/`title`/`summary`/`workstream`(默认 `cross`)
    自动填，`project: global` 或不绑项目。
- 旧版两条都经 `MutationRuntime.run`（自动 commit；`WB_NO_AUTO_PUSH=1` 关自动推送），落盘复用
  `repositories/thread_notes.append_work_log`——**不要另写一套落盘**。
- **收件箱提升通路**（2026-09-19 起，契约 §10）——`inbox.md` 的条目可以被提升为正式内容：
  - **`GET /api/inbox`** ——待处理条目 + 稳定标识 + `#项目` 解析 + capture 机器标记
    （`wb-capture-kind/-due/-project`）+ **本地启发式**的默认目标。**纯读、绝不调模型**。
  - **`POST /api/inbox/suggest`** ——**显式按钮**才调一次 `capture` 能力的模型，只给建议、不写盘。
  - **`POST /api/inbox/promote`** ——三种目标各有既有落盘实现，**不要另写第二套**：
    `project` → `repositories/writeback.py`（`## 下一步` / `## 跟进事项`）；
    `feishu-task` → `workflows/review_apply.py::create_task_through_outbox`（审批写回同一条
    outbox 路径：账本 + `candidate_id` 幂等 + 结果未知不重 POST；**库内不留可检索正文**，
    只在 `review/archive/` 留痕）；`thought` → `repositories/thought_notes.py::write_thought_note`
    （与 `/api/journal/thought` **同一实现**，第六·六阶段那套思考落盘已上移到这里；
    该模块 2026-09-19 从 `repositories/thread_notes.py` 拆出）。
    三者都必须：**同一个提交**里把条目移出 `inbox.md`、**不留占位行**（§10），且
    `changed_paths` 列全（目标页 + inbox；第七阶段的事故就是漏列）。
  - **成本线**：列表渲染不调模型；只有「让 AI 判断这条适合变成什么」这个显式按钮会花钱。
    机器守卫：`tests/unit/test_inbox_promote.py::test_read_endpoint_never_calls_the_model`
    + `web/scripts/test-browser-contract.mjs` 的**位置**守卫（`/api/inbox/suggest` 只许出现在
    `web/src/features/today/inbox.ts`）。
- **改 `web/` 之后必须 `npm --prefix web run build` 并把产物一起提交**（产物在
  `src/summit_workbench/webapp/static/`，含 `build-meta.json` 的前端身份）；只改源码不重建，
  面板上看到的还是旧界面。前端契约测试：`npm --prefix web run test:frontend`。

## ⚠️ 不要相信本仓库的历史文档

- `docs/archive/implementation/*`（2026-09-19 从 `docs/implementation/` 整体归位的 16 篇）里大量写的是
  **已被撤销**的旧结构（`clusters/`、`## 主题簇`、`hr/people`、按人页）。
  这些文件是**当时的历史计划/会话快照**，已加「结构已过时」横幅，**保留原文**，
  **不要照它判断现有目录结构**，也不要"顺手"把它们改成新结构（会伪造历史）。
  `docs/implementation/` 另含两份 SPLIT-PLAN 的**指路 stub**、OneDrive 工作台实施计划和 W0 接口／写入盘点。
  要看拆分后的模块落点看 stub 的「收口现状」，别翻 archive 里的旧行号。
- 判断当前结构**一律以 `_vault/conventions.md` 与 `_vault` 实际内容为准**。
- 仍有价值的活文档：`docs/product/WEB_USAGE_GUIDE.md`、`docs/contracts/WORK-KB-RETRIEVAL-CONTRACT.md`
  —— 这两份已按当前结构校正过，**改动结构时要同步更新它们**。

## 踩过的技术坑（改之前先看）

- **`workstream` 门禁是"按需启用"的**：`check_vault(..., work_vault=True)` 才生效
  （`cli/vault.py:39`、`cli/doctor.py:96` 已启用；开关定义在 `repositories/vault.py:99`）。
  语义：机器写入页（`logs/ artifacts/ index/*.md inbox.md review/meetings.md README.md`）
  **只豁免"必填"，值存在但越界时仍报错**。（`daily/`、`reviews/` 自 2026-09-19 起已不在库内，
  已从豁免集合删除——见「验证命令与基线」下的 `kb_verify_links` 说明与批次 A 迁移。）
- **`type: workstream` 是活的页面类型，不要当死代码删除**
  （`templates/vault/workstream.template.md` 存在，`tests/unit/test_vault_templates.py:22` 断言了它）。
  别把它与 frontmatter 的 `workstream:` **字段**混淆。
- **同步 remote 接受 `https` 与 `ssh://` / SCP-like**；仍拒绝 `http://`、`file://`、URL 含明文密码。
  网络策略是直连优先，超时则回退系统代理；`_https_pool_manager()` 只在没有 env 代理时读取 macOS 系统代理，SSH 直连可用。
  **不要动 `_vault` 的 remote，不要 force push。**
  - SCP-like（`git@host:path`）**不含 `://`**，任何用「有没有 `://`」判断"是不是远端"的代码都会把它
    误当本地路径。`git_backend.is_missing_local_remote()` 是两后端共用的正确判据（2026-09-18 踩过：
    该 bug 让 SSH remote 的 push 在联网前就报 `remote-unavailable`）。
  - `3ed9780` 只放行了 SSH 的 **scheme 门禁**，**没有**覆盖 push 路径；新增远端形状支持时必须
    同时验证 fetch 与 push（能 fetch ≠ 能 push）。
- **飞书任务时效**：审批页复用 `start_at` 作为任务开始日期；`feishu-task` 写回必须同时发送全天
  `start` 与 `due`，开始/截止字段使用日期控件，缺失时只告警不阻断批准。

- **往固定区块里插内容时，别把「区块尾随空行」留在 `lines[end:]` 里**（2026-09-19 修）：
  `writeback.py` 的两个写入器都写成「把 `end` 退到正文最后一行之后 → `[*lines[:end], 新内容,
  "", *lines[end:]]`」，而 `end` 退位后**尾随空行正好落在 `lines[end:]` 开头** ⇒ 与自己的 `""`
  叠成双空行（收件箱提升到项目页「下一步」后，与「阻塞」之间多出一个空行，真机实测）。
  现在统一走 `_block_tail(lines, start, heading_index) -> (end, tail)`：`end` 是正文终点、
  `tail` 是其后第一个**非空**行，插在 `end`、从 `tail` 续接。
  守卫：`test_promote_leaves_exactly_one_blank_line_before_the_next_block`、
  `test_set_project_status_keeps_a_single_blank_before_the_next_block`（都做过变异验证）。

- **模型侧：`max_output_tokens` 是「思考 + 答案」共用的预算**。DeepSeek-V4 系列**默认开启思考模式**
  且 `effort=high`；预算太小会被 `reasoning_tokens` 吃光 → `content` 为空 → 表面报"不符合 schema"
  （2026-09-18 真机：4096 被推理全部耗尽，且 API 当时**不返回** `finish_reason`，靠单一字段判断会漏）。
  抽取/摘要/分类类任务一律 `thinking="disabled"`；截断判定必须同时看 `output_tokens >= 上限`。
  能力清单以 `providers/llm/config.py:CAPABILITIES` 为准（含 `digest`），逐能力参数见 `config.example.toml`。

- **dulwich 1.2 把 `pool_manager` 从 `porcelain.fetch` 的签名里删了**（2026-09-19 真机，用户可见）：
  `fetch` / `push` / `clone` 三者**只有后两者**还有 `**kwargs`（`_filter_transport_kwargs` 会保留
  并转发给 `get_transport_and_path`，而后者**接受** `pool_manager`），但 `dulwich_git.py` 的 fetch
  仍按 0.22.x 的 API 把 `transport_kwargs()` 交给 `porcelain.fetch` ⇒
  `TypeError: fetch() got an unexpected keyword argument 'pool_manager'`，被 `_classify_remote`
  兜底成 **`unclassified`**，界面只说「未分类的同步失败」。
  ⇒ **自 build `2026091917`（dulwich `1.2.15` 迁移）起，打包 App × HTTPS 远端一直无法同步**。
  本地路径/SSH 远端不受影响（`transport_kwargs()` 对非 HTTPS 返回 `{}`），CLI 默认 system git
  后端也不受影响——**这正是它藏了十几版的原因**。
  修法：fetch 自己建 client —— `get_transport_and_path(url, config=repo.get_config_stack(),
  operation="fetch", **transport_kwargs)` → `client.fetch(path.encode(), repo, progress=sink.write)`
  → `cast(Any, porcelain)._import_remote_refs(...)` 落 `refs/remotes/<remote>/*`（复刻
  `porcelain.fetch` 的语义）。守卫：`tests/contract/test_dulwich_api_contract.py`
  （行为回归 + 参数面收敛 + 依赖前提三条，已变异验证：还原旧实现即红）。
  **教训**：升级依赖后，`porcelain.*` 这类"转发型"API 的签名会漂移；测试里把 `transport_kwargs`
  monkeypatch 成 `{}`、或只断言它的内容，就会让这条调用链**永远不被真实签名检阅**。
  ⇒ **见到 `unclassified` 先怀疑调用点与依赖 API 漂移，别先查网络。**
- **改 `pyproject.toml` 的 `version` 后必须跑 `uv lock`**：`uv.lock` 里记着项目版本，
  不更新会被 `pre-push` 门禁的 `uv lock --check` 拦下（2026-09-19 发 0.4.10 时踩到）。

## 当前开发与验收状态（2026-10-04）

- **2026-10-04 交接基线**：交接核对时 `main` 与 `origin/main` 均为 `1ece2cd`，工作区干净；该提交仅在 `1141155` 上新增本交接文档。此为交接起点记录，不表示后续整理后的当前 HEAD。
- **2026-10-06 进展补记**：Air 上运行 `0.5.0`、前端 `v2026.10.06-9c141154`；本轮构建记录为 build `2026100602`、源码提交 `7b50597`。Studio 截图未核实包身份。Studio → Air → Studio 日志往返已由 Air 界面与用户提供的 Studio 截图确认；Phase 3 整体未通过。用户决定当前不测任何异常，异常场景须记为未测试，不得记为通过。详见 `docs/acceptance/STUDIO-AIR-0.5-ACCEPTANCE.md`。
- Phase 1 W0–W8 已通过；Phase 2 OneDrive 样板验收已由用户确认完成。阶段证据入口见 `docs/README.md`、Phase 2 报告及上述 Phase 3 现场记录。旧真实 `_vault` 仍不做写入验收。

## ⚠️ 交付产物历史基线（2026-09-19 起，保留当时记录）

- **2026-10-03 本机 INTERNAL-DEV 包（历史，未发布）**：`0.5.0 / build 2026100307`，arm64，源码
  `b077702bee6340393194bf6783af897a576da423`，前端 `v2026.10.03-6a8114bc`；已安装到
  `/Applications/SummitWorkbench.app`。此包用于新版工作库与 OneDrive 样板，未启用自动更新；
  包身份见 `docs/acceptance/SWB-WORKBENCH-PHASE1-REPORT.md`。
- **截至当时的人工验收状态**：Phase 1 W0–W8 已通过；Phase 2 OneDrive 样板验收仍在进行，见
  `docs/acceptance/SWB-WORKBENCH-PHASE2-REPORT.md`。该样板库不是旧真实 `_vault`。

- **已发布（tag `v0.4.11`，**最新**）**：`yifeng93/SummitWorkbench-Updates` 的 **Latest** 发布，
  由 CI（`release.yml`、run `35480773191`；**第 1 次跑在 `hdiutil create` 撞上 `Resource busy`，
  直接 rerun 即全绿**——这是 macOS runner 的瞬时故障，不是代码问题）从 tag 提交 **`6253d31`** 构建；
  **build `25`**（run number）。DMG SHA-256
  `da20c6348e4b86c2010b111120f92d2ba6c794064074d334aeb1ef4fc4d5c549`（51,764,164 B）；
  App SHA-256 `d372a0218324f8c83e329ebaf5305a664bebae50dde216d086c5ddf3f3becb5e`；
  `update-feed.json` 带签名（`signature` + `public_key`）；`test-manifest.json` 13 项 `passed`。
  **本版修掉用户可见的「点已完成任务的 ✓ 弹红」**（`complete_task` 幂等，见「踩过的技术坑」）。
  发布前置：`release` environment 的 `UPDATE_DOWNLOAD_URL` 已同步到 v0.4.11（**每次发版都要先改**）。
- **已发布（tag `v0.4.10`，已被 0.4.11 取代）**：`yifeng93/SummitWorkbench-Updates` 的 **Latest** 发布，
  由 CI（`release.yml`、run `35448306057`）从 tag 提交 **`4e91469`** 构建；**build `24`**（run number）。
  DMG SHA-256 `fdc1c2ef7d3646e390c5456b7f5e542112107714704d9333a128bc05b607f719`（51,770,064 B）；
  feed 带签名。**这一版修掉了 HTTPS 远端无法同步的阻断**（见「踩过的技术坑」），
  `0.4.9`（build 23）装机的机器可在 App 内直接升级。
- **已发布（tag `v0.4.9`，已被 0.4.10 取代）**：CI run `35446664234`、build `23`、提交 `5204abf`，
  DMG SHA-256 `f5c3b65f67b46641de2468cfcb5948558c1a7ce43bc31e3c31c53705d86676a4`。
  ⚠️ 它带 HTTPS 同步阻断，**别再用它装新机器**。
  **build 号口径**：`release.yml` 用 `github.run_number`（历史发布的 19/24/29/…/50 同口径），
  **与本机 INTERNAL-DEV 包的 `yyyyMMddNN` 是两套编号，别混**。
  发布前置：`release` environment 的 `UPDATE_DOWNLOAD_URL` 必须等于**按 tag 算出的**期望值
  （`.../releases/download/<tag>/SummitWorkbench-<version>-arm64-INTERNAL-DEV.dmg`），否则
  `Prepare protected update configuration` 步直接 FAIL（每次发版都要先同步它）。
- **本机 INTERNAL-DEV 构建（2026-09-20，未发布；`update_feed` 为空 → 不接自动更新）**：
  `0.4.10 / build **2026092001**`（`INTERNAL-DEV`、arm64、ad-hoc），由 **`10bec79`** 构建
  （`release-metadata.json` 的 `git_commit` 即此值，可直接复核）；前端身份 **`v2026.09.20-d1a8ace7`**；
  包内**已内置飞书默认凭据**（`build-manifest.json` 的 `feishu_credentials.complete=true`），
  `test-manifest.json` 的 13 项检查全过，SHA-256 见下一条。
  **本版含一个用户可见的修复**：工作台「今日」点待办「✓」不再对**飞书侧已完成**的任务弹红——
  `complete_task` 改为幂等（PATCH 被拒后只读复核，确为完成态即按成功返回；真机报错
  `Invalid Param 'task.completed_at', cannot set non-zero completed_at for a completed task`）。
  本机 `/Applications/SummitWorkbench.app` 当前**正是本包（`2026092001`，用户已装机并实测通过）**；
  但它 `update_feed` 为空 ⇒ **不接自动更新**；要跟上已发布的 `0.4.11` 需手动装 v0.4.11 的 DMG
  （装过一次带 feed 的发布包后，后续版本即可在 App 内升级）——别把 CI 的 `run_number` 与本机
  `yyyyMMddNN` 两套 build 编号混为一谈。
- **上一版本机 INTERNAL-DEV 构建**：`0.4.9 / build **2026091925**`（`e62d3a3`，
  前端 `v2026.09.19-d1a8ace7`；本机旧装机曾为 `2026091923`＝`0c9ff4f` / 前端 `v2026.09.19-4a04d298`，
  该版只改后端，故身份与更早一版相同，别把"身份没变"当成"产物没重建"）。
  **本版含两个用户可见的修复**：① 手工写进 `inbox.md` 的条目现在也按正文 `#项目` 走默认目标
  （上一版会默认判成「一篇工作思考」，见待办 8）；② 写回项目页的条目与下一个区块之间不再多出
  一个空行（`_append_under_heading` / `set_project_status` 的双空行，见「踩过的技术坑」）。
  上一版 `e1700e2` → build `2026091922` 新增【今日】页的「收件箱（N 条）」块与「提升为…」弹层
  （契约 §10）；再上一版 `375ce98` → build `2026091921` 含两个修复：写日志不再留下未提交的项目页
  （`changed_paths`）、以及「撤销历史」面板在打包 App（dulwich 后端）上**从空变有**。
  更早的交付依次是 `7b7df74` → build `2026091920`、`f710aca` → build `2026091919`（新增两个写入入口）、
  `a49bb42` → build `2026091918`（批次 A 语料边界）、`2d1cf3a` → `2026091917`
  （Dulwich `1.2.15` 迁移 + 日常 CI 收窄为手动触发）。
  原生壳自 build `2026091813` 起**保留 Dock 图标**（`LSUIElement=false` + `.regular`），
  `WB_DOCK_ICON=0` 可退回菜单栏模式。
- **本机重建必须带内置飞书凭据**：默认 `REQUIRE_BUNDLED_FEISHU=true`，缺
  `WB_FEISHU_APP_ID` / `WB_FEISHU_APP_SECRET` 会在**打包阶段**才失败（前面几十分钟的测试与
  PyInstaller 全白跑 —— 2026-09-19 批次 A 交付实测踩到）。凭据从**上一个含内置凭据的包**里取证、
  不手抄、不落仓库，步骤见 `docs/RELEASING.md`（本次即用它从装机版包内 `feishu-defaults.json`
  生成 0600 临时 env）。另外 `release-macos.sh` 要求**显式** `BUILD_NUMBER`，且**拒绝覆盖已存在的
  发布目录**（要重建同一版本须先移除旧目录）。
- `dist/` **只保留最新一份**：`releases/0.4.10/arm64/`；build `2026092001` 的
  **App SHA-256 为 `b733d44ea94d66e3affd1b833c00a3e5c9b259ab2b4af98aff6ef8b19f8fa579`**，
  **DMG SHA-256 为 `edde2100213ca1f2749d6705dd2e6c62fb9ad02d15519171cebc92165034bdfb`**（52,099,332 B）
  （**以 `release-metadata.json` 的 `sha256` 为准**：`SHA256SUMS` 只覆盖 DMG 与元数据文件、不含 App）。
  旧发布目录按惯例移到 `/tmp`（`release-macos.sh` 拒绝覆盖同名目录）：
  `2026091925`（`e62d3a3`，App `ca58c846…` / DMG `6c31855d…`）→ `/tmp/swb-releases-0.4.9-2026091925`；
  `2026091923`（`0c9ff4f`，App `a7f35b32…` / DMG `78e39964…`）→ `/tmp/swb-releases-0.4.9-2026091923`；
  `2026091924`（`c9b3fc5`，App `91ed6e8e…` / DMG `87f27884…`，只进过 dist、未装机也未入档）
  → `/tmp/swb-releases-0.4.9-2026091924`；`2026091922`（App `21db9aa7…` / DMG `a98de539…`）
  → `/tmp/swb-releases-0.4.9-2026091922`。
  装机包内**真实**依赖以发布目录的 `SBOM.json` 为准（本版依赖与前一版相同：
  `dulwich==1.2.15`、`uvicorn==0.53.0`、`pyinstaller==6.22.3`、`ruff==0.16.7`、`hypothesis==6.168.0`）。

- **设置页布局是使用者的显式偏好**（2026-09-18）：主区只放 工作区 / AI 模型 / 飞书
  三张卡且**每张一行**（`.settings-grid-single`）；「自动化与更新」「模型参数（只读）」在
  页面下方的「高级与维护」折叠区里。机器守卫在 `web/scripts/test-browser-contract.mjs`。

## 付费与不可逆动作

- 本仓库**不产生嵌入费用**（检索已退役）。但**工作库的索引由 SK 负责**：
  **一次全量重嵌会真实调用云端嵌入接口花钱** —— 不要为了验证而触发。
- 不要 `git push` 用户的 `_vault`，除非任务明确要求。

## 验证命令与基线（交付提交 `6253d31`）

```bash
./.venv/bin/python -m pytest -q                 # 实测 1403 passed, 1 skipped（6253d31）
./.venv/bin/python -m pytest -q --cov           # 实测 84.56%（门槛 80%，同一 commit）
./.venv/bin/ruff check && ./.venv/bin/ruff format --check && ./.venv/bin/mypy src
./.venv/bin/wb vault check ~/Documents/Work/_vault   # 判据是"全部通过"，篇数随写入增长（当前 86）
./.venv/bin/python scripts/kb_check_contract.py --vault ~/Documents/Work/_vault
./.venv/bin/python scripts/kb_verify_links.py ~/Documents/Work/_vault
./.venv/bin/python scripts/kb_check_templates.py --templates ~/Documents/Work/_vault/templates
./.venv/bin/python scripts/kb_check_decision_hygiene.py          # 期望：19 篇决策页无库机制描述
```
数字会随开发变化：**报基线时务必带上你所测的 commit**，并说明如何重测。
（`release-macos.sh` 内部另跑一份较窄的 pytest 子集，数量少于上表的全量数，别把两者当矛盾——
所以这里**不写死**那个子集数。）

> **`kb_verify_links.py` 的覆盖范围（2026-09-19 修过一次静默回归）**：覆盖 `[[目标#区块]]`、
> `` `路径#区块` ``，以及**有唯一来源上下文**的裸锚点 `` `#区块` ``；**不覆盖** `###` 及更深的
> 锚点（契约只把 `#`/`##` 当块边界，`_vault/conventions.md` §13 遗留 12），以及**没有/无法唯一
> 确定来源页**的裸锚点（§13 遗留 13）。判据是 `source_context()`：**扫全篇「来源标记行」**
> （拉丁词用词界，否则路径里的 `sources/` 会被当成 "source" 标记）→ 全篇唯一则用它；多个候选时
> 收敛到**开头区块**声明的那个；候选必须能解析且**不是本页自身**。
> ⚠️ 它曾"只看首块"，第五阶段把 H1 前的前言并进第一个 `##` 后，裸锚点计数 **56 → 0**：
> 门禁不再校验那两页，却仍报"全部可解析"。**看输出时务必核对"裸锚点 N 条"这个数**——
> 期望 **56**；掉到 0 就是覆盖又断了，不是"库变干净了"。

> **改 `_vault` 结构（新增/删除目录、增删项目、增删 type）时，除上面的命令外还要跑
> `scripts/kb_check_contract.py --vault …`**（只读）。它把 `conventions.md` 声明的
> 目录/类型与库内实际比对，并**刻意分两层**：**FAIL** = 契约错/自相矛盾/与库内硬冲突
> （如项目页集合对不上、已撤销目录又出现在 §1 树、库内出现契约未声明的 type）；
> **WARN** = 契约已声明但按需创建、库内还没有（如 `thinking/`、0 篇的 `long-form-thought`）。
> 别把 WARN 当缺陷修掉——那正是它存在的意义（第一阶段若不分层就会被误报挡住）。

> **vault check 由 86 改为 84（2026-09-19，批次 A）**：`daily/2026-09-18.md` 与
> `daily/2026-09-19.md` 已按新契约（简报不在库内）逐字搬到本机程序目录
> `profile_dir(<workspace_id>)/briefs/` 后从库内 `git rm`，空 `reviews/` 一并移除。
> 86 − 2 = 84。
> **注：84 是批次 A 当时的瞬间值。**此后 `logs/`（日常手记）与 `thinking/`（工作思考）的真实写入
> 又把它涨回 **86**（2026-09-19 实测，与上面「当前 86」一致）——篇数只反映库里有多少页，
> **不是契约判据**；判据始终是"全部通过"。

**`uv sync` 会按 extras 收窄依赖，裸跑会卸掉构建工具**：dev 工具在 `dev` extra、
PyInstaller 在 `packaging` extra、Web 面板在 `web` extra。裸 `uv sync` 或
`uv sync --extra dev` 会把 `.venv` 里其余 extra 的包**卸载掉**（2026-09-19 踩过：PyInstaller
被卸，`release-macos.sh` 一路跑到打包步才报 `No module named PyInstaller`）。
**构建或跑门禁前统一用 `uv sync --extra dev --extra web --extra packaging`。**

**⚠️ 旧版 0.4.x 写入曾自动 commit + push legacy vault**（2026-09-19 真实事故；0.5.0 已退役此链路）：
`webapp/mutation_runtime.py` 的 `_push_after_commit` 把所有写路径（capture / 任务编辑 /
审批写回……）在 commit 之后接到 `sync_coordinator.push_after_commit`。这是日常使用应有的
行为，但**验证动作不该顺带推送**——当时闸门加了 `--no-push` 仍被运行中的 App 自动推送，
验证件与本地未推提交一起进了 `origin/main`。三条纪律：

1. **验证不要打运行中的 App**：App 构建新版本前没有下面这个开关，capture 必然推送。
2. **用源码起一个带 `WB_NO_AUTO_PUSH=1` 的服务**，再用 `--swb-url` / `--swb-token` 指过去。
3. **开关语义**：`WB_NO_AUTO_PUSH=1`（也接受 `true`/`yes`/`on`）→ commit 照常、**不自动 push**；
   跳过会写服务日志 `auto_push_skipped`，并在响应里带 `auto_push: {skipped: true, note: "（已跳过自动推送…）"}`。
   **绝不允许把它记成同步成功（`ready`）**——跳过发生在 push 之前，同步状态机不参与。
   默认不设 = 行为完全不变。显式 `/api/sync/run`、`wb sync` 不受影响。

**legacy vault 跨端回归闸门**（跨旧版 SWB × `_vault` × SK，**会写库并花一次极小模型费用**；新版 Phase 1 不运行）：

```bash
# 验证姿势（推荐）：源码服务 + 不自动推送 + 收尾不推
WB_NO_AUTO_PUSH=1 WB_SESSION_TOKEN=... \
    ./.venv/bin/python -m summit_workbench.cli.main web --host 127.0.0.1 --port 8791 &
./.venv/bin/python scripts/kb_three_end_gate.py \
    --swb-url http://127.0.0.1:8791 --swb-token ... --no-push-cleanup
# 其它开关
./.venv/bin/python scripts/kb_three_end_gate.py --keep        # 保留验证件供人工查看
./.venv/bin/python scripts/kb_three_end_gate.py                # 默认：收尾清理提交会 push vault
```
预检会**醒目打印**本次写入打的是哪个 SWB 端点、该端点是否启用了 `WB_NO_AUTO_PUSH`；
收尾会打印 vault `origin/main` 前后取值，**未启用推送模式却发生变化时判 FAIL**（不是告警——
只看退出码也要能发现"验证意外推送了 vault"）。`[1/8]` 把 `state=local-ahead` 当 **WARN**
（本机有未推送提交正常且安全，推荐的验证姿势本身就会制造它，判 FAIL 会导致第二次跑闸门必挂）。
另外 `--no-push` 是 `--no-push-cleanup` 的弃用别名（旧名容易被误读为"整个闸门不推送"，
实际只关收尾那一推）。**闸门共 8 步（`[1/8]`…`[8/8]`）**：只有 `[2/8]` 的 capture 会调一次
极小模型；`[3/8]`（日志）与 `[4/8]`（收件箱提升）都是纯本地写盘，**不调模型、不花钱**。

一句话验完八类曾经"测试全绿却发生"的不变量：① 真实写入后**工作树干净**（S-1(a)）；
② `_signals/` **未被回跟踪**（S-1(b)）；③ 逐字稿与 `inbox.md` **不进语料**（P1-4）；
④ 精排**真的生效**且结果里无 `meeting-transcript`（P0-4）；
⑤ **原件（`<project>/sources/`）与 `daily` / `weekly-review` 不进语料**（批次 A 语料边界）；
⑥ **来源白名单覆盖真实库的全部主线项目**（`thinking` 在内；这条只在有真实库的环境成立，
故放在闸门而不是只做单元测试）；
⑦ **`/api/journal/log` 写入后工作树干净、关联项目页（若本次确实被改动）与日志页同一个
提交、落盘页面只有一个「关联」区块**（第七阶段新增，第八阶段把判据改精确；`[3/8]` 这一步
**不调用模型所以不花钱**）。"若本次确实被改动"是必须的：`_touch_projects_activity` 只刷
`activity_at`，而 `update_note_status` 的重写**幂等** ⇒ 同一天第二次写日志时项目页根本不变，
"提交里没有项目页"是**正确行为**（2026-09-19 真机实跑就是被这条假阴性挡住的）。
⑧ **`POST /api/inbox/promote`（`project` 目标）之后工作树干净、`inbox.md` 与
`projects/<项目>.md` 在**同一个提交**里、条目移出收件箱且不留占位行/不产生双空行、
目标页无双空行且 `wb-candidate` 幂等键出现且只出现一次**（第九阶段新增，落在 `[4/8]`）。
**只测 `project` 目标：闸门绝不在使用者的飞书里建真实待办**（`feishu-task` 目标有外部副作用，
`thought` 目标与 `/api/journal/thought` 共用落盘实现，两者留给单元测试）；这一步**不调模型、
不花钱**。
第 ⑦⑧ 条迟到的原因值得记住：闸门原来只覆盖 `capture`（写 `inbox.md`）这一条写路径，而
**新增写入口不会自动被覆盖**——journal 路径漏列 `changed_paths` 就是这样在"闸门全绿"的
情况下漏掉的；第九阶段的 `inbox/promote` 写路径同理，现已纳入 `[4/8]`（它必须排在 `[6/8]`
的 `pending_index` 记账**之前**，因为提升写下的项目页也是语料文件）。改了 vault 写路径、
git 后端、检索策略、来源白名单或 SK 端点配置之后**跑它**。

## 内容层面的硬规则（2026-09-18 使用者定规）

- **决策页只记业务结论**：`decisions/*.md` 正文**禁止**出现知识库自身机制的描述
  （「本库 / 归属判定 / 素材落点 / 双链 / 不设两份 / 闭掉未决条目 / 检索侧 / 入库管线」等）。
  决策回答"业务上定了什么"，不是"材料该放哪一页"——后者归 `conventions.md` §1.1。
  机器守卫：`scripts/kb_check_decision_hygiene.py`（维护 vault 时运行，命中即 exit 1）。
- **会议笔记不再生成 `## AI 建议`**（`meeting-note` 由九区块减为八区块）：模型推断的下一步不入库；
  确需成为结论时人工提炼为决策。历史笔记里的该区块仍合法（区块标题只增不减）。
  改这条契约要同时动：`domain/vault.py` 的 `NOTE_TYPES`（`optional_blocks`）、
  `repositories/meeting_note.py` 的渲染器、`prompts/meeting-processor.md`、两份模板，
  以及 `tests/unit/test_meeting_note.py` 的两条守卫。

## 已知待办（下一批一起做）

1. **`.venv` CLI 与打包 App 的 git 后端不同**（提示，非缺陷）：打包 App 固定 dulwich
   （`git_backend.py:207`），CLI 默认 system。改 git 语义时必须**两个后端都验**
   （已有跨后端参数化测试，保持它）。

2. ~~**跨端闸门的三个判据缺陷**~~ —— **已修（2026-09-19 第六·五阶段，提交见本批 `fix:`）**：
   ① 前置步骤的 `state=local-ahead` 降为 **WARN**（"本机有未推送提交"正常且安全，且推荐验证姿势
   本身就会制造它——判 FAIL 会让第二次跑闸门必挂）；② `[推送守卫]` 改为 **FAIL**（只看退出码也要
   能发现"验证意外推送了 vault"）；③ 新增**结构性守卫**
   `tests/unit/test_auto_push_switch.py::test_auto_push_goes_through_the_single_gated_outlet`
   ——AST 扫 `src/`，把"允许直接调 `sync_coordinator.push_after_commit` 的调用点"钉成白名单
   （`mutation_runtime._push_after_commit` + `routers/sync_conflicts.py::api_sync_conflict_recover`
   的显式恢复推送；后者 2026-09-19 前在 `routers/sync.py`，重构后 `sync.py` 已无该调用点），新增绕过出口的
   调用点会立刻变红。

3. ~~**闸门 `[3/8]` 的日期相关假阴性断言**~~ —— **已修（2026-09-19 第八阶段）**：
   它曾断言"日志提交必须一并包含关联项目页"。但 `_touch_projects_activity` 只刷新 `activity_at`，
   而 `update_note_status` 的重写是**幂等**的 ⇒ 同一天第二次写日志时项目页不再变化，
   于是"提交里没有项目页"是**正确行为**、断言却判 FAIL（真机实跑：
   `❌ 日志提交一并包含关联项目页 — HEAD 触及：['logs/2026-09-19-002.md']`）。
   修法：`[3/8]` 在写入前后各读一次项目页字节，**只有内容确实变了才要求它进同一个提交**；
   "写入后工作树干净（S-1(a)）"**原样保留、未弱化**（它才是真正防住原缺陷的那条）。
   守卫：`tests/unit/test_kb_gate_helpers.py::test_gate_journal_write_tolerates_idempotent_project_page`
   （真实 router 连写两次；断言第二次项目页字节不变、走"未变化"分支、零 FAIL、工作树干净）。

4. ~~**`dulwich` 后端的 `log_grep` 语义与 system 不一致（用户可见）**~~ —— **已修（2026-09-19 第八阶段）**：
   `autocommit._WB_PREFIX_GREP = "^wb:"`；system 走 `git log --grep`（**正则**，且 `^`/`$` 按
   **消息的每一行**锚定），dulwich 原是 `needle in subject`（**字面子串**、且只看主题）⇒ 打包 App
   （固定 dulwich）里 `list_wb_commits()` 恒返回 `[]`、**「撤销历史」面板空白**。
   修法：`dulwich_git.log_grep` 改为 `re.search(pattern, 整条消息, re.MULTILINE)`，主题按
   `git log --pretty=%s` 规则算（`_git_subject`：首个空行前的整段、换行折空格、续行缩进保留）。
   **残留差异（未修，已登记）**：git 用 POSIX ERE、这里用 Python `re`，`\d` / `\w` / lookaround
   等写法两者不同；生产上只用 `^wb:`，两种 flavour 一致。
   守卫：`tests/unit/test_git_backends.py::test_log_grep_semantics_agree_across_backends`
   （两后端 × 7 个模式，含把 `wb:` 放进正文的那一行）。

5. **`update_note_status` 会重排整个 frontmatter**（噪音，非缺陷）：它用 `yaml.safe_dump`
   整篇重写，于是"只刷 `activity_at`"会把 `tags: [a, b]` 这类 flow style 变成 block style。
   证据：一次"一行改动"的提交实际 diff 是 11 insertions / 3 deletions。不影响正确性。

6. **`mutation_invariant` 兜底的两个固有弱点**（既有设计，登记）：它在**提交之后**才跑
   （只能报错、不能阻止工作树变脏）；且用"新脏路径 − 写入前脏路径"判定，
   **被改动文件若此前已脏则完全静默**。⇒ 新增写路径时务必自己列全 `changed_paths`，
   不要指望这条兜底。

7. **`log_grep` 返回的时间字段在两后端语义不同**（2026-09-19 修 `log_grep` 时发现，未修）：
   system 侧用 `%aI`（**author** 时间），dulwich 侧用 `commit.commit_time`（**committer** 时间）。
   SWB 自己写的提交两者相同（`commit_paths` 同时给 author/committer），所以现有守卫
   （system 写库、`GIT_AUTHOR_DATE == GIT_COMMITTER_DATE`）**覆盖不到这个差异**；
   若将来出现 author≠committer 的提交（手工造、别的工具写），两后端返回的第二项会不同。
   要修的话需先确认"该返回哪个时间"（撤销面板的展示语义），别只改一侧。

8. ~~**手工写进 `inbox.md` 的条目拿不到 `#项目` 启发式**~~ —— **已修（2026-09-19，
   提交 `0c9ff4f`）**：`repositories/inbox.py` 的 `project` / `due` **只认 `wb-capture-*`
   机器标记**，而 `suggest_promotion` 第 2 条规则写的是「有 `#项目` ⇒ `project`」，`inbox.md`
   的抬头又**明确邀请**手写 `- [ ] 想法内容 #项目名` ⇒ 手工条目被默认判成「一篇工作思考」。
   修法：`routers/inbox.py::_with_text_project`（标记优先、正文标签兜底）在读端点的启发式、
   `project` 目标取项目、`feishu-task` 的 `target_project` 三处**共用同一个回退值**，
   于是「默认选中什么」与「不给项目字段时落到哪」不再各说各话；`repositories/inbox.py`
   仍是纯逻辑（不读盘、不解析标签）。
   守卫：`tests/unit/test_inbox_promote.py::test_hand_written_entry_uses_its_project_tag`
   （变异验证：去掉回退即红）。**`due` 仍然只认标记**——手工条目无法在本地凭空算出截止日期，
   要 AI 判断就点弹层里的显式按钮。

9. ~~**`git push` 的 pre-push 钩子在 Swift 一步必挂**~~ —— **已修（2026-09-19，提交见本批
   `fix(scripts)`）**。症状：`git push` → `.git/hooks/pre-push` → `scripts/pre-push-gate.sh` →
   `scripts/test-native-updates.sh` 报 `error: failed to build module 'Swift'; this SDK is not
   supported by the compiler`（CLT SDK 是 MacOSX27.0 / Swift 6.4，编译器是 6.3.3），
   随后 `error: failed to push some refs`。
   - **根因（非显然，值得记住）**：**macOS 的 git 包装器在跑钩子时会导出
     `SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk`**，并把
     `…/Xcode.app/Contents/Developer/usr/libexec/git-core` 插到 `PATH` 最前
     （把钩子环境的 `env` 打出来一比就看见）。该 SDK 比当前编译器新 ⇒ `xcrun swiftc` 去加载
     **arm64e** slice 的 `Swift.swiftinterface`，于是报"SDK 与编译器不匹配"，而脚本里给的
     `-target arm64-apple-macosx13.0` 形同虚设。
   - 这就是"**前台单独跑必过（4/4）、挂在 `git push` 后面必挂（3/3）**"的全部原因——
     不是偶发，是环境注入；复现命令：`SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk
     bash scripts/test-native-updates.sh`（修复前 exit 1，修复后 exit 0）。
   - 修法：`test-native-updates.sh` 里改成 **`env -u SDKROOT xcrun swiftc …`** 并写明理由——
     这一步只做行为测试、编译目标固定为 macosx13.0，没有理由听凭环境变量改 SDK；
     去掉后由 `xcrun` 按当前工具链正常解析（**CLT-only 的机器同样成立**，所以不要改成
     `-sdk "$(xcode-select -p)/Platforms/…"`，CLT 没有 `Platforms/` 目录）。
   - 教训：**钩子环境 ≠ 你的 shell 环境**。门禁脚本在 "git 里挂、外面过" 时，先把钩子环境的
     `env` 打出来跟自己的比——别急着怀疑代码或 `--no-verify`。

- **远端日常 CI 永久手动触发**：`.github/workflows/ci.yml` 只保留 `workflow_dispatch`；push/PR
  不会自动消耗 runner。推送前必须通过 `scripts/pre-push-gate.sh`，需要远端复核时显式运行
  `gh workflow run ci.yml --ref main`。release workflow 的 tag 触发策略不变。
  - 其 `macOS arm64 contract` 步**故意不内置飞书凭据**（`REQUIRE_BUNDLED_FEISHU=false` +
    `ALLOW_INCOMPLETE_FEISHU_DEV=true`，**两者必须成对**：`build-macos-app.sh:41` 只给一个会硬失败）。
    原因：凭据只存在于 `release` environment，而它的部署策略**只允许 `v*` 标签**，`main` 上的手动
    CI 取不到——2026-09-19（账单恢复后第一次真跑）暴露该步**从引入起就没有通过的可能**，红线会淹没真失败。
    守卫 `tests/contract/test_ci_contract.py::test_arm64_ci_build_opts_out_of_credentials_and_cannot_distribute`
    同时钉住「该 job 不得 `upload-artifact`」，保证不含内置凭据的包永不进入分发面。
    凭据已于 2026-09-19 恢复（run `35444857578` 起 4/4 全绿）。

## 提交纪律

- 用 `type: 中文描述`（如 `fix: 同步门禁支持 SSH remote`）。**不要 push 本仓库**除非任务明确要求。
- **改任何 `##` 区块标题前，先看 SK 的区块标题词表**（它写死在
  `SummitKnowledge/retriever.py` 的 `NAV_HEADINGS` / `CONCLUSION_HEADING_PREFIXES`），
  否则会**静默改变检索加权**。
- 判断"要不要修"用 `_vault/conventions.md` §13「缺陷修复判据」：
  第 ① 类（持续制造新错误）必须修并补机器守卫；第 ② 类（只污染历史）登记即可，不必回头重做。
