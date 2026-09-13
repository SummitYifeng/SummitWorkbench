# 交接 · 工作知识库重建 + Workbench 第二大脑检索优化（下一对话执行）

> 本文档由 2026-09-13 的会话写出，**给下一个对话的 agent**。
> 使用者给你的指令是：**先把工作知识库的结构与规范定对，再把第一批真实材料入库，最后把
> Workbench 的"第二大脑"检索改造好（含代码与测试）**；并且**动手之前必须先用选择题与使用者对齐**。
>
> 阅读顺序：§1 现状（事实）→ §2 已对齐的需求 → §3 分类方案候选（**先让使用者挑**）→ §4–§6 设计
> → §7 重建运行方案 → §8 交付与验收 → §10 你要问的选择题 → §12 坑与铁律。

---

## 1. 现状侦察（2026-09-13 实测，非推测）

### 1.1 三个既有资产

| 资产 | 路径 | 事实 |
|---|---|---|
| **工作知识库（目标）** | `~/Documents/Work/_vault` | 24 个文件 / 55 提交，**全部是 M0–M1 测试产物**（`projects/demo-project.md`、示例会议、示例日报…）。远端 `https://github.com/yifeng93/YifengWorkKnowledge.git`。`workspace_id = bf22c8d2-ef62-4bd3-9917-e76fdd3f7f0f`，主设备 Studio `51885d3d-…`、Air `e1b8b735-…`，归属 generation 3 |
| **个人知识库** | `~/Documents/GitHub/MyKnowledge` | 80 文件、Obsidian、远端 `yifeng93/MyKnowledge`。PARA 式编号目录（`00_Inbox`…`99_Archive`）+ `90_System/{Standards,Templates,Workflows}`。**规范 v1.0** 见下。`05_Work/` 目前只有 3 篇 HIC 文档 |
| **第二大脑（既有软件）** | `~/Documents/GitHub/SummitKnowledge` | v0.10.1，**已经是一个成熟产品**：意图路由（点查/综合）+ **混合检索 RRF** + SQLite 向量库 + numpy + 千问百炼嵌入 + DeepSeek 对话 + 可迁移长期记忆（`user_memory.json`）+ Inbox 分析→人工确认管线 + 原生 macOS App。数据源固定为 MyKnowledge |

### 1.2 关键事实

- **`~/Documents/Work` 本身就是 Obsidian 库根**（`.obsidian/` 在那里），`_vault` 是它的**子目录**。
  ⇒ 双链解析、图谱、模板都在这个库的范围内；**工作知识库天然可被 Obsidian 打开**。
- **Workbench 的同步范围**：除 `_vault` 外，还会同步 `work_root`（`~/Documents/Work`）下**同级的其它 git 仓库**
  （`sync_coordinator` 的 `_discover(work_root)`）。⇒ 将来若要再加一个仓库，App 现成支持。
- **`_vault/conventions.md` 已经引用** `../MyKnowledge/90_System/Standards/knowledge-base-conventions.md`，
  且写着「继承 MyKnowledge 知识库规范，并叠加 SummitWorkbench 的执行层约定」——**这条继承关系目前是断的**
  （路径不存在，`MyKnowledge` 在 `~/Documents/GitHub/` 而不是 `~/Documents/Work/`）。**必须修**。
- **MyKnowledge 规范要点**（`90_System/Standards/knowledge-base-conventions.md`，164 行）：
  frontmatter `id/title/area/type/domain/status/created/updated/summary/tags/aliases`（顺序固定）；
  `area ∈ {diary, reading, tech, knowledge, work}`（`system` 不进索引）；文件名小写英文 kebab-case；
  正文一个 `#` 一级标题；双链用稳定文件名 + 中文别名，**每篇 1–3 条强关联并写关系理由**，
  新增候选先入确认清单、**经人工接受才写回正文**；`90_System`、`99_Archive` **不进问答索引**；
  `draft` 状态不进索引。
