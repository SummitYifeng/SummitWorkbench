# Handoff：Web 工作台体验对齐 + 修复方案（2026-09-02）

> 本文档由上一轮对话产出，用于交接到新对话继续执行。上一轮只做到**诊断**，除 fix①已实现（未编译/未提交）外，**其余均未改代码**。新对话可直接从「待执行」开始。

## 背景：这轮对齐怎么做的

用户要求：先用选择题从代码层面对齐"这个项目实际解决什么问题"，再用选择题对齐"用下来最真实的需求"，最后再谈优化。过程分两轮 `AskUserQuestion` + 代码核查，结论如下。

## 第一轮结论：代码解决的核心问题（用户确认）

- 核心痛点命中两项：**会议结论容易散失**（对应 `wb meeting import/backfill` + `wb review`）、**早上不知道先推哪条线**（对应 `wb brief`）。
- **未命中**："项目静默停摆没人发现"（`wb status` 健康度告警）、"想不起历史决定"（`wb ask`）——这两个功能都存在，但用户没把它们当核心痛点。
- 最高频使用：`wb review` 集中审批。
- 价值判断：「外置执行管理层」与「第二大脑」两层**同等重要**，说不出哪层更关键。
- 入口偏好：**本地 Web 面板 `wb web`**（不是命令行，不是被动看 Obsidian）。

结论：优化重心应该放在 **Web 面板**，尤其是 **review 审批体验**，而不是 CLI 或者被动简报阅读体验。

## 第二轮结论：用下来最真实的需求

1. **review 面板摩擦**（用户原话，信息量最大，值得完整保留）：
   > "一些操作端还是有点迷糊，比如我要去点待审批项，然后我不知道点击了那些意味着什么。是否会进入我的飞书任务。总之，整体上还不像一个一站式工作台的感觉。"
   同时勾选了：批量操作还不够顺手、AI 提取准确度不够。

2. **wb brief 有效性**：还没导入过近期会议，无法评价简报对排优先级的实际作用；但飞书日历+任务同步已经是感知到的优点。

3. **下一步最想要的新能力**：M4「快速捕捉分流」（不是 M3 带上下文启动）。

4. **wb ask / wb status 使用少的原因**（多选）：
   - **"Web 界面的第二大脑不稳定，问完了输出答案会突然又空白"**（关键信号——这是个可复现 bug，不是"没养成习惯"这种软性原因）
   - 用得少，还没养成习惯
   - 项目/会议量还不大，用不上

## 代码核查后的诊断（有具体文件行号，可直接定位）

### ① `wb ask` 答案消失 —— 确认是 bug，已定位根因

- [web/src/main.ts:722](../../web/src/main.ts) `window.setInterval(() => { void refreshState(); }, 60000)`：每 60 秒调用一次 `refreshState()`。
- `refreshState()` 只要当前在"今天"tab，就调用 `renderToday()`，而 `renderToday()` 会把 `view.innerHTML` **整体重建**，包括把问答区重新生成为空的 `<div id="answer"></div>`。
- 问答结果原来**只存在 DOM 里**，没有任何 JS 状态变量持久化它 —— 所以只要撞上这个定时刷新（或任何触发 `refreshState()` 的操作，比如批量审批、生成简报），刚显示的回答就会被无声清空。这精确对应用户报告的"问完了输出答案会突然又空白"。

**状态：已修复，未编译未提交。** 具体改动（`git diff web/src/main.ts`）：
- 新增模块级变量 `let lastAnswerHtml: string | null = null;`（紧跟 `state`/`review`/`tab`/`importing` 声明之后）。
- `renderToday()` 里 `askHtml` 的答案容器从固定空 `<div id="answer"></div>` 改成 `<div id="answer">` + `(lastAnswerHtml ?? '')` + `</div>`，重绘时把上次答案带回去。
- `bindAsk()` 里成功/失败两个分支都把最终 HTML 先赋给 `lastAnswerHtml` 再写入 DOM，保证状态和视图一致。

**新对话需要做的**：
1. 确认这个 diff 是否保留（上一轮改完就被用户叫停，代码还在工作区，未 `git add`）。
2. 跑一下前端构建验证没有 TS 报错：`cd web && npm install && npm run build`（产物会写入 `src/summit_workbench/webapp/static/`，`wb web` 才能生效）。
3. 手动验证：`wb web` 打开面板 → 问一个问题 → 等 60 秒以上或触发一次审批操作 → 确认答案不再消失。
4. 补充测试可选考虑：目前 `web/` 前端似乎没有单测覆盖（需要新对话确认 `web/` 目录下是否有测试框架；如果没有，口头验证即可，不必新增测试基建）。

