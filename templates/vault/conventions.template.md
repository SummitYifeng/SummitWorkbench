---
date: {{date}}
type: conventions
status: active
project: global
updated: {{date}}
title: 工作知识库规范
aliases:
  - Work Vault Conventions
  - 工作库规范
---

# 工作知识库规范（v2）

> **上游规范**：MyKnowledge 知识库规范，位于你的**个人知识库**里：
> `<个人库根>/90_System/Standards/knowledge-base-conventions.md`。
> 默认布局（个人库在 `~/Documents/GitHub/MyKnowledge`、工作库在 `~/Documents/Work/_vault`）下，
> 相对路径是 `../../GitHub/MyKnowledge/90_System/Standards/knowledge-base-conventions.md`。
> 本库**继承**上游的 frontmatter 公共字段、kebab-case 命名、双链与索引原则，并**叠加**工作层字段与执行层约定。
>
> **单一真源**：处理**工作内容**时，本文件是唯一真源；与上游冲突时以本文件为准（上游只约束个人库）。
> **第一读者是 Agent**：稳定路径、统一 frontmatter、固定区块标题，优先于人类排版偏好。

---

## 0. 边界与硬约束

1. **资产独立性**：纯 Markdown + Git 必须自足。任何索引、向量、缓存都**不得成为阅读前提**；
   生成的索引页（MOC / 时间线）必须是可读 Markdown，且随时可再生成。
2. **机器目录隔离**：`_signals/`、`.summit-workbench/`、以及任何检索索引**不进知识索引、不参与双链**。
3. **检索索引库放在 vault 之外**：`~/Library/Application Support/SummitWorkbench/kb-index.sqlite`，
   以免污染资产与双机同步。
4. **机器日志绝不写进本库**：库内 `logs/` 是**工作台内容**（人的工作记录），不是程序日志。
5. **第一阶段不引入向量库 / 嵌入 / RAG**：把纯文本检索做深（frontmatter 过滤 + FTS/BM25 + 双链/索引优先
   + 时间与权威加权 + 分块与引用）。
6. **内容分级**：本库当前内容**全部可以上云**（DeepSeek 对话 / 千问百炼嵌入）；
   `confidential` 字段为将来分级预留位，本期一律 `false`。

---

## 1. 目录结构（方案 A：工作线主线）

```
_vault/
├── README.md                      # 库入口：怎么用、去哪找
├── conventions.md                 # 本文件（规范单一真源）
├── index/                         # 导航层（MOC，人工维护 + 可再生成）
│   ├── workstreams.md             # 四条工作线总览
│   ├── projects.md                # 项目索引（含状态）
│   ├── people.md                  # 人物 / 组织索引
│   ├── decisions.md               # 决策台账（跨项目，带日期与状态）
│   └── timeline.md                # 大事记（倒序，链接到笔记）
├── templates/                     # 库内模板（Obsidian 核心 Templates 插件）
├── hii/                           # 工作线 1：HII 沟通
│   ├── hii-loyalty.md             # 线索主页（workstream，固定区块）
│   ├── notes/                     # 该线下的笔记
│   └── sources/                   # 该线下的原始材料（不可变）
├── it/                            # 工作线 2：IT 开发
│   ├── it-roadmap.md
│   ├── notes/
│   └── sources/
├── community/                     # 工作线 3：活满社群
│   ├── community-overview.md
│   ├── logs/                      # 工作日志
│   ├── thinking/                  # 工作思考（long-form-thought）
│   └── sources/
├── hr/                            # 工作线 4：公司人事
│   ├── hr-people.md
│   ├── notes/
│   └── sources/
├── decisions/                     # 决策记录（集中，一决策一篇）
├── projects/                      # 项目主页（沿用 Workbench 既有语义）
├── meetings/{notes,transcripts}/  # 会议笔记与逐字稿（证据链）
├── daily/ logs/ reviews/          # 执行层：每日 / 工作记录 / 复盘
├── review/{meetings.md,archive}/  # 审批入口（契约见 §11）
├── artifacts/ insights/ inboxes/  # 产物 / 问答洞察 / 项目收件箱
├── inbox.md                       # 全局收件箱（机器可读，契约见 §11）
├── _signals/ .summit-workbench/   # 机器目录，不进索引与双链
└── .gitignore
```

**归属判定（重要）**