- **Workbench 现有 vault 契约**（`conventions.md` + `wb vault check` + 代码）：
  frontmatter 必填 `date`/`type`/`status`，`project: <id>` 或 `projects: [<id>…]` **二者不可同时出现**；
  固定区块标题（项目主笔记 `## 当前状态/下一步/阻塞/决策记录`；会议笔记 9 个固定区块，标题不得改名）；
  `inbox.md` 待办条目必须 `- [ ] ` 开头、一行一条、积压数按行数算；会议明确行动项只进 `## 明确行动项`，
  模型推断只进 `## AI 建议`；分层：事实 / 待确认推断 / AI 建议。
- **Workbench 第二大脑现状**：`wb ask` = 路径 + frontmatter + 全文召回 + 云模型作答；
  `webapp/knowledge_sources.py` 定义了来源面板（`KNOWLEDGE_SOURCE_ROOTS`、`SOURCE_BODY_DISPLAY_CHARS`）。
  **没有嵌入、没有向量库**——这是写在产品硬边界里的（README/PROJECTDESC：
  「不建云端服务端、常驻守护进程、向量库或 RAG」）。
- **桌面材料**：`~/Desktop/当前材料`，11 文件 / 368K：
  - `和HII的沟通/`：`HII-HIC_IP关系与沟通全景总结_V2.1_2026-09-12.md`、
    `HIC-HII_Royalty_规则与沟通历程总结_V2.md`、`HIC_HII_China_Visit_Manual_v1.0.md`、
    `HIC_HII_Current_Visits_Danny_Nita_Crystal_2026-09-13.md`
  - `和IT相关的/`：`HIC IT 开发计划与当前进度总结｜2026.09.md`、
    `罗艺峰的视频会议 (1)(2)(3).txt`（会议转写）、`智能纪要：IT对齐 2026年8月3日.zip`
  - 文件名违反 MyKnowledge 命名规范（中文 + 下划线 + `V2.1` 版本后缀），入库时要改名。

---

## 2. 已对齐的需求（两轮选择题结论，2026-09-13）

| # | 决策 | 结论 |
|---|---|---|
| 1 | 工作知识库落位 | **A：`_vault` 就是工作知识库**（清空后按新规范重建）。不并入 MyKnowledge，也不另建仓库 |
| 2 | 清空方式 | **连 git 历史一起不要 → 重建仓库与新历史**。使用者原话：「内容全部清空，提交 git，里面的所有内容都不重要，我希望慢慢实打实往里面填充我的真正的工作内容」 |
| 3 | 敏感边界 | **全部可以上云**（DeepSeek 对话 / 千问百炼嵌入）⇒ 检索引入云模型/云嵌入**不是约束** |
| 4 | 检索技术路线 | **第一阶段不破「无向量库/RAG」硬边界**，把纯文本检索做深（frontmatter 过滤 + FTS/BM25 + 双链/索引优先 + 时间与权威加权 + 分块与引用） |
| 5 | 顶层分类 | **先不定**：由你（agent）在 §3 给出 2–3 套**具体目录 + frontmatter** 设计，交给使用者挑 |
| 6 | 本轮交付范围 | **规范 + 目录骨架 + 首批材料入库 + Workbench 检索改造（含代码与测试）** |
| 7 | 追溯最低要求 | **能回到会议逐字稿 / 原始会议记录**（其它来源本轮不作硬要求） |
| 8 | 入库管线 | **半自动：原始材料 → AI 结构化 → 使用者确认后入库** |
| 9 | 双链策略 | **照 MyKnowledge 规范**：候选清单 → 人工确认 → 每篇 1–3 条、带关系理由 |
| 10 | 检索优先场景 | **① 回溯来龙去脉（时间线/原委）② 决策支持 ⑤ 定期回顾与复盘**（使用者原话「1+2+5」；不优先"写材料带引用"与"找人找承诺"） |
| 11 | 命名 | **统一英文 kebab-case 文件名**；中文进 `title` / `aliases` |
| 12 | vault 契约改动 | **由你（agent）评估后给建议**（哪些必须改、代价多大） |
| 13 | 预期规模 | **数千篇**（含逐字稿；>1000 篇量级） |

