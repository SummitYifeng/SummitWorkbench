# 内容质量与「工作 vs 建库」边界 · 下一窗口作业单

> **历史边界校正（2026-09-17）**：本作业单保留旧阶段内容；`kb_measure.py`、`wb ask`、`wb kb` 与本地检索索引已退役。当前只执行结构/引用门禁，语义检索由 SummitKnowledge 负责。

> **用法**：新窗口把本文件交给 Agent，说「读 `docs/implementation/NEXT-SESSION-PROMPT-CONTENT-QUALITY.md` 并按它开工」。
> **配套读**：`NEXT-SESSION-PROMPT.md`（通用开工规范 · 门禁 · 铁律）、`_vault/conventions.md`（库规范）。
> **本文件自包含**：使用者原话、已对齐的 6 个决策、已取证的事实、要交付什么、验收标准。

---

## 0. 一句话目标

使用者要的是「**和我工作相关的知识沉淀**」，而不是「**关于建知识库的说明**」。
本轮把这条边界**落成规范**、把已经被污染的 **5 个项目页改写干净**、并修掉 App 的一个泄漏（`.obsidian` 出现在【项目】里）。

> 使用者原话（本质）：「**其实本质上是我们入库的东西呈现出什么样子**。我希望的是这个 work 知识库是
> 和我本身工作更相关的知识库沉淀，而不是和编程以及【建知识库】相关的。」

---

## 1. 使用者本轮反馈（**原话，不要改写**）

1. **App 项目详情页的 `## 当前状态` 没有分层分点**：基本是一大段文字，除了 Markdown 加粗外**阅读友好度很差**。
2. **`## 下一步` 里混进了大量「做初始资料 / 用 AI agent 处理初始资料」的内容**，与他的实际工作无关，
   也不会沉淀成工作经验。他逐字粘贴的例子（公司人事）：
   ```
   ~~交付第一批种子素材~~ —— 部分完成（2026-09-14）：一份按人沟通已入库。
   仍缺：人事制度类原件（招聘 / 入职 / 绩效 / 离职与权限清退）、其他团队成员的沟通。素材放 ~/Desktop/当前材料/HR/。
   建对象页（已示范一次）：hr/people/<person-slug>.md（文件名用拼音或英文名 slug，
   如 liu-yulan、zhang-lingzi.md），把该人的历史沟通一行一条追加进 ## 时间线。
   制度性内容（招聘 / 入职 / 绩效 / 离职与权限清退）建 hr/clusters/ 页，不混进人页。
   涉及账号 / 权限清退的沟通，与 IT 开发与进度 的账户治理联动（IT 侧有对应 P0）。
   按时间的工作日志进 hr/logs/（type: work-log、projects: [hr]）——
   2026-09-14 已确认「日志挂到对应线的 logs/，不单独成线」；按人的长期记录仍进 hr/people/。
   ```
   同样的形态**在活满后勤&行政里也有**（他另贴了一段，内容同类：交素材、建对象页、写模板路径）。
3. **「公司人事」不是 HR 那种人事**：这里记的是「**和公司每一个人的长期沟通**」——**也许形成项目，
   也许没有，也许只是一直在和这个人的沟通记录而已**。
4. **App【项目】里出现 `.obsidian`**，要清除。
5. **项目页里不该出现「建库类内容」**：他点名批评的句子是
   「建对象页（已示范一次）：对方是酒店 / 场地 / 供应商 → `logistics/vendors/<object-slug>.md`」——
   「**和我本身工作没关系**」。

---

## 2. 已对齐的 6 个决策（2026-09-14 选择题，使用者已选）