| 内容 | 放哪 | 理由 |
| --- | --- | --- |
| 某条工作线的现状 / 结论 / 未决 | `<workstream>/<line>-<name>.md`（`type: workstream`） | 一条线一个入口页 |
| 某条线下的普通知识笔记 | `<workstream>/notes/` | 归属无歧义 |
| 某条线下的原始材料 | `<workstream>/sources/` | 原件不可变，可回溯 |
| **项目主页** | **顶层 `projects/<slug>.md`** | 沿用 Workbench 写入器、`wb vault check` 与检索前缀匹配，契约零风险 |
| 决策记录 | `decisions/`（集中），各线索页用双链引用 | 「决策支持」检索能一次捞全历史决策 |
| 会议笔记 / 逐字稿 | `meetings/notes/`、`meetings/transcripts/` | Workbench 既有证据链 |

> ⚠️ **不产生两套组织方式**：项目主页**只**在顶层 `projects/`；工作线目录下**不要**再建 `projects/`。

---

## 2. frontmatter v2（MyKnowledge 超集）

字段**顺序固定**，便于 Agent 与 diff 稳定阅读：

```yaml
id: 2026-09-13-a1b2          # 稳定 ID，改名不变（工作库口径：<YYYY-MM-DD>-<4位十六进制>）
title: 中文自然语言标题        # 人类阅读用
area: work                   # 上游路由字段，工作库固定 work
workstream: hii              # 工作线：hii | it | community | hr | company | cross
project: hii-ip-trademark    # 绑定单一项目用它（与 projects 二者不可同时出现）
# projects: [a, b]           # 跨项目时用它
type: note                   # 笔记角色，词表见 §3
domain: trademark            # 更细主题
status: active               # 上游状态词表，见 §2.2
created: 2026-09-13
updated: {{date}}          # 只在内容发生实质变化时更新
date: {{date}}             # Workbench 既有必填：事件日期
summary: 一句话说明这篇解决什么问题
tags: []
aliases: [中文别名, 旧文件名]
source:                      # 溯源（本轮最低要求：能回到会议逐字稿）
  kind: doc                  # transcript | meeting | doc | chat | feishu | email | manual
  ref: meetings/transcripts/2026-08-03-it-alignment-transcript.md
  date: 2026-08-03
people: [罗艺峰]
org: [HIC, HII]
confidential: false
```

### 2.1 必填与叠加

- **Workbench 既有必填**（`wb vault check` 强制）：`date`、`type`、`status`。
- **本库叠加必填**（约定层，供检索与索引页聚合）：`id`、`title`、`area: work`、`workstream`、
  `created`、`updated`、`summary`。
- `project` / `projects`：**二者不可同时出现**。绑定关系可以是「单项目 / 多项目 / 都不绑」，
  由 `type` 的 scope 决定（§3）。
- `aliases`：中文别名与**历史文件名**，使重命名后的旧双链仍可解析。

### 2.2 `status` 词表（沿用上游 + Workbench，不得新增）

`active`、`paused`、`archived`、`draft`、`superseded`、`pending-review`、`generated`、`applied`、`ignored`。

- `draft`：**不进入问答索引**（未完成的内容不得被当成事实引用）。
- `superseded`：已被更新结论替代，仍留在原处供追溯。

---

## 3. `type` 词表与 scope

scope 决定绑定关系：`single` = 必须 `project: <id>`；`multi` = 必须非空 `projects: [...]`；
`global` = 必须 `project: global`；`free` = 三者皆可，但不得 `project`/`projects` 并存。

| `type` | scope | 固定区块 | 用途 |
| --- | --- | --- | --- |
| `workstream` | global | §4.1 | 线索主页（一条工作线的入口） |
| `note` | free | — | 一般知识笔记（正文结构自由） |
| `decision` | free | §4.2 | 决策记录（集中在 `decisions/`） |
| `source` | free | §4.3 | 原始材料笔记（不改写原文） |
| `index` | global | — | 导航层 MOC（`index/`） |
| `long-form-thought` | free | §4.4 | 工作思考长文 |
| `project-main` | single | §4.5 | 项目主页（`projects/<slug>.md`） |
| `work-log` | multi | — | 工作记录（`logs/`、`community/logs/`） |
| `meeting-note` | multi | §4.6 | 结构化会议笔记 |
| `meeting-transcript` | multi | — | 完整逐字稿（证据层） |
| `daily` | global | — | 每日笔记 |
| `weekly-review` | global | — | 周复盘 |
| `qa-insight` | global | — | 用户显式保存的问答洞察 |
| `inbox` | global | — | `inbox.md` |
| `conventions` | global | — | 本文件 |
| `approval-page` | global | — | `review/meetings.md` |
| `project-inbox` | single | — | `inboxes/<project>.md` |
| `thread-doc` | single | — | AI 产物（阶段总结 / PRD / 背景包） |