使用者未明说、需要你在选择题里补的：工作线之外的顶层维度取舍（§3）、What/Where 归档策略、
附件（PDF/图片/表格）如何入库存放、附件是否进 Git（体积）。

---

## 3. 分类方案候选（**必须让使用者挑，不要自己定**）

三套都满足：Obsidian 可开、纯 Markdown + Git、英文 kebab-case、MyKnowledge 兼容 frontmatter、
Workbench 既有目录（`daily/ logs/ reviews/ inbox.md meetings/ artifacts/ insights/ _signals/`）继续可用。

### 方案 A · 工作线主线（workstream-first）

```
_vault/
├── README.md                      # 库入口：怎么用、去哪找
├── conventions.md                 # 本库规范（继承 MyKnowledge 规范 + 工作层叠加）
├── index/                         # 导航层（MOC，人工维护 + 可再生成）
│   ├── workstreams.md             # 四条工作线总览
│   ├── projects.md                # 项目索引（含状态）
│   ├── people.md                  # 人物/组织索引
│   ├── decisions.md               # 决策台账（跨项目，带日期与状态）
│   └── timeline.md                # 大事记（按时间倒序，链接到笔记）
├── hii/                           # 工作线 1：HII 沟通
│   ├── hii-loyalty.md             # 线索主页（固定区块，见 §4）
│   ├── hii-ip-trademark.md
│   ├── hii-daily-contacts.md      # 日常人员往来
│   ├── notes/                     # 该线索下的笔记
│   └── sources/                   # 该线索下的原始材料（不可变）
├── it/                            # 工作线 2：IT 开发
│   ├── it-roadmap.md
│   ├── projects/<project-slug>.md # 每个开发项目一篇主页
│   ├── notes/
│   └── sources/
├── community/                     # 工作线 3：活满社群
│   ├── community-overview.md
│   ├── logs/                      # 工作日志
│   ├── thinking/                  # 工作思考（long-form-thought 模板）
│   └── sources/
├── hr/                            # 工作线 4：公司人事
│   ├── hr-people.md
│   ├── notes/
│   └── sources/
├── meetings/{notes,transcripts}/  # 保留 Workbench 既有结构（证据链）
├── decisions/                     # 决策记录（或并入各线索，见取舍）
├── daily/ logs/ reviews/          # 保留（执行层）
├── inbox.md inboxes/              # 保留（Workbench 契约）
├── artifacts/ insights/
└── _signals/ .summit-workbench/   # 机器目录，不进知识索引
```

- **优点**：与使用者的四条工作线心智完全一致；每条线自带 `notes/` 与 `sources/`，归属无歧义。
- **代价**：与 Workbench 既有的 `projects/ logs/` 形成**两套组织方式**（一条线下的项目 vs 顶层 `projects/`），
  需要在规范里明确"谁在哪"（例如：`it/projects/<slug>.md` 为正式主页，顶层 `projects/` 仅保留
  Workbench 兼容页或改为指针）。
- **契约影响**：**加法**（新增目录 + 新字段），但 `projects/` 的语义要重新定义 → 需要与使用者确认。

### 方案 B · 项目/时间主线（project-first，工作线做 MOC）

```
_vault/
├── README.md conventions.md
├── index/{workstreams,projects,people,decisions,timeline}.md
├── workstreams/{hii,it,community,hr}.md     # 四条线只做导航页（MOC）
├── projects/<project-slug>.md               # 复用 Workbench 既有 projects/（固定区块）
├── notes/<YYYY>/<MM>/YYYYMMDD-<slug>.md     # 所有笔记按时间落盘
├── sources/<kind>/<YYYY>/…                  # 原始材料按 kind + 时间（transcript/doc/chat/…）
├── thinking/<YYYY>-<slug>.md                # 工作思考
├── meetings/{notes,transcripts}/ daily/ logs/ reviews/ …（保留）
└── _signals/ .summit-workbench/
```