| # | 决策 | 对实现的影响 |
|---|---|---|
| 1 | **建库类内容全部移出 vault**，只留在仓库侧（Agent 自己的活） | 5 个项目页里所有「交素材 / 建对象页 / 用什么 slug / 素材放哪个目录 / 用哪个模板」一律删除；这些事项要**汇总到仓库侧**（建议新建仓库侧维护待办文件，或落在 PLAN 的一节），**不能丢**，但**库里不出现** |
| 2 | **立规范 + 改写全部 5 页** | `conventions.md` 新增「项目页 / 对象页区块写法」：`## 当前状态` **必须分点分层**、`## 下一步` **只写工作事项**、**禁止建库类内容**；随后改写全部 5 个项目页 |
| 3 | **公司人事只改标题与定位，目录不动** | 目录 `hr/` 与项目 ID `hr` **保持不变**（避免契约级改动）；改 `title` / `summary` / 正文定位说明 / `aliases`——定位改为「**与公司每个人的长期沟通记录**，可能成项目也可能只是持续记录」 |
| 4 | **`hr/clusters/` 的四个待建项直接删掉** | 「招聘 / 入职 / 绩效 / 离职与权限清退」不再作为本线的待建主题；项目页 `## 主题簇` 与 `index/projects.md` 同步删除 |
| 5 | **`.obsidian` 统一排除「点开头 + 机器目录」** | 改过滤规则（不是只加一个名字），**补测试 + 变异验证**；属 App 代码改动 ⇒ **需要重建并安装**才能在他界面生效 |
| 6 | **`## 下一步` 我只从材料 / 决定里提炼，不推断** | 材料里没说的进 `## 未决问题`；**不要**替他编下一步；更不要写建库事项 |

---

## 3. 已取证的事实（本轮已查，直接用，不要重查）

- **`.obsidian` 的位置**：`~/Documents/Work/.obsidian`（在 **Work 根目录**，与 `_vault` 并列；
  `_vault/.obsidian` **不存在**）。
- **它为什么漏出来**：`src/summit_workbench/repositories/project_scan.py` 用
  `is_internal_dirname(p.name)` 过滤 Work 根目录（约 **190 / 205 行**两处 `work_root.iterdir()`），
  该函数**没有排除点开头目录**。修它（或统一过滤规则）即可。
- **另有两处各自维护的忽略名单**（建议本轮统一，避免第三处再漏）：
  - `src/summit_workbench/repositories/vault.py:22` → `_SKIP_DIRS = {".git", ".obsidian", "_signals", "templates"}`
  - `src/summit_workbench/repositories/kb_index.py:39` → `_SKIP_DIRS = {".git", ".obsidian", "_signals", ".summit-workbench", "templates"}`
- **5 个项目页的污染程度**（grep `素材放|已示范一次|object-slug|person-slug|template|模板|入库|conventions|slug|Desktop/当前材料`）：
  `projects/huoman-logistics.md` **11 处** > `huoman-community.md` **9 处** > `hr.md` **8 处** >
  `it-development.md` **5 处** > `hii-affairs.md` **4 处**。**5 页全中，新线最重**（都是 2026-09-14 我写的）。
- **`hr.md` 的 `## 下一步` 原文**：见 §1 第 2 条使用者粘贴（逐字一致，可据此核对改完是否删干净）。
- **vault 现状**：70 篇内容页 / 16 个模板 / 5 个项目页 / 16 篇决策；
  HEAD `a5409f7`（已推送远端）；`wb vault check` 70 篇全过。
- **仓库现状**：HEAD `5a1c01a`（已推送）；pytest **1189 passed / 1 skipped / 83.84%**；
  **App 校验只在 CLI/Agent 侧**（`webapp/`、`workflows/` 都不调用 `validate_note`）——
  但**本轮第 5 条改的是 `project_scan.py`（App 读项目列表的路径）**，所以**必须重建并安装**。

---

## 4. 要交付什么（按价值排序）

1. **规范的边界条款**（`_vault/conventions.md`）：明确两类内容的去处，并给出项目页区块写法。
   建议措辞方向（可优化，但要把判据写死）：
   - **只进库**：工作事实、工作结论、工作决定、工作下一步、工作阻塞、来源与出处。
   - **只进仓库侧（不进库）**：怎么建库、放哪个目录、用什么 slug / 模板 / 字段、素材放哪个桌面目录、
     入库进度与批次、校验与脚本、Agent 的操作步骤。
   - **项目页区块写法**：`## 当前状态` **分点分层**（每点一句、结论在前、带出处）；
     `## 下一步` **只写工作事项**（谁 / 做什么 / 什么时候）；`## 阻塞` 只写**工作阻塞**；
     禁止出现文件路径规范、目录结构、slug、模板名、桌面目录等建库内容。
2. **改写 5 个项目页**（`projects/{hii-affairs,it-development,huoman-community,huoman-logistics,hr}.md`）：
   删净 §3 那 37 处建库类内容；`## 当前状态` 改为分点分层；`## 下一步` 只留工作事项。
   ⚠️ **不要**为了"看起来有内容"而编造下一步 —— 没有就写「（待补：等材料到位）」或进 `## 未决问题`。
