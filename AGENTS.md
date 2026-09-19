# AGENTS.md — SummitWorkbench（SWB）

> 给进入本仓库的 agent。**只写你从代码/README 里猜不到、踩过坑才知道的约束**；
> 架构与命令细节看 `README.md`。
> 基线：当前交付源码提交 **`7b7df74`**（2026-09-19，即安装包 build `2026091920` 的来源；
> 上一份是 `f710aca` → build `2026091919`（新增两个写入入口），再上份 `a49bb42` → build `2026091918`）。
> 若 HEAD 更新，先确认下面的行号与数字是否漂移——**基线的锚是那个源码提交，不是 HEAD**
> （否则「更新基线」这一动作本身会产生新提交，基线永远追不上，参见前端 build 身份的同类教训）。

## 所有权边界（硬约束）

- **SWB 是工作知识库 `_vault` 的唯一写入方**（入库 / 审批 / 写回 / 简报）。
- **`_vault` 的规范单一真源不在本仓库**，而在另一个仓库：
  `~/Documents/Work/_vault/conventions.md`（其 **§9.1** 是 SWB ↔ SK 的接口契约）。
  写与工作库相关的代码前，**先读它**。
- **SK（SummitKnowledge）是唯一检索方**，只读工作库；不要在本仓库实现检索/向量化。

## 写入 API（Web 面板 → vault）

- 日常写入入口（2026-09-19 起，契约 §4.10）：
  - **`POST /api/journal/log`** ——「日常手记」五区块形态。入参 `did` / `remaining` /
    `reflection` / `blockers`（**至少填一段**）+ 可选 `projects`；落顶层 `logs/<日期>-<seq>.md`，
    不绑项目写 `project: global`，`status: active`。某段为空不出区块；`## 关联` 恒在
    （无项目写 `- （无）`）；**单块 > 1500 字符拒绝**（超长块会被 SK 切成共享同一锚点的子块）。
  - **`POST /api/journal/thought`** ——`type: long-form-thought`，三段（`problem` / `thinking` /
    `conclusion`）都必填；落 `thinking/<YYYYMMDD>-<slug>.md`（目录按需创建，不放 `.gitkeep`），
    **落盘前**过 schema + 检索就绪 + §2.1 叠加必填；`id`/`title`/`summary`/`workstream`(默认 `cross`)
    自动填，`project: global` 或不绑项目。
- 两条都经 `MutationRuntime.run`（自动 commit；`WB_NO_AUTO_PUSH=1` 关自动推送），落盘复用
  `repositories/thread_notes.append_work_log`——**不要另写一套落盘**。
- **改 `web/` 之后必须 `npm --prefix web run build` 并把产物一起提交**（产物在
  `src/summit_workbench/webapp/static/`，含 `build-meta.json` 的前端身份）；只改源码不重建，
  面板上看到的还是旧界面。前端契约测试：`npm --prefix web run test:frontend`。

## ⚠️ 不要相信本仓库的历史文档

- `docs/implementation/*` 里大量写的是**已被撤销**的旧结构
  （`clusters/`、`## 主题簇`、`hr/people`、按人页）。
  这些文件是**当时的历史计划/会话快照**，已加「结构已过时」横幅，**保留原文**，
  **不要照它判断现有目录结构**，也不要"顺手"把它们改成新结构（会伪造历史）。
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

- **模型侧：`max_output_tokens` 是「思考 + 答案」共用的预算**。DeepSeek-V4 系列**默认开启思考模式**
  且 `effort=high`；预算太小会被 `reasoning_tokens` 吃光 → `content` 为空 → 表面报"不符合 schema"
  （2026-09-18 真机：4096 被推理全部耗尽，且 API 当时**不返回** `finish_reason`，靠单一字段判断会漏）。
  抽取/摘要/分类类任务一律 `thinking="disabled"`；截断判定必须同时看 `output_tokens >= 上限`。
  能力清单以 `providers/llm/config.py:CAPABILITIES` 为准（含 `digest`），逐能力参数见 `config.example.toml`。