- **优点**：单一内容轴（项目 + 时间），**不产生两套组织方式**；四条线是横切视图（现实中一个项目常横跨多条线）；
  与 MyKnowledge「kebab-case + index」的气质最接近；对"回溯时间线"最友好。
- **代价**：四条线在目录树里不可见（只在 `index/` 与 frontmatter `workstream` 上体现），使用者需要适应。
- **契约影响**：**最小**（`projects/` 语义不变，只是增加 `notes/ sources/ thinking/ index/`）。

### 方案 C · 知识层 / 执行层二分（knowledge-first）

```
_vault/
├── knowledge/     # 沉淀后的知识：workstreams/ projects/ decisions/ thinking/ index/
├── sources/       # 原始材料（不可变，按收到日期）
├── execution/     # Workbench 执行层：daily/ logs/ reviews/ inbox/ meetings/ …
├── _signals/ .summit-workbench/
```

- **优点**：资产与机器产物**物理分离**，「即便没有 Workbench 依旧是核心资产」这条最干净；
  sources 不可变 ⇒ 溯源最强。
- **代价**：**改动最大**——Workbench 代码里 `daily/`、`projects/`、`inbox.md`、`review/` 等路径
  目前在 vault 根，需要同步改写入器、`wb vault check`、口径与测试；风险最高。
- **契约影响**：**重构级**（与使用者第 12 题"由 agent 评估"直接相关）。

### 三套共用的 frontmatter（建议，v2「MyKnowledge 超集」）

```yaml
id: 20260913-a1b2            # 稳定 ID，改名不变（MyKnowledge 规范）
title: 中文自然语言标题        # MyKnowledge 规范
area: work                   # MyKnowledge 路由字段（固定 work）
workstream: hii              # 新增：hii | it | community | hr | company | cross
project: hii-ip-trademark    # 复用 Workbench 字段（单项目）
# projects: [a, b]           # 跨项目时用这个，二者不可同时出现（Workbench 既有校验）
type: meeting-note           # 统一词表（见下）
domain: trademark            # 细主题
status: active               # 复用 MyKnowledge 词表
created: 2026-09-13          # MyKnowledge 规范
updated: 2026-09-13
date: 2026-09-13             # Workbench 既有必填（事件日期）
summary: 一句话说明这篇解决什么问题
tags: []
aliases: [中文别名, 旧文件名]
source:                      # 溯源（本轮最低要求：会议逐字稿）
  kind: transcript           # transcript | meeting | doc | chat | feishu | email | manual
  ref: meetings/transcripts/2026-09-08-demo-kickoff-transcript.md
  date: 2026-09-08
people: [张三]                # 人物（供 index/people.md 聚合）
org: [HII, HIC]
confidential: false          # 预留分级位（本轮全部可上云，先留 false）
```

- **`type` 统一词表（建议）**：`workstream`（线索主页）、`project-main`、`project-note`、
  `meeting-note`、`meeting-transcript`、`decision`、`work-log`、`long-form-thought`、
  `daily`、`weekly-review`、`qa-insight`、`source`、`index`、`inbox`、`conventions`、`approval-page`。
  ⚠️ 改动 `type` 词表会牵动 `wb vault check` 与检索过滤 ⇒ 属于"加法"（新增值），不得删除既有值。
- **固定区块（新增类型）**：
  - 线索主页（`workstream`）：`## 现在在哪`、`## 关键结论`、`## 未决问题`、`## 决策记录`、`## 时间线`、`## 关联`。
  - 决策记录（`decision`）：`## 背景`、`## 选项`、`## 决定`、`## 理由`、`## 影响`、`## 证据`。
  - 原始材料（`source`）：`## 来源`、`## 要点`、`## 关联`（**正文尽量不改写原文**，改写产物放对应 note）。
- **命名**：`<YYYYMMDD>-<english-slug>.md`（笔记）、`<english-slug>.md`（主页/索引）、
  `<YYYY-MM-DD>-<english-slug>-transcript.md`（逐字稿，复用 Workbench 既有格式）。