> ⚠️ 词表**只做加法**：新增 `type` 必须同步更新 `src/summit_workbench/domain/vault.py` 与测试；
> 删除或改名既有值属于契约级改动，需同步快照与测试。

---

## 4. 固定区块（标题不得改名，Agent 依赖其定位）

### 4.1 线索主页（`workstream`）

`## 现在在哪`、`## 关键结论`、`## 未决问题`、`## 决策记录`、`## 时间线`、`## 关联`

### 4.2 决策记录（`decision`）

`## 背景`、`## 选项`、`## 决定`、`## 理由`、`## 影响`、`## 证据`

`## 证据` 必须逐条给出 `路径#区块` 级出处，并能沿双链走到会议笔记与逐字稿。

### 4.3 原始材料（`source`）

`## 来源`、`## 要点`、`## 关联`

**正文尽量不改写原文**；改写产物放对应 `note`。>1MB 的原件不进 Git，在 `## 来源` 写本机原件路径。

### 4.4 工作思考（`long-form-thought`）

`## 问题缘起`、`## 思考展开`、`## 当前结论`（中间的「思考展开」可按需增加 `###` 三级标题）

### 4.5 项目主页（`project-main`）

`## 当前状态`、`## 下一步`、`## 阻塞`、`## 决策记录`

### 4.6 结构化会议笔记（`meeting-note`）

`## 一分钟摘要`、`## 会议信息`、`## 事实与进展`、`## 已形成决策`、`## 明确行动项`、
`## 未决问题`、`## 关联项目`、`## 证据索引`

会议**明确形成**的行动项只进 `## 明确行动项`；模型推断的下一步不入库（2026-09-18 起）。

---

## 5. 命名

- 文件一律**小写英文 kebab-case**，禁止空格、下划线、冒号、斜杠、连续连字符与 `V1`/`final` 之类状态后缀。
- 笔记：`<YYYYMMDD>-<english-slug>.md`（例：`20260912-hii-hic-ip-overview.md`）
- 主页 / 索引：`<english-slug>.md`（例：`hii-loyalty.md`、`workstreams.md`）
- 逐字稿：`<YYYY-MM-DD>-<english-slug>-transcript.md`（沿用 Workbench 既有格式）
- 模板：`<type>-template.md`
- 中文标题与旧文件名进 `title` / `aliases`。

**重命名流程**：① 全库搜旧文件名与旧双链 → ② 改名（**不改 `id`**）→ ③ 更新双链与 `aliases`
→ ④ 再搜一次确认无残留 → ⑤ 检查 `git diff --summary`。

---

## 6. 附件策略

| 体积 | 处置 |
| --- | --- |
| ≤ 1MB | 放 `<workstream>/sources/attachments/`，**随库进 Git** |
| > 1MB | **不进 Git**（`.gitignore` 已忽略 `**/sources/attachments/oversize/`）；库内只留引用 + 本机原件路径 |

- 原件（PDF / 图片 / 表格 / zip）**不可变**：要改写就新建 `note`，不要就地改原件。
- 从 Git 外引用原件时，在 `## 来源` 写清「本机路径 + 收到日期 + 来源人」，便于换机器后重新放置。

---

## 7. 双链规则（沿用上游）

- 双链用**稳定文件名**作目标，并提供中文别名：`[[hii-loyalty|HII 沟通线索]]`。
- 双链表达**有解释价值的语义关系**，不写「同目录」「同标签」这类可由元数据推导的关系。
- 每篇内容笔记保留 **1–3 条强关联**，并在链接后写**一句关系理由**。
- 同一关系只需在最适合解释它的一篇里写一次；检索会同时遍历出链与入链。
- **新增候选先入确认清单，经人工接受才写回正文**（清单落点见 §13）。
- 机器目录（`_signals/`、`.summit-workbench/`、`templates/`）**不参与双链**。

