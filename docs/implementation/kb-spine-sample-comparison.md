# 工作知识库架构 · 库外样例对照记录（α 工作线优先 / β 项目管线优先）

> 生成日期 2026-09-14 · 样例位置 `/tmp/kb-spine-sample/{alpha,beta}`（**库外临时目录**，正式 `_vault` 未动）
> 唯一素材：`/Users/yifengstudio/Desktop/当前材料/和HII的沟通/HII-HIC_IP关系与沟通全景总结_V2.1_2026-09-12.md`
> （1038 行 / 35985 字节 / sha256 `b541187e6267b132361fb10534e3f58f9c8a21754e5f3eee8a0d36db61ef7402`）
> 生成脚本 `build.py`（可重跑）· 自检 `verify.py` · 检索对比 `compare.py` · 原始输出 `compare-output.txt`
> **两套的差别只有一个**：工作线视角放在独立 `type: workstream` 主页（α），还是收敛进项目主页（β）。

## 1. 概览与校验结果

| 项 | α 工作线优先（改造版） | β 项目管线优先 |
|---|---|---|
| vault 路径 | `/tmp/kb-spine-sample/alpha` | `/tmp/kb-spine-sample/beta` |
| Markdown 篇数 | **15**（含 `hii/hii-loyalty.md`、`index/workstreams.md`） | **13**（无 workstream 主页、无 workstreams 索引） |
| 索引块数 | **136** | **131** |
| `wb vault check <path>` | ✓ 15 篇全部通过（exit 0） | ✓ 13 篇全部通过（exit 0） |
| `wb kb index <vault> --index-file <库外>` | ✓ 136 块，FTS5/trigram 可用（exit 0） | ✓ 131 块，FTS5/trigram 可用（exit 0） |
| 索引库位置 | `/tmp/kb-spine-sample/alpha.sqlite`（**vault 之外**） | `/tmp/kb-spine-sample/beta.sqlite`（**vault 之外**） |
| 双链 / 块锚点自检 | ✓ 0 死链、0 失效锚点 | ✓ 0 死链、0 失效锚点 |
| 检索对比 | 3 问 × （全库 + `project=hii-affairs`），`use_model=False`，未调用任何模型 | 同左 |

`wb vault check <path>` **支持指定路径**（`cli/vault.py:20-33`），`wb kb index` 支持 `--index-file` 且拒绝把索引库放进 vault 内（`cli/kb.py:48-50`）。

## 2. 两套完整目录树（`find` 输出）

```
alpha/inbox.md
alpha/hii/clusters/ip-trademark.md
alpha/hii/notes/20260912-hii-hic-ip-analysis.md
alpha/hii/hii-loyalty.md
alpha/hii/sources/20260912-hii-hic-ip-overview.md
alpha/conventions.md
alpha/projects/hii-affairs.md
alpha/decisions/20260623-hii-registration-entity.md
alpha/decisions/20260623-ip-filing-before-license.md
alpha/decisions/20260912-huoman-vs-hefuman-separate.md
alpha/decisions/20260730-hif-to-hii-scope.md
alpha/README.md
alpha/index/projects.md
alpha/index/workstreams.md
alpha/index/decisions.md
```

```
beta/inbox.md
beta/hii/clusters/ip-trademark.md
beta/hii/notes/20260912-hii-hic-ip-analysis.md
beta/hii/sources/20260912-hii-hic-ip-overview.md
beta/conventions.md
beta/projects/hii-affairs.md
beta/decisions/20260623-hii-registration-entity.md
beta/decisions/20260623-ip-filing-before-license.md
beta/decisions/20260912-huoman-vs-hefuman-separate.md
beta/decisions/20260730-hif-to-hii-scope.md
beta/README.md
beta/index/projects.md
beta/index/decisions.md
```

行数对照：α 合计 2119 行 / β 合计 2049 行；两套的 `hii/sources/*.md` 都是 1111 行（1038 行原件逐字 + 头部）。

## 3. 每个变体一个代表页的完整 frontmatter（原样）

α 的代表页 = 它独有的工作线主页 `alpha/hii/hii-loyalty.md`：

```yaml
id: 2026-09-14-a008
title: HII 事宜（线索主页）
area: work
workstream: hii
project: global
type: workstream
domain: hii
status: active
created: 2026-09-14
updated: 2026-09-14
date: 2026-09-14
summary: HII 工作线的入口页：现状、关键结论、未决问题、决策、时间线（α 变体独有）。
tags: [workstream, hii]
aliases: [HII 沟通线索, HII 事宜线索主页]
people: [曹木子, 罗艺峰]
org: [HIC, HII]
confidential: false
```