---

## 4. 知识库规范要点（写进 `conventions.md` 的目标状态）

1. **继承关系必须修好**：把 `_vault/conventions.md` 里指向 MyKnowledge 规范的相对路径改成可达路径，
   并明确"**工作层叠加**"了哪些字段（`workstream`/`source`/`people`/`org`/`confidential`）。
2. **单一真源**：工作库规范只在 `_vault/conventions.md` 一处定义；MyKnowledge 的规范作为被引用的上游。
   两份规范若冲突，以**工作库规范**为准处理工作内容（并在文档里写明）。
3. **第一读者是 Agent**（沿用 Workbench 既有原则）：稳定路径、统一 frontmatter、固定区块标题优先于人排版偏好。
4. **资产独立性**：任何"索引/向量/缓存"都**不得成为阅读前提**——纯 Markdown + Git 必须自足；
   生成的索引（MOC/时间线）必须是**可读 Markdown**且可再生成。
5. **机器目录隔离**：`_signals/`、`.summit-workbench/`、以及任何检索索引**不进知识索引、不参与双链**；
   索引数据库**放在 vault 之外**（`~/Library/Application Support/SummitWorkbench/…`）以免污染资产与双机同步。
6. **附件策略**：原件（PDF/图片/表格/zip）建议放 `sources/…` 或 `attachments/`，体积大者**不进 Git**、
   改为"库内只留引用 + 本机原件路径"；需使用者拍板（见 §10）。
7. **`inbox.md` 与 `review/meetings.md` 的既有契约不动**（Workbench 的捕捉/审批链路依赖它们）。

---

## 5. 入库管线（半自动 + 人工确认 + 双链候选）

```
原始材料（当前材料目录 / 会议转写 / 手册 / 汇总 md）
   │  ① 归档为 source 笔记（不可变，保留原文与来源）
   ▼
AI 结构化草稿（status: draft）
   │  ② 提取：事实 / 决策 / 行动项 / 未决问题 / 人物 / 组织 / 时间
   │  ③ 生成：目标笔记（workstream / project / decision / note）
   │  ④ 生成：双链候选清单（每条带关系理由）+ 命名建议（英文 kebab-case）
   ▼
人工确认（Workbench 审批页 / 或库内 review 队列）
   │  ⑤ 使用者逐条确认：接受 / 修改 / 拒绝（默认不选中，与 MyKnowledge 一致）
   ▼
写回正式笔记（补 frontmatter、更新 index/、更新 timeline）
```

- **必须复用 Workbench 既有机制**：`review/meetings.md`（会议提取的唯一待确认入口）、
  Workbench 的审批页与 mutation runtime（写回自动 `wb:` 留痕 + 双机同步）。
  新增的"入库确认"应挂进同一条确认链路，不要另造一套。
- **判重**：入库前对 `id`/`aliases`/标题/来源做去重检查（重复时走"合并到已有笔记"分支）。
- **幂等**：同一份原始材料重复入库不得产生重复笔记（用 `source.ref` + 内容哈希做键）。
- **首批 11 个文件**：4 篇 HII 梳理 → `hii` 线索主页 + 相应决策/note；1 篇 IT 计划 →
  `it/it-roadmap.md` + 各开发项目页；3 份会议 txt + 1 个 zip → `sources/` + 会议笔记（若有要点）。

---

## 6. 第二大脑检索设计（第一阶段：纯文本做深，不破硬边界）

**目标**：让「回溯来龙去脉」「决策支持」「定期回顾」三类问题**答得准、查得到出处、不编**。

1. **索引层（可重建，不入 Git）**
   - frontmatter → 结构化表（`path,id,title,area,workstream,project,type,domain,status,date,people,org,tags,updated,hash`）。
   - 正文 → 分块（**按 `##` 标题切**，保留标题路径）→ SQLite **FTS5**（若打包的 Python 无 FTS5，退化为
     自建 BM25；**先探测再决定**，不要假设）。
   - 增量：按 `(path, mtime, hash)` 跳过未变文件；全量重建必须可用。
   - 位置：`Application Support/…/kb-index.sqlite`（**不在 vault**）。