## ⚠️ 交付产物基线（2026-09-19）

- 本机 `/Applications/SummitWorkbench.app` 为 `0.4.9 / build 2026091920`（`INTERNAL-DEV`、arm64、ad-hoc），
  由 `7b7df74` 构建（`release-metadata.json` 的 `git_commit` 即此值，可直接复核）；前端身份仍为
  **`v2026.09.19-a99f4166`**（本版未改前端）；包内**已内置飞书默认凭据**
  （`build-manifest.json` 的 `feishu_credentials.complete=true`）。
  更早的交付依次是 `f710aca` → build `2026091919`（新增写日志/写工作思考入口）、
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
- `dist/` **只保留最新一份**：`releases/0.4.9/arm64/`；build `2026091920` 的
  **App SHA-256 为 `abc12e30850ef02cb7ac93ac5130cc6f83b376dc2e13eb1e960fab282b44aa6a`**，
  **DMG SHA-256 为 `d3ed49316516dc85e1d2b448772abd8e7704a553a12e0c2c198331d812336d90`**
  （**以 `release-metadata.json` 的 `sha256` 为准**：`SHA256SUMS` 只覆盖 DMG 与元数据文件、不含 App）。
  装机包内**真实**依赖以发布目录的 `SBOM.json` 为准
  （build `2026091920` 实测 `dulwich==1.2.15`、`uvicorn==0.53.0`、`pyinstaller==6.22.3`、
  `ruff==0.16.7`、`hypothesis==6.168.0`，与前三版相同）。

- **设置页布局是使用者的显式偏好**（2026-09-18）：主区只放 工作区 / AI 模型 / 飞书
  三张卡且**每张一行**（`.settings-grid-single`）；「自动化与更新」「模型参数（只读）」在
  页面下方的「高级与维护」折叠区里。机器守卫在 `web/scripts/test-browser-contract.mjs`。

## 付费与不可逆动作

- 本仓库**不产生嵌入费用**（检索已退役）。但**工作库的索引由 SK 负责**：
  **一次全量重嵌会真实调用云端嵌入接口花钱** —— 不要为了验证而触发。
- 不要 `git push` 用户的 `_vault`，除非任务明确要求。

## 验证命令与基线（交付提交 `7b7df74`）

```bash
./.venv/bin/python -m pytest -q                 # 实测 1353 passed, 1 skipped
./.venv/bin/python -m pytest -q --cov           # 实测 84.31%（门槛 80%）
./.venv/bin/ruff check && ./.venv/bin/ruff format --check && ./.venv/bin/mypy src
./.venv/bin/wb vault check ~/Documents/Work/_vault   # 判据是"全部通过"，篇数随写入增长（当前 86）
./.venv/bin/python scripts/kb_check_contract.py --vault ~/Documents/Work/_vault
./.venv/bin/python scripts/kb_verify_links.py ~/Documents/Work/_vault
./.venv/bin/python scripts/kb_check_templates.py --templates ~/Documents/Work/_vault/templates
./.venv/bin/python scripts/kb_check_decision_hygiene.py          # 期望：19 篇决策页无库机制描述
```
数字会随开发变化：**报基线时务必带上你所测的 commit**，并说明如何重测。
（`release-macos.sh` 内部另跑一份较窄的 pytest 子集，数量少于上表的 1262，别把两者当矛盾。）

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

**`uv sync` 会按 extras 收窄依赖，裸跑会卸掉构建工具**：dev 工具在 `dev` extra、
PyInstaller 在 `packaging` extra、Web 面板在 `web` extra。裸 `uv sync` 或
`uv sync --extra dev` 会把 `.venv` 里其余 extra 的包**卸载掉**（2026-09-19 踩过：PyInstaller
被卸，`release-macos.sh` 一路跑到打包步才报 `No module named PyInstaller`）。
**构建或跑门禁前统一用 `uv sync --extra dev --extra web --extra packaging`。**

**⚠️ 任何经 App / Web 的写入都会自动 commit + push vault**（2026-09-19 真实事故）：
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

