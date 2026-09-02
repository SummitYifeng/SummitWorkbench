# 第二大脑对话化（Ask Chat）：需求对齐记录（2026-09-02）

> 本文档记录「第二大脑挪到导航栏 + 对话形式 + 10 会话」的需求对齐结论，供实现轮直接开工。
> 对齐方式：AskUserQuestion 五道选择题，用户全部选了推荐项，无异议项。

## 用户原始诉求

1. 第二大脑放在导航栏「今日 - 审批 - 第二大脑」，方便以后扩展；输入框回车即提问、Shift+Enter 换行。
2. 第二大脑做成对话（chat）形式，可存 10 个会话、可切换查看。

## 现状事实（实现前已核查）

- 导航只有「今日 / 审批」两个 tab；问答区在今日页内（`web/src/main.ts`：`renderToday()` 的 askHtml + `bindAsk()`）。
- `/api/ask`（`webapp/app.py:446`）是**单轮**问答：`workflows/ask/ask.py::answer_question(vault_dir, question)` 每次独立对 vault 召回，结构化回答（summary + 带来源 facts + suggestions + conflicts）渲染成 `answer_html`。**无任何多轮上下文/记忆**。
- 问答 bug 修复（`lastAnswerHtml` 持久化，见 HANDOFF_web_ux_fixes.md ①）与新结构的关系：答案状态应随会话消息存储迁移，不再依赖 `renderToday()` 的局部 DOM 重建。

## 对齐结论（五条，全部=推荐项）

| # | 决策点 | 结论 |
|---|---|---|
| 1 | 导航结构 | 顶部导航变「今日 / 审批 / 第二大脑」；第二大脑独立成页（会话列表 + 聊天区）；**今日页移除问答区**（不再与今日信息混排） |
| 2 | 对话记忆级别 | **追问级**：同一会话内把前几轮的问题 + 它们引用过的来源 id 带给下一轮（可追问「那后来呢 / 具体哪次会」）；AI 仍只从 vault 召回事实，**不把 AI 自己的历史回答当事实**（守住「事实必须有来源」） |
| 3 | 会话存储 | **浏览器 localStorage**：面板刷新/重启仍在；不进 vault、不污染第二大脑知识库；换浏览器/机器不带 |
| 4 | 切换 UI | **左侧会话列表**（类聊天 App）：新会话按钮 + 列表 + 当前高亮；自动用首问前 ~12 字命名；支持 ✎ 重命名、✕ 删除；上限 10 |
| 5 | 满额与输入键 | 满 10 个后「新会话」置灰并提示「已满 10 个，请先删除/清空一个」；**回车 = 提问**（中文输入法组词时的回车不触发，即 IME 保护）、**Shift+Enter = 换行**；提问按钮保留作备选 |

## 实现要点（给实现轮）

### 前端（`web/src/main.ts` / `web/src/style.css`）

- `Tab` 扩展为 `'today' | 'review' | 'ask'`；`renderShell()` 加第三个 tab（无徽标即可）；`render()` 分发到 `renderAsk(view)`；`view-ask` 新 section。
- `renderToday()` 移除 ask 区与 `bindAsk()`；`lastAnswerHtml` 逻辑随消息存储迁移后删除（或保留仅兼容 SSR 之外的过渡，实现时定）。
- 会话数据模型（localStorage 单 key，如 `wb.askThreads`）：
  ```ts
  interface AskMsg { role: 'user' | 'ai'; html: string; sources: string[]; ts: string }
  interface AskThread { id: string; title: string; createdAt: string; messages: AskMsg[] }
  // state: threads: AskThread[]（cap 10）+ activeThreadId
  ```
  - `sources`（该轮引用来源 id）与 `html`（答案渲染结果）都要存，追问时把前几轮 `{问题原文, sources}` 发给后端。
  - 消息 html 存库即可，聊天区渲染无需每次重跑 markdown。
- 输入键处理（textarea，keydown）：
  - `Enter` 且非 shift 且非 IME 组词（`e.isComposing || e.keyCode === 229`）→ `preventDefault()` + 提交；
  - `Shift+Enter` → 默认换行（不拦截）。
- 聊天 UI：用户气泡 / AI 气泡（复用现有 `.answer` 的 md→html 产物与来源样式）；等待时「思考中…」指示；自动滚到底；提问按钮保留。
- 会话栏：新会话（满 10 置灰 + 提示）、列表高亮、✎ 重命名（inline input）、✕ 删除（confirm）。
- 60s `refreshState()` 只重绘今日页，第二大脑页状态在 localStorage，不因定时刷新丢消息——天然规避旧 bug。