---

## 8. 决策记录

- 一决策一篇，放 `decisions/`，`type: decision`，文件名 `<YYYYMMDD>-<english-slug>.md`。
- 各线索主页 / 项目主页的 `## 决策记录` 区只放**链接 + 一行摘要**，不复制决策正文。
- 决策被推翻时**不改旧文**：新写一篇并把旧篇 `status` 置 `superseded`，两篇互链。

---

## 9. 索引层（`index/`）

- 索引页只做**导航与简短说明**，不复制正文。
- 新增笔记时同步更新对应索引页（工作线 → `index/workstreams.md`，项目 → `index/projects.md`，
  决策 → `index/decisions.md`，人物 → `index/people.md`，大事 → `index/timeline.md`）。
- 索引页与线索主页在检索中带**权威加权**，因此条目要写「一句话 + 双链」。

---

## 10. 检索约定（Workbench 第二大脑）

- **引用粒度＝`路径#区块`**（vault 相对路径 + `##` 区块标题），与 Obsidian 的
  `[[文件#标题]]` 语法一致，因此在 Workbench 与 Obsidian 里都能直接跳转。
- **只依据召回内容作答**；证据不足必须明说「库里没有」，不得用模型自身知识填补。
- **事实 / 推断 / 建议分层**：事实进 `facts`（必须带出处）；模型判断进 `suggestions`。
- **回溯要能走到底**：`笔记 → 会议笔记 → 逐字稿`。逐字稿不进初始召回（避免淹没信号），
  但通过会议笔记的 `## 证据索引` 双链在**检索轨迹**里显式暴露并可点开。
- **分块**：正文按 `##` 切块；检索命中的是**块**，引用到块，而不是整篇。

---

## 11. `inbox.md` 与 `review/meetings.md` 契约（**不动**）

- 待处理条目必须以 `- [ ] ` 开头，一行一条，可带 `#项目名` 标签；积压数按行数算；
  已处理条目移出「待处理条目」区，**不留占位行**。
- `review/meetings.md` 是会议提取结果影响执行系统前的**唯一审批入口**；
  `- [ ]` 待确认、`- [x]` 批准、`~~条目~~`（可追加 `#ignore`）拒绝。仅保存文件**不会**触发写回。
- 任何改变项目状态 / 下一步 / 阻塞 / 创建飞书任务的写回，必须经该审批入口一次确认。

---

## 12. 分层与证据

事实与待确认推断必须**分层保存与展示**；模型推断的下一步不入库。会议知识可自动归档；
推断内容不得写入事实层。`draft` 状态的内容不进入问答索引。

---

## 13. 入库管线（半自动：原始材料 → AI 结构化 → 人工确认）

```
原始材料（飞书日历 / 任务 / 会议纪要 / 转写 / 文档）
   │ ① 归档为 source 笔记（不可变，保留原文与来源）
   ▼
AI 结构化草稿（status: draft）
   │ ② 提取：事实 / 决策 / 行动项 / 未决问题 / 人物 / 组织 / 时间
   │ ③ 生成：目标笔记 + 双链候选（每条带关系理由）+ 英文 kebab-case 命名建议
   ▼
人工确认：库内候选清单 `review/kb-intake.md`（逐条接受 / 修改 / 拒绝，默认不选中）
   ▼
写回正式笔记（补 frontmatter、更新 index/、更新 timeline）
```

- **判重**：入库前对 `id` / `aliases` / 标题 / `source.ref` 做去重检查；重复时走「合并到已有笔记」。
- **幂等**：同一份原始材料重复入库**不得**产生重复笔记（键 = `source.ref` + 内容哈希）。
- 候选清单是本轮人工确认的落点；`review/meetings.md` 保持其「会议提取唯一入口」语义不变。

---

## 14. 本轮来源范围与将来扩展

- **本轮来源范围**：飞书日历 + 飞书任务 + 会议纪要（含线上会议转写）。
- **飞书日历 / 任务进库形态**：**只**把与某条工作线 / 项目相关的条目结构化进库
  （带飞书 ID、时间、状态、负责人、来源链接）；无关的日常流水**不入库**
  （每日简报快照已落在 `daily/`，需要时可反查）。
- **本轮不做**：微信 / 邮件 / Office 附件 / 内部平台的自动接入；
  结构上不堵死，`source.kind` 词表已为其预留取值。