2. **查询路由**（借用 SummitKnowledge 的设计，不引其代码）：先判 **点查 / 综合 / 回溯 / 决策 / 回顾**，
   再决定检索配比；判定用现有模型客户端（DeepSeek）+ 便宜的启发式兜底（关键词、问句形态、时间词）。
3. **检索信号融合**（加权或 RRF，权重可配、可测）：
   - FTS/BM25 命中（正文与标题分权）；
   - frontmatter 过滤（workstream/project/type/status/date/people/org/tags）；
   - **索引/MOC 页优先**（`index/*`、`<workstream>.md` 等主页给权威加权）；
   - **双链扩展 1–2 跳**（出链 + 入链，`aliases` 也要能解析）；
   - 时间与权威加权（越新越靠前，`decision`/`index`/`workstream` 权重高于散记）；
   - 去重（同笔记同分块只留一次），并保留"为什么命中"。
4. **回答与引用**：只依据检索到的内容作答；**每条结论带 `路径#区块` 级引用**；
   证据不足要明说"库里没有"；推断与事实分层（沿用 Workbench 既有"事实/推断/建议"分层）。
   来源面板已有基础（`webapp/knowledge_sources.py`），应扩展为"检索轨迹"（命中了哪些块、走了哪些双链）。
5. **三个优先场景的专门形态**
   - **回溯**：给定线索/项目 → 按时间聚合笔记 + 决策 + 会议（含逐字稿链接）→ 输出"演化时间线 + 关键转折"。
   - **决策支持**：检索同一主题的历史决策（`type: decision`）+ 未决问题 + 相关会议结论 + 风险 → 输出
     选项对比与建议，并显式列出"依据了哪些历史决策"。
   - **定期回顾**：按周期汇总新增笔记/决策/双链变化 → 生成可读 Markdown（放 `reviews/` 或 `index/`）。
6. **落到代码**：`wb ask`（`src/summit_workbench/workflows/ask/`）与 `webapp/knowledge_sources.py` 是主战场；
   涉及新路由时必须同步更新 `docs/contracts/web-route-contract.json`
   （`scripts/update-web-route-contract.py`）——**这是公开契约，不能漏**。

---

## 7. 重建运行方案（**破坏性步骤必须逐条向使用者确认**）

使用者已选「连历史一起不要 → 重建仓库与新历史」。要点：

1. **先备份**：把现有 `_vault` 与远端 clone 各留一份到仓库外（例如
   `~/Library/Application Support/SummitWorkbench/backup/vault-before-rebuild-<date>/`），**并告知使用者**。
2. **新建远端**：GitHub 新建**空**私有仓库（例如 `yifeng93/WorkKnowledge`；不要勾选 README）。
   **不要**用 force-push 改写旧仓库历史——Workbench 的推送路径只在图复核确认真快进时才强推（D9），
   改写历史会与这条安全约束冲突。旧仓库建议 **archive**（保留可追溯），是否删除由使用者定。
3. **Studio（主设备）**：清空 vault 内容 → 重建规范骨架（§3 选定方案）→ `git init` 新历史 →
   用**上一轮已实现的「首次发布到远端」**流程绑定新远端（`POST /api/settings/git/remote/publish`，
   见 `docs/acceptance/OPEN-VERIFICATION-ITEMS.md` §R）。
4. **workspace_id 取舍（重要，需使用者拍板）**：
   - **保留** `.summit-workbench/workspace.json` 的同一个 `workspace_id` ⇒ 两台机器的 profile、
     Keychain 凭据（`git:github.com:Yifeng93`）、主设备声明都继续有效，重建成本最低；
   - **换新** ⇒ 两台机器都要走一遍连接向导，并且主设备声明要重新建立。
