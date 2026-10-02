# 工作知识库检索契约（WORK-KB-RETRIEVAL-CONTRACT）

> **新版工作区补充（2026-10-02）**：新版工作库可以是用户选择的任意本地或 OneDrive 目录，不再要求工作库是 Git 仓库。跨设备同步由 OneDrive 客户端负责；本地写盘不等于云端同步完成。新版正式内容需具有匹配当前版本的批准证明才能检索，契约定义见 [SWB-WORKSPACE-CONTRACT-v1](SWB-WORKSPACE-CONTRACT-v1.md)。真实旧 `_vault` 的原有目录与 §9.1 接口契约继续按其自身 `conventions.md` 维护；第一阶段不得迁移或改写它。

> 状态：生效（v0.4.9 起）。
> 适用范围：`~/Documents/Work/_vault/`（下称**工作库**）的全部 Markdown。
> 双方：**SummitWorkbench（SWB）是写入方**，**SummitKnowledge（SK）是检索方**。
> 本文件只写契约（字段、语义、边界），**不含任何一方的实现细节、API 配置或算法参数**。
>
> **2026-09-17 边界校正**：SWB 已退役 `wb ask`、`wb kb`、本地 SQLite/FTS/BM25 索引与问答生成；本契约只描述写入格式和 SK 的读取语义。`qa-insight` 仅作为历史兼容类型保留，不再由 SWB 生成。

---

## 1. 定位与边界

| 系统 | 职责 | 明确不做 |
|---|---|---|
| **SummitWorkbench** | 看板、采集、审批、源数据处理；决定「什么内容、以什么状态、落到哪一页」 | 不做 embedding、不建向量库、不做语义精排 |
| **SummitKnowledge** | 跨个人库/工作库的语义检索与长期记忆体验；切块、召回、精排、生成 | 不写工作库（工作库对 SK 只读） |

高级语义检索、切块、召回、精排和问答均由 SummitKnowledge 负责；SWB 不提供本地检索命令或索引。

**写入方承诺**：SWB 自动沉淀进工作库的每一篇 Markdown 都必须满足本契约（§8 有可执行校验）。
**检索方承诺**：SK 按本契约解释区块边界、状态与权威顺序；不得自行改写工作库文件。

---

## 2. 共享引用契约

```
source_id = 相对当前知识库根目录的 POSIX 路径，不含 .md
heading   = Markdown 标题文字，不含 # 前缀
anchor    = heading 非空时为 source_id#heading，否则为 source_id
```

- 知识库根：个人库 = MyKnowledge 根；工作库 = `_vault` 根。**同一个 `source_id` 在不同库里指不同文件**，因此引用必须带库上下文（profile）。
- `source_file` 内部可以保留 `.md`；对外生成 `source_id` 时统一去掉后缀。
- 例：`_vault/hii-ip-license/ip-trademark.md` 的 `## 关键结论` → `hii-ip-license/ip-trademark#关键结论`。
- 文件级引用（整篇）用 `source_id` 本身，此时 `heading=""`。

---

## 3. 状态语义

| status | 含义 | 事实问答中的处理 |
|---|---|---|
| `active` | 正常参与回答 | 正常参与 |
| `paused` | 可检索，但「当前状态 / 下一步」类问题降低时效权重 | 降权 |
| `archived` | 历史项目已结束；**不代表内容错误或被推翻** | 保留历史知识资格；只在「当前状态」类问题降时效权重 |
| `generated` | 派生内容，低权威 | 可参与回答，**不能单独支撑高置信事实** |
| `applied` | 已确认或已应用内容 | 正常参与 |
| `superseded` | 已被替代 | 默认降权并明确标注被替代；必须能顺着替代链接找到新结论 |
| `draft` | 草稿 | **不进入事实问答** |
| `pending-review` | 待确认 | **不进入事实问答** |
| `ignored` | 已忽略 | **不进入事实问答** |

**硬规则**：

1. `draft` / `pending-review` / `ignored` 可以合法保存，但**不构成事实语料**——它们可以在批准后流转为 `applied` 再参与回答。
2. `archived` ≠ `superseded`。项目结束不等于结论被推翻；把 `archived` 当成「被推翻」是错误解释。
3. `status: superseded` 的决策必须同时带 `decision_status: superseded` 与 `superseded_by: <替代页 source_id>`。