**跨端回归闸门**（跨 SWB × `_vault` × SK，**会写 vault 并花一次极小模型费用**）：

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
只看退出码也要能发现"验证意外推送了 vault"）。`[1/7]` 把 `state=local-ahead` 当 **WARN**
（本机有未推送提交正常且安全，推荐的验证姿势本身就会制造它，判 FAIL 会导致第二次跑闸门必挂）。
另外 `--no-push` 是 `--no-push-cleanup` 的弃用别名（旧名容易被误读为"整个闸门不推送"，
实际只关收尾那一推）。

一句话验完七类曾经"测试全绿却发生"的不变量：① 真实写入后**工作树干净**（S-1(a)）；
② `_signals/` **未被回跟踪**（S-1(b)）；③ 逐字稿与 `inbox.md` **不进语料**（P1-4）；
④ 精排**真的生效**且结果里无 `meeting-transcript`（P0-4）；
⑤ **原件（`<project>/sources/`）与 `daily` / `weekly-review` 不进语料**（批次 A 语料边界）；
⑥ **来源白名单覆盖真实库的全部主线项目**（`thinking` 在内；这条只在有真实库的环境成立，
故放在闸门而不是只做单元测试）；
⑦ **`/api/journal/log` 写入后工作树干净、关联项目页（若本次确实被改动）与日志页同一个
提交、落盘页面只有一个「关联」区块**（第七阶段新增，第八阶段把判据改精确；`[3/7]` 这一步
**不调用模型所以不花钱**）。"若本次确实被改动"是必须的：`_touch_projects_activity` 只刷
`activity_at`，而 `update_note_status` 的重写**幂等** ⇒ 同一天第二次写日志时项目页根本不变，
"提交里没有项目页"是**正确行为**（2026-09-19 真机实跑就是被这条假阴性挡住的）。
第 ⑦ 条迟到的原因值得记住：闸门原来只覆盖 `capture`（写 `inbox.md`）这一条写路径，而
**新增写入口不会自动被覆盖**——journal 路径漏列 `changed_paths` 就是这样在"闸门全绿"的
情况下漏掉的。改了 vault 写路径、git 后端、检索策略、来源白名单或 SK 端点配置之后**跑它**。

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
   （`mutation_runtime._push_after_commit` + `routers/sync.py` 的显式恢复推送），新增绕过出口的
   调用点会立刻变红。

3. ~~**闸门 `[3/7]` 的日期相关假阴性断言**~~ —— **已修（2026-09-19 第八阶段）**：
   它曾断言"日志提交必须一并包含关联项目页"。但 `_touch_projects_activity` 只刷新 `activity_at`，
   而 `update_note_status` 的重写是**幂等**的 ⇒ 同一天第二次写日志时项目页不再变化，
   于是"提交里没有项目页"是**正确行为**、断言却判 FAIL（真机实跑：
   `❌ 日志提交一并包含关联项目页 — HEAD 触及：['logs/2026-09-19-002.md']`）。
   修法：`[3/7]` 在写入前后各读一次项目页字节，**只有内容确实变了才要求它进同一个提交**；
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

- **远端日常 CI 永久手动触发**：`.github/workflows/ci.yml` 只保留 `workflow_dispatch`；push/PR
  不会自动消耗 runner。推送前必须通过 `scripts/pre-push-gate.sh`，需要远端复核时显式运行
  `gh workflow run ci.yml --ref main`。release workflow 的 tag 触发策略不变。

## 提交纪律

- 用 `type: 中文描述`（如 `fix: 同步门禁支持 SSH remote`）。**不要 push 本仓库**除非任务明确要求。
- **改任何 `##` 区块标题前，先看 SK 的区块标题词表**（它写死在
  `SummitKnowledge/retriever.py` 的 `NAV_HEADINGS` / `CONCLUSION_HEADING_PREFIXES`），
  否则会**静默改变检索加权**。
- 判断"要不要修"用 `_vault/conventions.md` §13「缺陷修复判据」：
  第 ① 类（持续制造新错误）必须修并补机器守卫；第 ② 类（只污染历史）登记即可，不必回头重做。
