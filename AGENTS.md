# AGENTS.md — SummitWorkbench（SWB）

> 给进入本仓库的 agent。**只写你从代码/README 里猜不到、踩过坑才知道的约束**；
> 架构与命令细节看 `README.md`。
> 基线截至 **`3ed9780`**（2026-09-17）。若 HEAD 已更新，先确认下面的行号与数字是否漂移。

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
  本机 HTTPS 需经 macOS 系统代理（已在 `repositories/dulwich_git.py` 内置回退）；SSH 直连可用。
  **不要动 `_vault` 的 remote，不要 force push。**

## 付费与不可逆动作

- 本仓库**不产生嵌入费用**（检索已退役）。但**工作库的索引由 SK 负责**：
  **一次全量重嵌会真实调用云端嵌入接口花钱** —— 不要为了验证而触发。
- 不要 `git push` 用户的 `_vault`，除非任务明确要求。

## 验证命令与基线（截至 `3ed9780`）

```bash
./.venv/bin/python -m pytest -q                 # 期望 1225 passed, 1 skipped
./.venv/bin/python -m pytest -q --cov           # 覆盖率期望 ≈83.92%（门槛 80%）
./.venv/bin/ruff check && ./.venv/bin/ruff format --check && ./.venv/bin/mypy src
./.venv/bin/wb vault check ~/Documents/Work/_vault          # 期望 80 篇全过
./.venv/bin/python scripts/kb_verify_links.py ~/Documents/Work/_vault
./.venv/bin/python scripts/kb_check_templates.py --templates ~/Documents/Work/_vault/templates
```
数字会随开发变化：**报基线时务必带上你所测的 commit**，并说明如何重测。

## 提交纪律

- 用 `type: 中文描述`（如 `fix: 同步门禁支持 SSH remote`）。**不要 push 本仓库**除非任务明确要求。
- **改任何 `##` 区块标题前，先看 SK 的区块标题词表**（它写死在
  `SummitKnowledge/retriever.py` 的 `NAV_HEADINGS` / `CONCLUSION_HEADING_PREFIXES`），
  否则会**静默改变检索加权**。
- 判断"要不要修"用 `_vault/conventions.md` §13「缺陷修复判据」：
  第 ① 类（持续制造新错误）必须修并补机器守卫；第 ② 类（只污染历史）登记即可，不必回头重做。
