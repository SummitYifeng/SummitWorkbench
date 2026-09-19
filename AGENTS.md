# AGENTS.md — SummitWorkbench（SWB）

> 给进入本仓库的 agent。**只写你从代码/README 里猜不到、踩过坑才知道的约束**；
> 架构与命令细节看 `README.md`。
> 基线：当前交付源码提交 **`a49bb42`**（2026-09-19，即安装包 build `2026091918` 的来源；
> 上一份是迁移交付 `2d1cf3a` → build `2026091917`）。
> 若 HEAD 更新，先确认下面的行号与数字是否漂移——**基线的锚是那个源码提交，不是 HEAD**
> （否则「更新基线」这一动作本身会产生新提交，基线永远追不上，参见前端 build 身份的同类教训）。

## 所有权边界（硬约束）

- **SWB 是工作知识库 `_vault` 的唯一写入方**（入库 / 审批 / 写回 / 简报）。
- **`_vault` 的规范单一真源不在本仓库**，而在另一个仓库：
  `~/Documents/Work/_vault/conventions.md`（其 **§9.1** 是 SWB ↔ SK 的接口契约）。
  写与工作库相关的代码前，**先读它**。
- **SK（SummitKnowledge）是唯一检索方**，只读工作库；不要在本仓库实现检索/向量化。

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
  语义：机器写入页（`daily/ logs/ artifacts/ reviews/ index/*.md inbox.md review/meetings.md README.md`）
  **只豁免"必填"，值存在但越界时仍报错**。
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

- 本机 `/Applications/SummitWorkbench.app` 为 `0.4.9 / build 2026091918`（`INTERNAL-DEV`、arm64、ad-hoc），
  由 `a49bb42` 构建（`release-metadata.json` 的 `git_commit` 即此值，可直接复核）；前端身份仍为
  `v2026.09.19-6550855f`（批次 A 未改前端源码）；包内**已内置飞书默认凭据**
  （`build-manifest.json` 的 `feishu_credentials.complete=true`）。
  上一份交付是 `2d1cf3a` → build `2026091917`（Dulwich `1.2.15` 迁移 + 日常 CI 收窄为手动触发）。
  原生壳自 build `2026091813` 起**保留 Dock 图标**（`LSUIElement=false` + `.regular`），
  `WB_DOCK_ICON=0` 可退回菜单栏模式。
- **本机重建必须带内置飞书凭据**：默认 `REQUIRE_BUNDLED_FEISHU=true`，缺
  `WB_FEISHU_APP_ID` / `WB_FEISHU_APP_SECRET` 会在**打包阶段**才失败（前面几十分钟的测试与
  PyInstaller 全白跑 —— 2026-09-19 批次 A 交付实测踩到）。凭据从**上一个含内置凭据的包**里取证、
  不手抄、不落仓库，步骤见 `docs/RELEASING.md`（本次即用它从装机版包内 `feishu-defaults.json`
  生成 0600 临时 env）。另外 `release-macos.sh` 要求**显式** `BUILD_NUMBER`，且**拒绝覆盖已存在的
  发布目录**（要重建同一版本须先移除旧目录）。
- `dist/` **只保留最新一份**：`releases/0.4.9/arm64/`；build `2026091918` 的
  **App SHA-256 为 `8b23e5bcf0d24de322bd3f826b1d3337fbebd59680d801d7bee4a30cfd6e4c37`**，
  **DMG SHA-256 为 `8a30b9ef8a73f5efd3764f418bca463b65ce60b2914347827e3846dced3d6c61`**
  （**以 `release-metadata.json` 的 `sha256` 为准**：`SHA256SUMS` 只覆盖 DMG 与元数据文件、不含 App）。
  装机包内**真实**依赖以发布目录的 `SBOM.json` 为准
  （build `2026091918` 实测 `dulwich==1.2.15`、`uvicorn==0.53.0`、`pyinstaller==6.22.3`、
  `ruff==0.16.7`、`hypothesis==6.168.0`，与上一版相同）。