β 的代表页 = 它唯一的入口页 `beta/projects/hii-affairs.md`（α 的同名页只有四固定区块 + 主题簇）：

```yaml
id: 2026-09-14-b006
title: HII 事宜
area: work
workstream: hii
project: hii-affairs
type: project-main
domain: hii
status: active
created: 2026-09-14
updated: 2026-09-14
date: 2026-09-14
summary: HII 事宜（Hoffman 授权、商标 IP、Loyalty、人员往来）的唯一入口页：项目四区块 + 工作线六区块 + 主题簇。
tags: [project, hii]
aliases: [HII 事宜, HII Affairs]
people: []
org: [HIC, HII]
confidential: false
```

决策页在公共字段**之后**追加（两套相同，`fixed` 顺序未被打乱）：

```yaml
decision_status: effective
decided_on: 2026-06-23
review_on: 2026-12-31
```

`source` 字段（原件页，逐字入库的幂等键）：

```yaml
source:
  kind: doc
  ref: /Users/yifengstudio/Desktop/当前材料/和HII的沟通/HII-HIC_IP关系与沟通全景总结_V2.1_2026-09-12.md
  date: 2026-09-12
  hash: b541187e6267b132
```

## 4. 双链清单（每篇写了哪些 `[[…]]`、关系理由）

两套的链接**内容相同**，只有「指向哪个入口页」不同（α→`hii-loyalty`，β→`hii-affairs`）。

- `hii/notes/20260912-hii-hic-ip-analysis.md`（14 条，全部带块锚点）：`[[20260912-hii-hic-ip-overview#2.1 HII 核心 IP 体系|来源·2.1]]` 等 —— 每条结论一对一挂原件对应区块，理由「本文每条结论都能在原件对应区块逐字核对」；末尾 `[[ip-trademark|商标 IP 主题簇]]`（结论归档到簇页）、`[[hii-loyalty|HII 事宜线索主页]]`／`[[hii-affairs|HII 事宜项目主页]]`（结论的入口）、`[[20260912-hii-hic-ip-overview|IP 全景原件]]`（取原文）。
- `hii/sources/20260912-hii-hic-ip-overview.md`（3 条）：回链分析页（「结论已拆到该分析笔记，引用结论请引分析笔记」）、簇页（「本件是簇页与 4 篇决策卡的唯一证据来源」）、入口页。
- `hii/clusters/ip-trademark.md`（7 条）：4 篇决策（`## 决策记录` 一行摘要 + 生效日）、分析页（「引用结论优先引它」）、入口页、原件页。
- `projects/hii-affairs.md`：4 篇决策 + 主题簇 `[[ip-trademark|商标 IP]]`；α 版另有 `[[hii-loyalty|HII 事宜线索主页]]`（「两页内容有意重叠」），β 版另有 `## 关联` 三条（簇页 / 分析页 / 原件页）。
- `hii/hii-loyalty.md`（α 独有，7 条）：4 篇决策 + 簇页（「本页只保留一句话级结论」）+ 分析页（「引用请引下层」）+ `[[hii-affairs|HII 事宜项目主页]]`（「本页负责工作线视角」）。
- 4 篇 `decisions/*.md`（各 2 条）：`[[ip-trademark|商标 IP 主题簇]]`（「本决策挂在该簇 `## 决策记录` 下」）+ 分析页或原件页（「出处见其 6.2 / 4.2 / 7.1 区块」）。链接写在 `## 影响` 末尾。
- `index/projects.md`：`[[hii-affairs|项目主页]]` + `[[ip-trademark|商标 IP]]`。
- `index/decisions.md`：4 篇决策 × 2 条（决策 + 所属簇）。
- `index/workstreams.md`（α 独有）：`[[hii-loyalty|HII 事宜线索主页]]`。
- `README.md`、`conventions.md`：导航与规范示例链接（`[[ip-trademark|商标 IP]]`、`[[ip-trademark#关键结论|商标 IP·关键结论]]`）。

## 5. 检索对比表（同一问题，两套各跑；`use_model=False`）

路由与命中块数在两套间几乎一致（α 命中 106/105/36，β 103/102/33），**差异全部集中在入口页归属**。