3. **「公司人事」重新定位**（只改标题/定位/aliases，**目录与项目 ID 不动**）：
   定位＝「与公司每个人的长期沟通记录（也许形成项目，也许只是持续记录）」；
   删除 `## 主题簇` 里那四个 HR 行政待建项，并在 `index/projects.md` 同步；
   检查 `index/people.md`（人员聚合）是否需要跟着调整描述。
4. **建库类内容不丢**：把从 5 页里删掉的事项**汇总到仓库侧**（建议
   `docs/implementation/WORKBENCH-MAINTENANCE-TODO.md`：素材还缺什么、模板与规范待办、待验证项）。
   库里不出现，但**下一窗口必须能查到**。
5. **修 App 的 `.obsidian` 泄漏**：统一「点开头 + 机器目录」过滤；补单元测试
   （含**变异验证**：把过滤去掉，测试必须红）；`project_scan.py` 是 App 路径 ⇒
   **重建 + 安装 + 提醒使用者 ⌘R 刷新**（见 `NEXT-SESSION-PROMPT.md` §六：发布脚本拒绝覆盖同名目录，
   需先 `mv`；构建较慢放后台；装完 ad-hoc 签名包第一次读 vault 会弹 TCC 授权要提醒他点允许）。

**验收标准**（使用者视角，最要紧的一条）：他打开 App 任意一个项目的详情页，
**`## 当前状态` 是一屏能读完的分点结构**，**`## 下一步` 里没有任何一句是关于"怎么建库"的**。

---

## 5. 门禁与铁律（照 `NEXT-SESSION-PROMPT.md` 走，这里只列最容易翻车的）

```bash
cd /Users/yifengstudio/Documents/GitHub/SummitWorkbench
.venv/bin/python -m pytest --cov -q                 # 期望 1189 passed / 1 skipped / 83.84% 起
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy
.venv/bin/python scripts/secret_scan.py
.venv/bin/python scripts/kb_check_templates.py      # 库内模板 keep 判据
.venv/bin/python scripts/kb_check_templates.py --templates templates/vault --placeholders substitute
.venv/bin/wb vault check                            # 改完项目页必跑
.venv/bin/python scripts/kb_verify_links.py
.venv/bin/python scripts/kb_verify_quotes.py --vault ~/Documents/Work/_vault \
  --materials-root "/Users/yifengstudio/Desktop/3份素材"     # 另一个素材根是 ~/Desktop/当前材料，两个都要跑
.venv/bin/python scripts/kb_index_people.py --vault ~/Documents/Work/_vault --check
# 本地检索度量已退役；语义检索验收由 SummitKnowledge 负责。
```

- 提交信息用 **`-F <文件>`** 传（含反引号），统一带 `[skip ci]`，中文，讲清「为什么」与「验证了什么」。
- **绝不 force / reset / rebase / stash**；**没有任何备份**。
- **不许为了让测试/校验变绿而放松判据**；判据写错要说清原因并保留等价强度
  （2026-09-14 有过一次实例：`project` 字符集校验加到 schema 层，被两条既有测试证明与产品行为冲突，
  最终收窄为「只拦未替换占位符」——见 `domain/vault.py` 的注释与 `tests/unit/test_vault_project_binding.py`）。
- **改了 `_vault` 必跑** `wb vault check` + `kb_verify_links` + `kb_verify_quotes`（两个素材根）。
- **要动 App 代码：先提交代码 → 再构建 → 最后单独提交文档**（否则产物 stamp 指向不含该修复的提交）。
- 使用者重视**诚实标注「已知不足 / 未验证」**，也喜欢在动手前用**选择题**对齐需求。
- 上一轮刚推送完：vault `a5409f7`、仓库 `5a1c01a`，两边 **behind 0 / ahead 0**。

---

## 6. 明确不要做的

- **不要**新增或删除 `projects/*.md`（项目页**恒定 5 个**，见 conventions §13）。
- **不要**改 `hr/` 目录名或项目 ID `hr`（本轮决策：只改标题与定位）。
- **不要**把「建库类内容」搬进别的库内页（如 `inbox.md`）—— 本轮决策是**移出 vault**。
- **不要**替使用者编造 `## 下一步`（决策 6）；材料没提的写进 `## 未决问题`。
- **不要**顺手重写 `SEED-MATERIAL-SPEC.md` 的既有结论或重跑模型验收（本轮只动内容边界与 App 过滤）。