### ② review 卡片"点击后会发生什么"不够清楚 —— 未修复

- 信息其实存在：[web/src/main.ts:471-513](../../web/src/main.ts) 的 `entryCard()` 里，每张卡片的 `meta` 行已经包含 `落点：飞书任务/项目主笔记/项目inbox/全局inbox`（`e.route ? '落点：' + (ROUTE_LABELS[e.route] ?? e.route) : '落点：未定'`）。
- 问题是这行信息是**小字灰色 meta 文本**，混在"目标/截止/依据/历史补导"里，不在"✓ 批准"按钮附近，用户点批准前不会自然看到它。
- 按钮本身（`main.ts:495`）只写死文案 `✓ 批准`，没有把落点信息带出来。
- **对应的服务端渲染（SSR 兼容路由）** 在 [src/summit_workbench/webapp/views.py:139-186](../../src/summit_workbench/webapp/views.py) 的 `_card()` 函数里有几乎一样的问题（`route` 也是塞在 `.meta` 里），但 SSR 路由目前只是"旧入口与既有测试继续可用"的兼容层（见 `app.py:491` 注释），**不是** `wb web` 默认打开的界面（默认打开的是 SPA，`web/` 编译产物）。优先级上先改 SPA 即可，SSR 是否同步改看新对话判断（改了要注意可能有对应的 snapshot 测试，`views.py` 顶部注释写着"纯函数，无 IO；便于快照测试"）。

**建议修复方向**（未实现，留给新对话拍板细节）：
把 `entryCard()` 里的批准按钮文案从固定的 `✓ 批准` 改成带落点的动态文案，比如 `✓ 批准 → 飞书任务` / `✓ 批准 → 项目主笔记`，路由未定时给出明确提示（例如 `✓ 批准（落点未定，需先在"修改"里选落点）`，具体要不要在路由未定时禁用批准按钮，需要看 `is_actionable()` 的语义——目前不确定"未定落点"和"依据/目标缺失导致不可批准"这两种状态是否互斥，新对话开工前建议先读一下 `domain/review.py` 里 `is_actionable()` 的定义再动手，避免破坏已有的 actionable 逻辑）。

### ③ 批量操作"还不够顺手" —— 未诊断，需要用户提供具体场景

- 已有能力（`ed2f51a` 刚合入）：分组全批/全拒（`main.ts:405-418` 的 `groupsHtml`，按钮 `data-action="group-decide"`）、一键拒绝过期项（`main.ts:562-569`，`data-action="reject-expired"`）。
- 用户反馈"还不够顺手"但说不清具体卡点，本人选择"先不动代码，把批量操作的具体卡点说清楚"。
- **新对话需要做的**：用几个选择题定位具体场景，例如：
  - 是分组粒度不对（比如想跨会议一次性批准全部"低风险"类型，而不是按会议分组）？
  - 是操作后没有明显反馈（批了之后卡片消失太快/没有确认提示）？
  - 是"修改"面板本身操作步骤太多（展开 → 改字段 → 保存 → 再批准，要点很多次）？
  - 是别的场景？
  定位清楚后再决定要不要动代码。

### ④ AI 提取准确度不够 —— 未诊断，非本次代码可查问题

- 这是 `meeting-processor` prompt（[prompts/](../../prompts/) 目录下版本化 prompt）效果问题，不是代码 bug，需要具体案例（哪条被提错、错在哪）才能优化。
- **新对话需要做的**：等用户下次真实导入会议、遇到具体提取错误时，再针对具体 case 调 prompt，不要泛泛猜测优化。

### ⑤ M4「快速捕捉分流」—— 前门已建好，后端路由是真缺口

- 前门已存在：[src/summit_workbench/webapp/app.py:356-409](../../src/summit_workbench/webapp/app.py) 的 `/api/capture`，能把随手记的文字 AI 分类（承诺/想法 + 截止 + `#项目` 标签）后写入 global inbox（`append_global_inbox`）。前端对应 [main.ts](../../web/src/main.ts) 里的 `capture-form`/`#capture-input`（`renderToday()` 中）。
- 但代码注释自己写明了缺口：`# 分类以稳定标记写回 inbox，供 M4 wb task 承接路由`——写入 inbox 之后**没有任何东西把它路由到项目/审批/飞书任务**，条目会安静地躺在 global inbox 里，直到有人手工处理。
- 这正好解释了用户选"缺 M4"："记下来"这一步已经很顺（回车即记，<5秒），缺的是"记完之后自动流转到该去的地方"。
- **新对话需要做的**：这是设计量最大的一块，用户明确要求"先不改代码，讨论怎么设计"。开工前建议：
  1. 读 [docs/product/PRD.md](../product/PRD.md) 里 M4 相关的验收标准（如果有），不要凭空设计。
  2. 读 `domain/capture.py`（`CaptureKind` 等）和 `repositories/writeback.py` 里 `append_global_inbox` 的实现，搞清楚当前 inbox 条目的数据结构（是否已经有稳定的 marker 可供后续路由消费）。
  3. 和用户对齐：M4 的路由目标应该是"自动路由"还是"生成候选让用户在 review 面板里再批准一次"（后者更符合项目一贯的"人工审批边界"原则——参考 README 硬边界"未经用户确认的会议提取项不得写入项目状态或创建飞书任务"，M4 大概率也要遵守同样的边界，不能做成静默自动执行）。