| 问题 | α 全库 top-1…top-5 | β 全库 top-1…top-5 | 关键块命中差异 |
|---|---|---|---|
| Q1 商标共识规范 | 1 `hii/hii-loyalty#关键结论` 2 `README#怎么用` 3 `…registration-entity#选项` 4 `…filing-before-license#影响` 5 `…hif-to-hii-scope#影响` | 1 `projects/hii-affairs#关键结论` 2 `README#怎么用` 3–5 同 α | 两套都**未命中**期望的 `clusters/ip-trademark#关键结论`（同篇第 7 名前的 `#现在在哪`）、`notes/…#结论二`、`decisions/…#决定`、`source#6.1`；α 另有 `index/workstreams` 第 9、`projects/hii-affairs#主题簇` 第 10 |
| Q2 HII vs HIF | 1 `notes/…#结论三｜HII 与 HIF 不能做全局替换` 2 `…hif-to-hii-scope#证据` 3 `…hif-to-hii-scope` 4 `…hif-to-hii-scope#背景` 5 `README#怎么用`（α 另在第 6 名出 `hii/hii-loyalty#决策记录`、第 7 名 `projects/hii-affairs#决策记录`） | 1 同 α 2–4 同 α 5 `projects/hii-affairs#决策记录` | 两套 top-1 都正确；`decisions/…hif-to-hii-scope#决定` 都只在同篇出现（块不同），`clusters#关键结论` 与 `source#6.2` **均未召回** |
| Q3 活满 vs 和夫曼之旅 | 1 `decisions/20260912-huoman-vs-hefuman-separate` 2 `…#决定` 3 `…#证据` 4 `notes/…#结论六｜「活满」与「和夫曼之旅」从此分开管理` 5 `clusters/ip-trademark#现在在哪`（α 第 6 名 `hii/hii-loyalty#关键结论`） | 1–6 同 α（β 第 6 名 `index/decisions`，第 7 名 `projects/hii-affairs#关键结论`） | 期望 4 块命中 2 块；`clusters#关键结论` 两套都「同篇命中但块不同」，`source#9.2` **两套都未召回** |

**加 `project=hii-affairs` 过滤后（这是两套真正的分水岭）：**

| 问题 | α（过滤后） | β（过滤后） |
|---|---|---|
| Q1 | **top-1 掉成 `notes/…#未决与待确认`**（`hii-loyalty` 是 `project: global` 被丢弃）；但 `hii/hii-loyalty` 仍以**双链扩展**形式出现在轨迹里 | **top-1 仍是 `projects/hii-affairs#关键结论`**（项目绑定，未被过滤）；`README`（global）以双链扩展形式进入 |
| Q2 | 与全库几乎一致 | 与全库几乎一致 |
| Q3 | 第 6 名 `hii/hii-loyalty`（双链扩展带回的**前言块**） | 第 7 名 `projects/hii-affairs#关键结论`（直接命中） |

**一句话**：全库检索时 α 略优（多一个 0.95 权威的 workstream 页把入口结论顶到 top-1，Q1/Q3 都更快命中入口结论）；**一旦限定项目，β 明显更稳**——α 的入口页整页消失，Q1 的 top-1 从「入口关键结论」退化成「未决与待确认」，只剩双链扩展把它的前言块捞回来；β 的入口页因为 `project: hii-affairs` 而始终在场。

## 6. 取舍分析（各维度一句结论）

| 维度 | α 工作线优先 | β 项目管线优先 |
|---|---|---|
| **用户能懂** | 更贴真实心智（一条工作线一个主页），但同一结论在主页与簇页各写一遍，改一处漏一处就会自相矛盾 | 一页到底、界面与库完全一致，「首页在哪」没有歧义；代价是入口页 97 行、区块 10 个，页面偏长 |
| **机器能懂** | 多一个 `type: workstream`（权威 0.95）承载工作线，检索侧多一个高权威信号；但该页 `project: global`，一加项目过滤就整页失效 | 入口页 `type: project-main`（权威 0.85）同时是项目页与工作线页，项目过滤下始终在场；工作线维度只剩 frontmatter 字段，检索侧无加权落点 |
| **可扩展** | 每加一个主题要多维护两处（线索主页 + 簇页）；`workstream` 层未来会随工作线数量线性增长 | 每加一个主题只改两处（项目主页 `## 主题簇` + `index/projects.md`）；`projects/` 数量恒定，界面不膨胀 |
| **与 app 契约的贴合度** | 两处「都像首页」，审批写回要额外决定落哪一页；`workstream` 虽是 app 已有 type，但其 `scope: global` 与「项目过滤」天然冲突 | 完全贴合：唯一入口＝`projects/*.md` 的 `project-main`，审批落点、项目过滤、界面三处指向同一页 |

> 注（2026-09-14）：β 落地后项目页由 2 个扩至 **5 个**（新增活满社群、活满后勤&行政、公司人事）。
> 这不改变本表结论——要点是「数量**恒定**」而非「恒定为 2」；契约级变更流程见 `_vault/conventions.md` §13.3。