- **设置页布局是使用者的显式偏好**（2026-09-18）：主区只放 工作区 / AI 模型 / 飞书
  三张卡且**每张一行**（`.settings-grid-single`）；「自动化与更新」「模型参数（只读）」在
  页面下方的「高级与维护」折叠区里。机器守卫在 `web/scripts/test-browser-contract.mjs`。

## 付费与不可逆动作

- 本仓库**不产生嵌入费用**（检索已退役）。但**工作库的索引由 SK 负责**：
  **一次全量重嵌会真实调用云端嵌入接口花钱** —— 不要为了验证而触发。
- 不要 `git push` 用户的 `_vault`，除非任务明确要求。

## 验证命令与基线（交付提交 `a49bb42`）

```bash
./.venv/bin/python -m pytest -q                 # 实测 1306 passed, 1 skipped
./.venv/bin/python -m pytest -q --cov           # 实测 84.10%（门槛 80%）
./.venv/bin/ruff check && ./.venv/bin/ruff format --check && ./.venv/bin/mypy src
./.venv/bin/wb vault check ~/Documents/Work/_vault          # 期望 84 篇全过
./.venv/bin/python scripts/kb_check_contract.py --vault ~/Documents/Work/_vault
./.venv/bin/python scripts/kb_verify_links.py ~/Documents/Work/_vault
./.venv/bin/python scripts/kb_check_templates.py --templates ~/Documents/Work/_vault/templates
./.venv/bin/python scripts/kb_check_decision_hygiene.py          # 期望：19 篇决策页无库机制描述
```
数字会随开发变化：**报基线时务必带上你所测的 commit**，并说明如何重测。
（`release-macos.sh` 内部另跑一份较窄的 pytest 子集，数量少于上表的 1262，别把两者当矛盾。）

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
收尾会打印 vault `origin/main` 前后取值，**未启用推送模式却发生变化时逐条告警**
（绝不藏在裸 PASS 后面）。`--no-push` 是 `--no-push-cleanup` 的弃用别名（旧名容易被误读为
"整个闸门不推送"，实际只关收尾那一推）。

一句话验完六类曾经"测试全绿却发生"的不变量：① 真实写入后**工作树干净**（S-1(a)）；
② `_signals/` **未被回跟踪**（S-1(b)）；③ 逐字稿与 `inbox.md` **不进语料**（P1-4）；
④ 精排**真的生效**且结果里无 `meeting-transcript`（P0-4）；
⑤ **原件（`<project>/sources/`）与 `daily` / `weekly-review` 不进语料**（批次 A 语料边界）；
⑥ **来源白名单覆盖真实库的全部主线项目**（`thinking` 在内；这条只在有真实库的环境成立，
故放在闸门而不是只做单元测试）。改了 vault 写路径、git 后端、检索策略、来源白名单或
SK 端点配置之后**跑它**。

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

2. **跨端闸门的三个判据缺陷**（2026-09-19 批次 A 收口时实测发现，尚未修）：
   ① `[1/6]` 把 `state=local-ahead` 判成 **FAIL**——但"本机有提交未推送"是**正常且安全**的状态
   （界面常规横幅就是它），而推荐的验证姿势（`--no-push-cleanup` + 不自动推送）**本身就会制造
   local-ahead**⇒**连续跑两次闸门，第二次必在 `[1/6]` 失败**（本机实测）。应像 `error` 那样降为 WARN。
   ② `[推送守卫]` 只告警、不判失败——而它正是"验证意外推送"的判据，只看退出码的 agent 会忽略它，
   **应改为 FAIL**。
   ③ `WB_NO_AUTO_PUSH` 目前只在 `mutation_runtime._push_after_commit` 这一层生效；将来若有人新增
   **绕过该出口**的自动推送路径不会被覆盖（显式 `/api/sync/run`、`wb sync` 本就该推，不受影响）
   ⇒**补一条"自动推送必须经过单一出口"的结构性守卫**。

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