## 优先级（用户在第二轮选择题里的原话，全选，按顺序做）

1. 修好 ask 答案消失 bug（推荐，已部分完成，见①）
2. 把 review 卡片的后果提示改明显（见②，未开始）
3. 先不动代码，把批量操作的具体卡点问清楚（见③，未开始）
4. 先不改代码，讨论 M4 路由该怎么设计（见⑤，未开始）

## 当前代码库状态

- `git status --short` 只有一处改动：`M web/src/main.ts`（即上面①的 diff，未 `git add`，未编译，未提交）。
- 新对话开工前先跑 `git diff web/src/main.ts` 确认这个改动还在，且用户认可要保留（上一轮是被用户主动叫停，不是改错了）。
- 未跑过前端构建，`src/summit_workbench/webapp/static/` 里的产物还是旧版本，**这次改动实际生效前必须跑一次 `npm run build`**。

---

## 执行记录（2026-09-02 新一轮，已接续完成）

> 本节由接续对话追加。开工时工作区实际状态比上文描述的要多：树里已含 ② 的 SPA+SSR 改动且已构建过一次（`web/src/main.ts`、`views.py`、`static/` 均有未提交改动）。本节按「实际树状态 + 本轮新增」记录，供下一轮接手。

### 本轮做了什么

**① ask 答案消失 —— 确认保留 + 加固 + 已构建**
- 上轮 diff（`lastAnswerHtml` 模块变量 + 渲染时带回复制 + bindAsk 写入前先存状态）确认还在，保留。
- 加固：`bindAsk()` 现在用 `show(html)` 统一写 `lastAnswerHtml` 并**按 id 重新获取当前 `#answer` 节点**写入。原因：`renderToday()` 每 60 秒整体重建 DOM，若请求期间撞上重绘，旧实现会把响应写进已脱离文档的节点，可见区会一直停留在「思考中…」/旧答案——与用户报的「问完突然空白」同根因。现在加载态也持久化进 `lastAnswerHtml`，撞上重绘后重绘内容仍是「思考中…」，响应到达后写当前节点。
- `cd web && npm run build` 通过（tsc --noEmit 无错）。产物已更新：`static/index.html` → `assets/index-28sSD1ge.js` + `index-Du5LajBp.css`（旧 `index-vjB0y8Bj.js`/`index-COJbN5bj.css` 被清出）。
- Python 单测（webapi/webapp/review_apply/review_page/review_edit/review_schema/review_candidates）67 项全绿（`.venv/bin/python -m pytest`；注意 `uv run` 在本机因 `~/.cache/uv` 权限被拒不可用）。

**② 批准按钮后果可见 —— 树里已有实现，本轮复核 + 补文案**
- 复核结论：批准按钮改为动态文案（`✓ 批准 → 飞书任务` 等）且**落点未定即禁用**（带 title 提示）是**正确**的，与后端一致：`workflows/review_apply.py::_plan()` 对 approved 条目 route=None 一律判 `缺少 route` 不可执行（会在「应用」时报错弹回）。`domain/review.py::is_actionable()` 只要求证据+目标项目，route=None 且项目已解析的条目 actionable 但 apply 必失败——这正是旧 UI「批了没下文」的坑，禁用堵住了它。SSR `views.py::_card()` 已同步（兼容层，无快照测试覆盖该处，安全）。
- 本轮补的后果文案（都指向同一个用户困惑「批准了意味着什么、会不会进飞书任务」）：
  1. review 工具栏提示改为「`✓ 批准` 只做标记，点『应用（写回）』才会真正写入项目/创建飞书任务」。
  2. 单条/批量成功 toast 对 approved 追加「—— 仅标记，点『应用（写回）』才真正写回/建任务」。
  3. review 页新增 `.apply-nudge` 提示行：存在「已批准、未写回」条目（decision=approved 且无 apply_error）时显示「N 条已批准、尚未写回——点『应用（写回）』…」，应用后消失。