## 7. 发现的问题（样例过程中真实暴露）

1. **【锚点体系对 `#` 一级标题失效】原件用 H1 分节，段落无法被 `路径#区块` 引用。**
   `alpha/hii/sources/20260912-hii-hic-ip-overview.md`（逐字原文自第 62 行起）：原件 17 个一级章节
   （一～十七 + 附录 A/B）**没有 H2 锚点**，其正文被并入上一个二级块——实测
   `# 十、版权 filing 仍存在一个邮件内部口径差异` 与 `# 十一、关键时间线` 的开头并入 `## 9.2 …` 块，
   `# 十三、…状态表` 与 `# 十四、…` 并入 `## HIC / China 侧` 块，`# 十七、一句话总览` + 附录 A/B
   并入 `## P2｜形成 Core IP Definition` 块。可引用的只有原件 49 个 H2。
   分析笔记第 154 行因此只能写「引宿主块并注明真实章节名」。**这是 PLAN §10 铁律 6 的同类坑，且更隐蔽**
   （上一轮是 H2 降级，这一轮是 H1 根本没有锚点）。修复方向：入库时给一级章节补一个二级标题，或把引用粒度从 `##` 扩到 `#`。
2. **【过滤与双链扩展不一致】双链扩展不受 `project` / `workstream` 过滤约束。**
   过滤在 `src/summit_workbench/workflows/ask/fusion.py:174-179`，双链扩展在 `fusion.py:243-295`（没有重复过滤）。
   实测：α 用 `project=hii-affairs` 过滤后，`hii/hii-loyalty`（`project: global`）仍在 Q2/Q3 出现（第 6–7 名）；
   β 过滤后 `README`（`project: global`）仍在 Q1 第 2 名。**结论：按项目过滤得不到纯净的项目视图**，
   过滤结果里会混进 global 页。
3. **【α 的结构性风险被证实】`type: workstream` 的 `scope: global` 与项目过滤天然冲突。**
   `alpha/hii/hii-loyalty.md` frontmatter 是 `project: global`（`type: workstream` 强制，`domain/vault.py:87-97`）。
   全库 top-1 是它，加了 `project=hii-affairs` 之后直接消失，Q1 的 top-1 退化成
   `notes/…#未决与待确认`（带着「未决」字样的块）。这与 PLAN §2 期望的「项目/主题过滤」目标直接打架。
4. **【权威加权未校准被实测证实】真正逐条的规范块排不进 top-10。**
   Q1 两套的 `clusters/ip-trademark#关键结论`（8 条商标共识规范原文）、`notes/…#结论二｜登记主体统一为 HII`、
   `decisions/20260623-hii-registration-entity#决定`、`source#6.1 HII 的正式登记主体名称` **全部未进 top-10**，
   被 `clusters#现在在哪`（第 7 名）、`README#怎么用`（第 2 名）、`index/*` 等概括性/导航块挤掉。
   这正是 PLAN §2「检索缺口：权威加权对『项目主页 + 主题簇页』未校准」的现场证据。
5. **【路由缺口】Q2 / Q3 都没走 `decision` 路由。**
   `wb kb route`（`heuristic_route`）把「HII 与 HIF 是同一个主体吗？内部编辑时怎么处理？」判成 `synthesis`、
   把「『活满』与『和夫曼之旅』为什么分开管理？」判成 `point`（原因都是「无关键词：按长度兜底」）。
   Q1 因为含「共识 / 规范」才走到 `decision`。路由不中时靠融合兜底，实测 top-1 仍正确（Q2/Q3 均命中 `notes#结论三/#结论六`），
   但 `decisions/*#决定` 这类最该被顶起的块没有拿到路由优先权重。
6. **【决策页没有放双链的位置】六区块里没有 `## 关联`。**
   decision 的固定区块是 `背景/选项/决定/理由/影响/证据`（`domain/vault.py:101-111`），
   而 conventions 要求每篇 1–3 条强关联 + 一句关系理由。样例只能把双链塞进 `## 影响` 末尾
   （`decisions/20260623-hii-registration-entity.md:67-68` 等 4 篇）。**语义不符**（影响 ≠ 关联），
   建议要么给 decision 加第 7 区块 `## 关联`，要么在 conventions 里把这条权宜写法定成规范。