5. **Air**：清掉本地旧 vault → 重新走「从另一台 Mac 克隆」接新仓库（角色按 D10 自动判为 `secondary`）。
6. **收尾核验**：两台 `/api/sync/status` = `ready` / `0/0`；`acceptance-preflight` 11/11；
   Studio `automation_primary_device_id` = Studio；Air 角色 `secondary`；克隆后空库能正常提交与同步。

---

## 8. 本轮交付物与验收（DoD）

**A. 知识与规范**
- [ ] `_vault/README.md` + `conventions.md` v2（继承关系修好、字段表、命名、区块、双链规则、附件策略）
- [ ] 选定方案的**目录骨架**（含 `index/*` MOC 页初版）
- [ ] 模板：workstream 主页 / project / note / decision / work-log / long-form-thought / source（放库内 `templates/` 或复用 Workbench `templates/`）
- [ ] **首批 11 个文件全部入库**：改名（英文 kebab-case）、补 frontmatter（中文 title/aliases）、
      建主页与索引、生成双链候选并**经使用者确认**后写回
- [ ] 每条入库笔记都能沿 `note → 会议笔记 → 逐字稿` 走通（本轮追溯最低要求）

**B. Workbench 检索改造（含代码与测试）**
- [ ] 索引构建（增量 + 全量）+ frontmatter 结构化表
- [ ] 查询路由（点查/综合/回溯/决策/回顾）与多信号融合检索
- [ ] `wb ask` 与来源面板升级：`路径#区块` 级引用 + 检索轨迹 + 双链扩展
- [ ] 三个优先场景（回溯 / 决策支持 / 定期回顾）各有可验证的形态
- [ ] 新路由/新 payload 若引入：同步更新 route contract 快照
- [ ] 测试：索引、路由、融合排序、引用、去重、别名解析、增量重建各有着一例；
      **每项修复/新增都要有变异验证或可判定的失败模式**

**C. 门禁（沿用仓库既有约定，逐条必须绿）**
```
web/node_modules/.bin/tsc --noEmit -p web/tsconfig.json
npm --prefix web run test:frontend
npm --prefix web run build && node web/scripts/verify-build.mjs src/summit_workbench/webapp/static
.venv/bin/python -m pytest --cov -q
.venv/bin/ruff check && .venv/bin/ruff format --check
.venv/bin/mypy
.venv/bin/python scripts/secret_scan.py
WB_PACKAGED_APP=/Applications/SummitWorkbench.app .venv/bin/python -m pytest tests/integration/test_packaged_app.py -q
```
- 提交信息与是否 `[skip ci]`：**先问使用者**（上一轮约定是全部 `[skip ci]`、不跑 CI，本轮未定）。

---

## 9. 明确不做（Non-goals）

- 不把工作内容并入 MyKnowledge，不改 MyKnowledge 的现有结构与规范。
- 不改造/不耦合 SummitKnowledge（本轮只**借鉴其设计思路**；是否让它索引工作库留待以后）。
- 第一阶段**不引入向量库/嵌入/RAG**（不破硬边界）；不新增第三方依赖。
- 不改 Workbench 的飞书链路、双机同步语义、审批与 mutation runtime 的既有安全约束。
- 不动 `_signals/`、`.summit-workbench/` 的机器语义。

---

## 10. 你要问使用者的选择题（下一轮互动清单）