**③ 批量/操作摩擦 —— 用户选择题定位后的小改**
- 用户多选命中：**「修改」面板步骤太多** + **操作后反馈不够**（未选「全批批到不该批的条目」等，故未动批量语义/粒度）。
- 对应改动：
  1. 编辑表单新增**「保存并批准」**主按钮（仅 pending 条目显示；`仅保存` 保留为 ghost）：一次提交 编辑→标记批准 两步合一。落点仍为未定时拒绝批准并 toast 说明（与 ② 的禁用一致）；批准仍只标记，toast 带「点应用才真正写回」。
  2. 反馈增强 = 上段 1/2/3（toast 语义化 + apply-nudge）。
- 实现位置：`web/src/main.ts`（renderReview / entryCard / submit 监听 / decide / batchDecide）+ `web/src/style.css`（`.apply-nudge`）。

**④ AI 提取准确度 —— 未动**（按上轮结论：等真实提取错误案例再调 prompt，不泛泛优化）。

**⑤ M4 快速捕捉路由 —— 用户已对齐方向（本轮未写代码，按约定只对齐+记录设计）**
- 用户确认：**进审批面板当候选**（非直接建飞书任务、非全进 inbox）；范围 = **AI 判为「承诺」的 + 带 `#项目` 的「想法」**都生成候选；纯想法（无项目无截止）留在 inbox。
- 下一轮实现的设计草案（关键事实已核查）：
  - `/api/capture` 现有流程（`webapp/app.py:356`）已把条目写入全局 inbox 并带 `wb-capture-kind/due/project` 稳定标记；候选生成应在写入 inbox 后、命中范围时追加。
  - **复用现有审批机器**：捕捉候选可写入同一 `meetings.md` approval-page，用合成会议头如 `## <今天> 快速捕捉`——`repositories/review_page.py` 解析只要求首 token 作日期、标题自由，编辑/裁决/应用/审计全链路直接可用；`pending_review`（backlog.count）自动计入徽标/今日卡/简报。
  - **关键设计点（必须处理）**：`domain/review.py::is_actionable()` 要求有效 evidence，而快速捕捉没有逐字稿证据 → 候选会卡在「不可批准」。方向：为用户手录内容增加自证语义（如 `EvidenceRef(speaker="user", quote=原文)` 或 `ApprovalCandidate.user_entered` 放宽证据要求），需在下一轮定夺，别绕过证据门槛（meeting 候选仍需证据）。
  - route 沿用 `route_candidate()`（`domain/review.py:109`）：有截止/涉及他人 → feishu-task；带项目 → 项目 inbox；项目 inbox 落点要求 work_root 项目文件夹已存在（apply 会校验并报错，同会议流程一致）。
  - 候选 id 幂等：建议 `web-capture-<date>-<正文hash>`（当前 `/api/capture` 用时间戳 id 仅保证 inbox marker 唯一；重复捕捉同文本不应重复生成候选）。
  - inbox 生命周期未决（下轮与用户确认）：捕捉行进了审批并写回成功后，inbox 原行是归档/标记处理，还是保留当流水账；以及候选在审批页是独立分区标题「快速捕捉」还是混在会议组里。
  - 待核查：捕捉候选 kind 用什么（承诺 → task-create；带项目想法 → action-item？），SSR 兼容路由是否需要同步展示。

### 当前代码库状态（本节结束时）

- `git status --short`（未 add、未提交）：`web/src/main.ts` M、`web/src/style.css` M、`src/summit_workbench/webapp/views.py` M（上轮 ② SSR）、`static/index.html` M；`static/assets/` 旧 `index-vjB0y8Bj.js`/`index-COJbN5bj.css` D、新 `index-28sSD1ge.js`/`index-Du5LajBp.css` ??；`docs/plans/HANDOFF_web_ux_fixes.md` ??。
- 静态产物为最新构建（含 ①②③ 全部改动）。用户已确认提交本批改动（含本节与静态产物增删）；M4 实现按约定**下一轮开工**，两个小决策（inbox 原行处理、候选分区标题）开工时先按推荐值实现再给用户看。
- 手测清单（下轮或用户自测，需 `wb web` 面板）：
  1. 今日页问一句 → 等 ≥60 秒（或点顶部刷新）→ 答案仍在；
  2. 审批页：落点未定卡片批准按钮禁用并显示「先在修改里选落点」；修改选好落点后点「保存并批准」一键完成；批准后出现「N 条已批准、尚未写回」提示行；点「应用（写回）」后消失；
  3. 修改表单里「仅保存」仍是旧行为。