7. **【根目录 `README.md` / `sop.md` 必须带 frontmatter】否则 `wb vault check` 必红。**
   `iter_markdown_files` 只跳过 `.git/.obsidian/_signals/templates`（`repositories/vault.py:22`），
   `parse_frontmatter` 对没有 `---` 开头的文件直接返回 `"缺少 frontmatter"`（同文件 `vault.py:39-40`）。
   PLAN §3.2 把 `README.md`、`sop.md` 画在库根，但没写它们的 `type`。样例里 `README.md` 用
   `type: index / project: global` 才过校验（`alpha/README.md:1-16`）；`sop.md` 若照此入库同样需要。
8. **【`## 主题簇` 的「加一行」会立刻产生死链】** PLAN §3.1 说新增主题「在项目主页 `## 主题簇` 加一行」，
   但【HII 事宜】的另两个簇（Loyalty(royalty)、日常人员往来(relationships)）本轮无素材。
   样例因此在 `alpha/projects/hii-affairs.md:56` 与 `beta/projects/hii-affairs.md:91` 用**纯文本**列出待建簇，
   不写 `[[…]]`——否则 `verify.py` 会立刻报死链。**约定需要写明：待建簇不写双链。**
9. **【`source.ref` 语义冲突】** PLAN §3.3 的示例把 `ref` 写成 `hii/sources/20260912-hii-hic-ip-overview.md`（自指本页），
   而幂等键定义为 `source.ref + source.hash`（§4 执行细则 1）。样例按「真溯源」写成**桌面原件绝对路径**，
   于是封面页的 ref 与自指解释不能同时成立。**需要冻结一件事**：`ref` 是「原件位置」还是「本页路径」
   （若是前者，原件在桌面而不在库内时，换机器后该路径可能失效，应同时记录 vault 内副本路径）。
10. **【长 source 让单篇贡献 54 个块】** `hii/sources/…overview.md` 一篇 54 块（头部 5 + 原件 49），
    靠 `source_penalty=0.55`（`fusion.py:218`）与 `max_chunks_per_note=3`（`fusion.py:49`）兜住。
    实测 `source` 的块**没有**进过任何一题的 top-10，但 `## 要点` 这种概括块一旦命中会同时命中
    `## 关联`（NAV 降权）——建议在 conventions 里明确「原件是否值得整篇入索引」，或给 source 只索引头部三块 + 关键区块白名单。

## 8. 两套逐项差异清单

| 文件 | α 有 β 无 | 内容差异（其余全部逐字相同） |
|---|---|---|
| `projects/hii-affairs.md` | — | α：四固定区块 + `## 主题簇`（58 行）；β：四固定区块 + `## 关键结论` + `## 未决问题` + `## 时间线` + `## 关联` + `## 主题簇`（97 行） |
| `hii/hii-loyalty.md` | **α 独有** | `type: workstream`、`project: global`、六区块（77 行） |
| `index/workstreams.md` | **α 独有** | 工作线索引（33 行）；β 的库规范明确「不设本页」 |
| `index/projects.md` | — | 相同（35 行） |
| `index/decisions.md` | — | 相同（35 行） |
| `inbox.md` | — | 相同（31 行，5 条 `- [ ] `） |
| `README.md` | — | 入口导航不同：α 指向 `hii-loyalty`，β 指向 `hii-affairs`；均 48 行 |
| `conventions.md` | — | α 137 行 / β 138 行；§1 目录树、§3 scope 表、§4 区块映射、§9 扩展规则目标页不同 |
| `hii/clusters/ip-trademark.md` | — | 正文 87 行逐字相同，仅 `## 关联` 的入口页链接不同（α→`hii-loyalty`，β→`hii-affairs`） |
| `hii/notes/20260912-hii-hic-ip-analysis.md` | — | 正文 165 行逐字相同，仅 `## 关联` 的入口页链接不同 |
| `hii/sources/20260912-hii-hic-ip-overview.md` | — | 正文 1111 行逐字相同，仅 `## 关联` 的入口页链接不同 |
| `decisions/*.md`（4 篇） | — | 正文逐字相同；仅 `id` 前缀 `a00c–a00f` / `b00c–b00f` 不同 |

## 9. 复现命令

```bash
V=/Users/yifengstudio/Documents/GitHub/SummitWorkbench/.venv/bin
$V/python /tmp/kb-spine-sample/build.py                     # 重建两套样例库
$V/wb vault check /tmp/kb-spine-sample/alpha                # 期望 exit 0
$V/wb vault check /tmp/kb-spine-sample/beta                 # 期望 exit 0
$V/python /tmp/kb-spine-sample/verify.py                    # 期望 ✓ 0 死链 / 0 失效锚点
$V/python /tmp/kb-spine-sample/compare.py --cli             # 只检索不调模型；含 CLI 路径验证
```