### 后端（追问级上下文）

- `POST /api/ask` 请求体扩展：`{ question, history?: [{ question: string, sources: string[] }] }`（history 由前端从当前会话的前几轮组装，仅携带**问题原文 + 当时引用来源 id**，不带 AI 答案全文）。
- `workflows/ask/ask.py::answer_question(vault_dir, question, history=None)`：
  - 有 history 时：把前几轮问题作为「用户此前问过的背景」放进 prompt（明确标注为历史问题，非 vault 事实）；允许把历史轮引用过的来源 id **重新纳入本次召回候选**（保证「那后来呢」能引用同一批笔记），仍走现有 budget 截断。
  - 事实/冲突仍只允许引用本次提供的来源（`_ground` 越界核验逻辑不变）——AI 历史答案不进入来源集合。
- `_ask_html`（`app.py:122`）与 SSR `/ask` 兼容路由签名同步（SSR 保持单轮，传空 history）。
- 文档/提示词里写明：模型不得把历史轮 AI 回答当作 vault 事实。

### 不改的部分

- SSR 看板兼容路由保留单轮问答（旧入口与既有测试继续可用）。
- `/api/state`、today 页其它区块不变。
- 审批 / M4 不动（M4 设计见 HANDOFF_web_ux_fixes.md 执行记录）。

### 测试与验证

- Python：ask workflow 单测补 history 上下文用例（无 history 行为不变；有 history 时来源集合含历史引用、事实核验仍只认本次来源）。
- 前端无单测基建（现状），构建后手动验证清单：
  1. 回车提交 / Shift+Enter 换行 / 中文输入法选词回车不误提交；
  2. 新会话 → 问 A → 追问 B（引用 A 的话题）能答；AI 气泡含来源；
  3. 建满 10 会话后新建置灰；✎ 重命名、✕ 删除、切换会话内容互不串；
  4. 刷新页面消息仍在（localStorage）；等 >60s 消息不丢；
  5. 今日页不再显示问答区。

## 实现状态（2026-09-02 同日已实现并提交）

五条结论全部落地，与对齐记录的差异仅一处小增强（草稿保护）：

- **导航**：`Tab` 扩为 `today | review | ask`；`renderShell()` 加「第二大脑」tab 与 `#view-ask`；`render()` 分发 `renderAsk()`。今日页问答区已移除（`renderToday` 不再含 ask 区/`bindAsk`/`lastAnswerHtml`）。
- **对话 UI**：左侧会话列表（新建/切换/✎ 重命名/✕ 删除/当前高亮），上限 10（满额禁用新建并提示）；聊天区用户/AI 气泡（AI 复用服务端 `answer_html`），等待时「思考中…」；输入区保留「提问」按钮，提示「Enter 提问 · Shift+Enter 换行」。
- **输入键**：keydown 处理——Enter 且非 Shift 且非 IME 组词（`isComposing || keyCode===229`）→ `preventDefault` + 提交；Shift+Enter 走默认换行。
- **存储**：localStorage `wb.ask.threads.v1`（线程+activeId），刷新/重启仍在；消息体存用户原文 + AI html + 该轮 `sources`。
- **追问级上下文（后端）**：
  - `AskPayload.history`（`webapp/api.py`）+ `AskTurn`（`workflows/ask/ask.py`，只带问题原文+当时引用来源 id，**不带 AI 答案**）。
  - `retrieval.py` 新增 `candidate_by_id()`：按 source_id 重新纳入历史来源（越界/已删/派生类型跳过）。
  - `answer_question(..., history=...)`：历史问题作背景进 prompt（明确「不是知识来源」），历史来源并入候选（新鲜召回在前，token 预算截断）；轮数上限 6（`_MAX_HISTORY_TURNS`，前后端同口径）。
  - `_ask_html` 返回 `(html, source_ids)`；`/api/ask` 返回 `source_ids` 供前端存会话。SSR `/ask` 兼容路由保持单轮。
- **草稿保护（对齐外的小增强）**：等待回答期间输入的新问题不被响应后的重绘清空（`askDraft`）；「思考中…」只显示在真正等待的那个会话（`askBusyThreadId`）。
- **验证**：tsc + vite build 通过；ruff/mypy(strict) 全绿；pytest 404 全绿（新增 5 条 ask workflow 历史用例 + 1 条 webapi history 透传用例）。
- 手测清单见下；未覆盖项：真实模型调用下的追问质量（需要真机 vault + API key 人工验证）。