---

## 4. 块边界与切块口径

| 规则 | 说明 |
|---|---|
| 文首 H1 | 是**笔记标题**，不产生独立的可引用块 |
| `#` 与 `##` | 是块边界 |
| `###` 及更深 | 留在父块内，**不**成为引用边界 |
| 围栏代码块（``` / ~~~） | 其中的 `#` 是代码，不产生边界 |
| 首个区块前的正文 | 形成文件级块，`heading=""` |
| 重复标题 | **不得**生成「标题 2」这类假引用；出现重复可引用标题时，退化为文件级引用并记录诊断 |
| 超长区块 | 可按段落拆分，但所有子块继承**同一个**合法 heading |

---

## 5. 类型分层

### 5.1 会被检索的类型

`project-main`、`work-log`、`thread-doc`、`meeting-note`、
`workstream`、`note`、`decision`、`long-form-thought`。

### 5.2 只写不检索的类型

`index`（MOC 导航）、`conventions`（规范）、`inbox` / `project-inbox`（收件箱）、
`approval-page`（审批页）、`prompt`、`workflow`、`standard`、`template`、`qa-insight`、
`meeting-transcript`（原始逐字稿，仅供证据回链）、
`source`（原件层，仅作可点开的证据文件）、
`daily` / `weekly-review`（2026-09-19 起**不落在工作库内**：简报与周复盘由 SWB 写在本机
程序目录，见 `_vault/conventions.md` §1/§3；检索侧保留排除条目作为"防旧 App 回写"的保险）。

这些类型正文结构自由，**不要求**有 `##`，也不做检索就绪校验。

> `source` 是**例外**：它只写不检索，但仍须按 §5.3 写固定区块——写作结构不变，
> 只是不参与检索；这是「结构校验」与「检索就绪校验」两层职责的区别。

### 5.3 固定区块类型

`project-main`、`decision`、`meeting-note`、`source`、`long-form-thought`、`workstream`
继续执行 vault schema 的固定区块规则（区块名不得改名）。

短笔记（`note`）、`work-log`、`thread-doc` **允许文件级引用**：没有 `##` 不是缺陷。

---

## 6. 工作库权威顺序

在**语义相关**的候选内排序时使用，顺序如下（高 → 低）：

1. 当前项目主页、主题结论、有效决策。
2. 已应用内容、结构化会议笔记、周期复盘。
3. `thread-doc`、纯机器生成的日志（`generated`）和其他 `generated` 内容。

`source` 与 `meeting-transcript` 是**证据层**：**不进入工作库检索语料、不参与精排候选**
（§5.2）；要核对原文口径时，由结论页里的出处链接点开原件。需要检索会议内容时，使用结构化的
`meeting-note` 及其证据索引。

**硬规则**：权威度**只能**在语义相关候选中调整，不得让无关的「高权威页面」强行上榜。

---

## 7. 证据层不可变

- `source` 是**原件层**，保存后正文不可被自动规范化器改写。
- `meeting-transcript` 同样是不可变的原始记录，但不属于工作库检索语料，也不进入精排候选。
- 会议逐字稿按现有哈希与幂等规则归档：同内容重复归档空转，不覆盖既有证据文件。
- 派生内容（会议笔记、日志、产物）必须保留回链到原件的引用与证据文本。

---

## 8. 写入方可执行校验

SWB 侧对应三个纯逻辑入口（`src/summit_workbench/domain/`）：

| 入口 | 作用 |
|---|---|
| `validate_note(meta, body)` | vault schema：必填 frontmatter、status 词表、type 范围、项目作用域、固定区块 |
| `validate_retrieval_readiness(meta, body)` | 本契约的检索就绪校验 |
| `is_fact_retrieval_eligible(meta)` | 是否构成事实问答语料（§3 的 status 规则） |

`validate_retrieval_readiness` 覆盖：

1. 只对**会被检索的类型**校验（§5.1）。
2. 固定区块类型继续检查固定区块（§5.3）。
3. 检查**围栏代码块之外**的 H1/H2 是否重复；重复即错误，**不自动改名**。
4. 未闭合的代码围栏即错误（无法确定区块边界）。
5. `superseded` 决策必须带替代链接（§3 硬规则 3）。
6. `archived` 是合法历史知识；`generated` 合法但低权威；`draft`/`pending-review`/`ignored` 合法保存但不进事实语料。

