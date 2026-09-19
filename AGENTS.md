# AGENTS.md — SummitWorkbench（SWB）

> 给进入本仓库的 agent。**只写你从代码/README 里猜不到、踩过坑才知道的约束**；
> 架构与命令细节看 `README.md`。
> 基线：源码提交 **`8c24b7e`**（2026-09-18，即安装包 build `2026091810` 的来源）。
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

- 本机 `/Applications/SummitWorkbench.app` = `0.4.9 / build 2026091815`（`INTERNAL-DEV`、arm64、ad-hoc），
  由 `d738d13` 构建（含飞书任务时效、同步远端诊断、审批页签刷新、跨端回归闸门、clone 诊断对齐）；
  前端身份 `v2026.09.19-6550855f`；原生壳自 build `2026091813` 起**保留 Dock 图标**
  （`LSUIElement=false` + `.regular`），`WB_DOCK_ICON=0` 可退回菜单栏模式。
- `dist/` **只保留最新一份**：`releases/0.4.9/arm64/`（App + DMG + `SHA256SUMS` + `release-metadata.json`）；App SHA-256 为
  `131fc611c96bf5984454ecdb82fa12d942c2936a597848280e9a1335c5d6df25`，DMG SHA-256 为
  `f50f9afd0122cdf0727e077ab518ab73a86ee45f9e433ca60234b9eb31cf12b4`。

- **设置页布局是使用者的显式偏好**（2026-09-18）：主区只放 工作区 / AI 模型 / 飞书
  三张卡且**每张一行**（`.settings-grid-single`）；「自动化与更新」「模型参数（只读）」在
  页面下方的「高级与维护」折叠区里。机器守卫在 `web/scripts/test-browser-contract.mjs`。

## 付费与不可逆动作

- 本仓库**不产生嵌入费用**（检索已退役）。但**工作库的索引由 SK 负责**：
  **一次全量重嵌会真实调用云端嵌入接口花钱** —— 不要为了验证而触发。
- 不要 `git push` 用户的 `_vault`，除非任务明确要求。

## 验证命令与基线（源码提交 `8c24b7e`）

```bash
./.venv/bin/python -m pytest -q                 # 期望 1262 passed, 1 skipped
./.venv/bin/python -m pytest -q --cov           # 覆盖率期望 ≈84.05%（门槛 80%）
./.venv/bin/ruff check && ./.venv/bin/ruff format --check && ./.venv/bin/mypy src
./.venv/bin/wb vault check ~/Documents/Work/_vault          # 期望 82 篇全过
./.venv/bin/python scripts/kb_verify_links.py ~/Documents/Work/_vault
./.venv/bin/python scripts/kb_check_templates.py --templates ~/Documents/Work/_vault/templates
./.venv/bin/python scripts/kb_check_decision_hygiene.py          # 期望：19 篇决策页无库机制描述
```
数字会随开发变化：**报基线时务必带上你所测的 commit**，并说明如何重测。

**跨端回归闸门**（跨 SWB × `_vault` × SK，**会写 vault 并花一次极小模型费用**）：

```bash
./.venv/bin/python scripts/kb_three_end_gate.py            # 跑完自动清理验证件
./.venv/bin/python scripts/kb_three_end_gate.py --keep     # 保留验证件供人工查看
```

一句话验完四类曾经"测试全绿却发生"的不变量：① 真实写入后**工作树干净**（S-1(a)）；
② `_signals/` **未被回跟踪**（S-1(b)）；③ 逐字稿与 `inbox.md` **不进语料**（P1-4）；
④ 精排**真的生效**且结果里无 `meeting-transcript`（P0-4）。改了 vault 写路径、git 后端、
检索策略或 SK 端点配置之后**跑它**。

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

## 提交纪律

- 用 `type: 中文描述`（如 `fix: 同步门禁支持 SSH remote`）。**不要 push 本仓库**除非任务明确要求。
- **改任何 `##` 区块标题前，先看 SK 的区块标题词表**（它写死在
  `SummitKnowledge/retriever.py` 的 `NAV_HEADINGS` / `CONCLUSION_HEADING_PREFIXES`），
  否则会**静默改变检索加权**。
- 判断"要不要修"用 `_vault/conventions.md` §13「缺陷修复判据」：
  第 ① 类（持续制造新错误）必须修并补机器守卫；第 ② 类（只污染历史）登记即可，不必回头重做。