1. **§3 三套方案选哪套**（A 工作线主线 / B 项目+时间 / C 知识层与执行层二分）；若选 C，接受相应的代码重构代价吗？
2. **顶层维度取舍**：`workstream`（四条线）之外，是否需要 `company`（公司层面）与 `cross`（跨线）两个值？
3. **附件策略**：PDF/图片/表格/zip 是"进 Git 随库同步"还是"只留引用 + 本机原件"？有没有单文件体积上限？
4. **`projects/` 语义**（若选 A/C）：沿用 Workbench 既有 `projects/<id>.md` 还是迁到方案目录？旧页怎么办？
5. **决策记录的位置**：集中在 `decisions/`（便于"决策支持"检索）还是分散在各线索下（便于就地阅读）？两者要不要都留？
6. **workspace_id 取舍**（§7.4）：保留同一 workspace（重建成本最低）还是换新（更彻底）？
7. **旧远端 `YifengWorkKnowledge`**：archive 保留还是删除？
8. **首批入库的确认方式**：在 Workbench 审批页逐条确认，还是在 Obsidian 里看候选清单确认？
9. **索引与检索的实现基线**：SQLite FTS5 优先（先探测打包 Python 是否支持）还是自建 BM25？
10. **"定期回顾"的产物落点**：放 `reviews/`（沿用 Workbench）还是 `index/`（知识层）？周期是周还是月？
11. **提交与 CI 约定**：是否沿用 `[skip ci]`、是否跑远端 CI？
12. **验收方式**：首批入库与三场景检索，是否要像上一轮那样做"真机 + 双机"核验？

---

## 11. 关键文件与命令速查

| 用途 | 位置 |
|---|---|
| 工作库（目标） | `~/Documents/Work/_vault` |
| 工作库规范（现状） | `_vault/conventions.md` |
| 个人库规范（上游） | `~/Documents/GitHub/MyKnowledge/90_System/Standards/knowledge-base-conventions.md` |
| 个人库维护流程 / 双链清单 | `MyKnowledge/90_System/Workflows/{knowledge-base-maintenance-workflow,semantic-link-review-checklist}.md` |
| 上游 Inbox 契约 | `MyKnowledge/90_System/Standards/inbox-capture-contract.md` |
| 首批材料（**仓库外**） | `~/Desktop/当前材料/` |
| Workbench 检索代码 | `src/summit_workbench/workflows/ask/`、`src/summit_workbench/webapp/knowledge_sources.py` |
| Workbench vault 校验 | `wb vault check`（对应实现与测试在 `src/` + `tests/`） |
| 会议写入与审批 | `src/summit_workbench/workflows/meetings/`、`review_apply.py`、`review/meetings.md` |
| 路由契约快照 | `docs/contracts/web-route-contract.json`（`scripts/update-web-route-contract.py`） |
| 上一轮交付与真机证据 | `docs/acceptance/OPEN-VERIFICATION-ITEMS.md` §R（含 G2 首次发布流程） |
| 上一轮交接（格式参考） | `docs/archive/plans/HANDOFF-NEXT-DELIVERY-AND-CLEANUP.md` |

**上一轮已具备、本轮可直接复用的能力**：内置飞书凭据、G2「首次发布到远端」（新仓库绑定+首次推送）、
D10 角色自动判定、G3 服务日志、双机同步与真机核验配方。

---

## 12. 坑与铁律（沿用 Workbench 既有约定）

1. **不要跑 CI / 提交带 `[skip ci]`**：本轮是否沿用**先问使用者**。
2. **公开契约不能悄悄改**：路由、payload 字段名、错误码、vault 固定区块标题、`inbox.md` 格式 —— 改动必须
   同步更新快照与测试，并在提交说明里写清。
3. **绝不 force/reset/rebase/stash**；重建历史靠"新空仓库 + 首次发布"，不靠强推。
4. **不改公开模块的名字、不为了整洁合并模块**（上一轮清理已定调）。
5. **机器日志绝不写进 vault**（vault 内的 `logs/` 是**工作台内容**）；检索索引数据库也**不放进 vault**。
6. **写测试要避开 secret_scan 的凭据形状**（`https://user:pass@`、`-----BEGIN … PRIVATE KEY-----` 等）。
7. **改动前先 grep 确认无引用**；删/移文件后必须跑全部门禁。
8. **`install-macos-app.sh` 的 readiness 报错常常是假失败**：以 `runtime.json` 与接口探针为准。
9. **双机上的任何"角色/归属"操作**都不会自动同步到另一台的本机档案（见 §R.8 的说明）；
   涉及角色切换时，记得在另一台点一次「降级为备用设备」让显示自洽。
10. **首批入库会真的写入使用者的核心资产**：任何批量写回前，先把计划与改名映射表给使用者确认。