校验失败时写入方**拒绝落盘**，不写半成品。已存在的库文件由 `wb vault check`
一并扫描（`check_vault` 先跑 `validate_note`、再跑 `validate_retrieval_readiness`），
因此「重复 H2 / superseded 缺替代链接」不会等到 SK 侧引用退化才暴露。

**写入方必须落 `area` 与 `title`**（2026-09-15/16 两次真实提问实测的字段缺口）：

- **`area: work`** —— SK 侧「综合/总览」类问题按 `area` 过滤笔记总览。缺 `area` 的页面
  仍然**能**被向量/关键词检索召回，但会从**总览清单里静默消失**（实测：62 篇的库，
  总览只报 60 篇）。
- **`title`** —— 缺 `title` 时 SK 回退成文件名，总览里出现 `《2026-09-14》` 这类纯日期条目，
  语义全丢。标题取正文 H1，不得另造。
- 这两项由**写入端**产出（`daily/`、`logs/`、`artifacts/` 三条写入路径），不靠人工后补——
  手补会在下次生成时丢失。

---

## 9. 写入路径与校验点

| 写入物 | 校验 |
|---|---|
| 会议逐字稿（`meeting-transcript`） | 原件不可变；不套用规范化器；不进入检索与精排 |
| 结构化会议笔记（`meeting-note`） | `validate_note` + `validate_retrieval_readiness`；生成态 `pending-review` |
| 当日简报（`daily`） | 程序生成；落 `area: work` + `title: 晨间简报 <日期>`（否则总览不可见 / 只剩日期） |
| 推进日志（`work-log`） | 确定性结构规范化 + 双重校验；**形态两套**（「日常手记」五区块 / 「推进日志」`## 原文`）与 **`status` 解耦**——按来源取 `active`（手写）/ `generated`（纯机器产物）；「模型未消化」由 `summary` 字段缺失表达，不用 `draft` 降级；落 `area: work` + 与 H1 一致的 `title`；单个 `##` 区块 ≤ ~1500 字符（超长会被切成共享同一锚点的子块） |
| AI 产物（`thread-doc`） | 确定性结构规范化 + 双重校验；无 `summary` 为 `draft`，有 `summary` 为 `generated`；无论调用方是否给标题都落最终 heading 作为 `title` |
| 审批写回（主档案 / inbox / 知识沉淀） | 目标页与区块必须存在且**唯一**；锚点无法解析即拒批；**知识沉淀写回必须带可解析的 `<会议笔记 source_id>#<区块>` 出处**（附证据锚点），不得只留裸时间戳 |
| 收件箱提升（`inbox.md` → 项目页 / 飞书 / `thinking/`） | 契约 §10 的三种落点，**各复用既有写入实现**（项目页 `## 下一步`/`## 跟进事项`、审批同一条 outbox、思考与 `/api/journal/thought` 同一函数）；提升后条目**移出收件箱、不留占位行**，且与目标写在**同一个提交**里。落到飞书的那条**库内不留可检索正文**，只在 `review/archive/`（`approval-page`，不进语料）留痕 |
| 原件（`source`） | 逐字保存，不由模型改写 |
| 存量库文件 | `wb vault check`（`wb doctor` 复用）批量扫描两层校验 |

---

## 10. 变更流程

- 本契约的任何变更必须**同时**改 SWB 侧可执行校验与其单测；文档与代码不得漂移。
- SK 侧若要改变对区块边界 / 状态 / 权威顺序的解释，必须先改本文件，再改实现。
- 涉及真实工作库的规范文本（`_vault/conventions.md`）由 SWB 单独提交，只写规范，不写实现细节。

---

## 附：相关文档

- 产品边界：[`docs/product/PRD.md`](../product/PRD.md) §3.1.2 / §3.1.3 / §3.1.6 / §3.2.6
- 工作库规范：`_vault/conventions.md`（真实库内，检索契约章节）
- 当前校验入口：`wb vault check`、`scripts/kb_verify_links.py`；语义检索验收由 SummitKnowledge 负责。
