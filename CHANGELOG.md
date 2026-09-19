## [0.4.10] - 2026-09-19

> 修一个**用户可见的同步阻断**：打包 App（固定 dulwich）× **HTTPS 远端永远同步失败**，
> 而界面只说「未分类的同步失败」。无破坏性变更、无新依赖。

### 修复

- **HTTPS fetch 的传输参数必须交给接受它们的入口**：dulwich `1.2.15` 把 `pool_manager`
  从 `porcelain.fetch` 的签名里移除了（fetch/push/clone 三者只有后两者还有 `**kwargs`），
  而 `repositories/dulwich_git.py` 的 fetch 仍按 0.22.x 的 API 把 `transport_kwargs()`
  交给它 ⇒ `TypeError: fetch() got an unexpected keyword argument 'pool_manager'`，被
  `_classify_remote()` 兜底成 `unclassified`。
  改为复刻 `porcelain.fetch` 的做法：`get_transport_and_path(...)`（**接受** `pool_manager`）
  建 client → `client.fetch()` → `_import_remote_refs()` 落 `refs/remotes/<remote>/*`。
- **影响面**：自 dulwich `1.2.15` 迁移（build `2026091917`）起，**任何 HTTPS 远端在打包 App
  里都无法同步**。本地路径/SSH 远端不受影响（`transport_kwargs()` 对非 HTTPS 返回 `{}`），
  CLI 默认走 system git 后端也不受影响——这正是它藏了这么久的原因（详见下方「为什么没被门禁挡住」）。
- **守卫**：`tests/contract/test_dulwich_api_contract.py`（行为回归 + 参数面收敛 + 依赖前提
  三条），已做变异验证——把 fetch 还原成旧实现，行为回归那条立刻变红。

### 为什么没被门禁挡住（值得记住）

1. 单测要么把 `transport_kwargs` monkeypatch 成 `{}`（本地路径远端走这个分支），要么只断言
   它的**内容**，从没拿真实签名调过一次 HTTPS fetch；
2. CLI 默认 system git 后端，只有打包 App 固定 dulwich；
3. 结果就是「测试全绿 + CLI 正常 + 打包 App 里 HTTPS 同步永远坏」。

### 观察项

`unclassified` 是 `_classify_remote()` 对**未识别异常类型**的兜底码。这次真因是编程错误
（调用点与依赖 API 漂移），不是网络/凭据。**以后再见 `unclassified`，先怀疑后端调用与依赖
API 漂移，而不是先查网络。**

## [0.4.9] - 2026-09-19

> 第二大脑的**检索与决策层做深**，工作知识库**首批入库落地**，并修掉几个一直没被门禁覆盖的真缺陷。
> **不破**既有硬边界：无向量库 / 无 RAG / 不加第三方依赖；不引云服务端、不引守护进程。
> 本轮为**内部 INTERNAL-DEV 迭代**（旧编号 build 36→42；2026-09-19 起 build 号改为 `yyyyMMddNN`
> 形态，本版最终交付 **build `2026091923`**），**未打 tag、未发布**到 Updates 仓库；
> 最新已发布 tag 仍是 `v0.4.8`。

### 新增

- **审批第 7 个落点「知识沉淀」**（`webapp/routers/review.py` / `webapp/api.py`）：把结论写回
  **指定页面的指定区块**。目标由候选显式带 `sink_target`，只接受 vault 相对路径（拒穿越），
  目标页缺失即拒绝批准；写入带出处与幂等标记。15 例新测试 + 变异验证。
- **Workbench「决策」页**（`GET /api/decisions` + 新 tab）：按管线 / 主题 / 状态筛选、看演进关系
  （`supersedes` / `superseded_by`），状态分组、关系行、空态、输入防抖。8 例后端单测 +
  1 个前端纯渲染测试。
- **`decision` 第 7 区块 `## 关联` 进 app 固定区块表**（契约级：`domain/vault.py` + 模板 +
  契约测试 + 路由契约快照）。此前六区块里没有放双链的地方，样例只能塞进 `## 影响` 末尾，语义不符。
- **检索 · 块级角色加权（R1）**：结论型 ×2.8 / 支持型 ×0.8 / 引言 ×0.45 / 导航 ×0.4；
  类型权威调整（`index` 1.0→0.45、`project-main` 与 `decision` →0.95）。
- **检索 · BM25 召回补足**（`_supplement_with_bm25`）：此前 BM25 只在 FTS 完全无结果时才用，
  Q3 在 FTS 层只命中 10 个块；两路按各自最高分归一后取并集，Q3 候选 **10 → 321**。
- **检索 · 问句形态兜底（R4）**（`_FORM_RULES`）：只在零关键词命中时才生效，不与词表抢路。
- **检索 · 「要原文」时放开证据层降权（R6）**（`EVIDENCE_REQUEST_RE`）：问「要原文 / 原话」时
  不再对 `source` 整篇 ×0.8 降权，其余时候照旧。
- **检索 · 主题通道**：问题点名某主题时抬起该主题簇页的结论型区块
  （标题 / 领域 / 别名 / tag 的 2-gram + 拉丁词命中，`topic_step=0.4`、封顶 2.4）。
- **验收与工具**：`scripts/kb_index_decisions.py`（决策台账聚合，含 YAML date 陷阱回归）、
  `scripts/kb_verify_links.py`（双链与块级锚点自检；注入死链 + 坏锚点 + 坏 `路径#区块` 三类变异全被捕获）、
  `scripts/kb_acceptance_installed.py`（对**装到 `/Applications` 的那一份**做端到端验收，
  新增 `--only <子串>` 单题重跑省 token，失败时逐条列出「进入上下文的来源」）。
- **Air 备用机接入作业单**（`docs/implementation/AIR-MACHINE-HANDOFF.md`）：这一对机器的真实值 +
  装完的合格清单。接入路径已在 Studio 上用真远端真凭据跑过。
- **App 内指南补齐**：知识沉淀落点、决策页、提问技巧（主题优先 / 要原文给原文 / 块级引用）。

### 修复

- **全新 workspace「首次发布到远端」必然失败（BUG-1）**：`_checked_publish_target()` 构造真 vault 的
  `GitRepo` 时没传 `username` / 凭据回调，push 时抛 `GitCredentialsUnavailable`，又被兜底的
  `except Exception` 吞成 `remote_publish_rolled_back`——**真因完全不可见**；而预检那次是真推，
  远端已被留下 `main` 半成品。修好凭据透传并把真因暴露为可诊断错误。2 例回归 + 变异验证。
- **项目档案区块不渲染 Markdown**（使用者报的界面问题）：项目详情把每行 `esc()` 后直接塞进 `<li>`，
  `**粗体**`、`[[目标|显示名]]`、`| 主线 | 状态 |` 表格全部以源码示人。根因是它**绕过**了仓库里
  已有的共享渲染器（`md.ts` / `views.md_to_html`）。改为把共享渲染器补成真渲染器（段落回流 /
  有序列表 / 任务清单 / 嵌套 / 表格 / 引用 / 代码块 / 斜体 / wikilink 只显示标签）再接上去；
  顺带修好「指南」页 37 处编号列表。测试抓出两个真 bug：① 表格会把紧跟其后的 `[[目标|显示名]]`
  当表格行吞掉（wikilink 里也有 `|`）；② 中文软换行在行内标记边界缝出空格。
- **回答撞输出上限时不再把 `LLMSchemaError` 抛给使用者**：改为带「收窄材料」提示重试一次，
  仍截断则回报可操作提示（问得更具体 / 提高 `max_output_tokens`）。
- **`GET /api/sources/read` 空值与「只有 `#区块`」返回 500 而非 400**：
  `Path("").with_suffix(".md")` 抛 `ValueError: PosixPath('.') has an empty name`，而这句排在
  400 守卫**之前**——前端传一个畸形参数就只能看到兜底的「服务内部错误」。两者现在都是 400。
- **`scripts/kb_verify_quotes.py --materials-root` 在真库上 6/6 误报**：判据用
  `body.split("\n---\n\n## 关联")` 剥页尾区块，而真库里 `## 关联` 前面**没有** `---`，于是
  `conventions` §4.3 规定的页尾区块被当成「原件之后另加的内容」。改为「原件逐字、连续出现，
  且其后只放行约定的页尾 `## 关联` 区块」；真库由 6 条误报 → 0 条，覆盖 8 篇原件比对。
- **`scripts/kb_index_people.py` 会抹掉新规范 frontmatter**：它自带一份最小 frontmatter，
  写入时把页面已有的 `id` / `area` / `workstream` / `summary` 整段覆盖；改为保留既有 frontmatter、
  只替换正文。

### 变更

- **块边界由 `##` 扩到 `#` 与 `##`（R2）**：原始材料常用 `#` 分大章（HII IP 原件有 20 个 H1），
  只切 `##` 会让这些章节的正文并进相邻块、无法定点引用；Obsidian 的 `[[文件#标题]]` 本来也不区分
  标题级别。决定性实测：1038 行原件的 **17 个一级章节 + 2 个附录全部成为可定点锚点**（此前 0 个）。
  同时把语义收紧为「**文首 H1 是笔记标题、不算块边界**」。样例库块数 131 → 151；
  真实库全量重建后 `conventions#工作知识库规范`、`projects/hii-affairs#HII 事宜` 等 H1 锚点生效。
- **双链扩展三处修正**：① 同一邻居被多个种子各加成一次（实测把正文相关度 0.29 的块顶到 41.05）
  → 改为只取最强种子、只应用一次；② 旧实现把邻居分整体替换成 `promoted`，不同邻居被抹成相同分数、
  顺序退化为任意（Q1 排名 2–10 全是 25.03）→ 改为**乘性加成**；③ 扩展重复应用 `project` /
  `workstream` 过滤（R3），按项目过滤时不再混入 `project: global` 的页。
- **两次数据驱动的回退（记录在案）**：BM25 `b=0.35` 与 CJK 2-gram 补词都**实测有害**
  （块级命中 44% → 31%），已撤回。教训：检索权重 / 词表这类改动必须先用真实问题量一遍，不能凭直觉。
- **检索效果**：改造前基线块级命中 **4/16 = 25%** → 本轮 **6–7/16 = 38–44%**。

### 测试

- 真实库验收 `scripts/kb_acceptance.py`：**9 题**（4 题真调模型 + 5 题零 token 机制回归）。
  关键证据支持「**等价入口 any-of**」——两个入口都没进上下文时仍然红。
- 已装 App 验收 `scripts/kb_acceptance_installed.py`：4 题模型口径，build 41 与 build 42 各跑一轮全过。
- `tests/unit/test_kb_scripts.py` 增补**真页面形状**用例（原件 + 页尾 `## 关联`）：此前的 fixture
  里没有该区块，导致「剥页尾区块」那条分支从未被真实形状覆盖——**测的是 fixture，不是库**。
- 关键信号继续做**代码级变异验证**（删掉守卫 / 降权 / 去重后测试必须立刻红）。本轮新增：
  逐字判据在**真库副本**上的四类变异（改字母 / 同长度换字 / 删一行 / 页尾前插区块）全部红，
  反向对照（只删页尾区块、原件未动）仍绿；`/api/sources/read` 移除守卫即红。
- 门禁：`pytest --cov` **1133 passed / 1 skipped**，覆盖率 **83.73%**；`ruff check` +
  `ruff format --check`；`mypy` 359 文件；`scripts/secret_scan.py`；前端 **16 组**（76 源文件）。

### 检索契约（SWB ↔ SummitKnowledge，本批次新增）

- **可执行检索契约**（`domain/retrieval_contract.py`）：把「能被 SummitKnowledge 稳定索引/引用」
  变成校验——`validate_retrieval_readiness`（固定区块 + 围栏代码外 H1/H2 不重复 + superseded
  决策必须带替代链接）、`is_fact_retrieval_eligible`（draft/pending-review/ignored 不进事实问答；
  archived 是合法历史知识、不等于被推翻）。type/status 词表与固定区块分类全部复用 vault schema。
- **自动产物确定性规范化**（`workflows/knowledge_normalization.py`）：清重复文首 H1、保留原 H2/H3、
  补缺失的 `## 关联项目`；重复标题 / 未闭合围栏 / 空标题 → 拒绝落盘、不写半成品。
  `append_work_log` 与 `save_thread_artifact` 走同一规范化器，写盘后同时执行 schema 与检索就绪校验。
- **推进日志恒为 `generated`**：此前「模型不可用只存原文」落 `status: draft`，而 `draft` 会被检索
  契约整体排除出事实问答——恰恰把最需要的原始证据挡在门外。现在摘要有无只由 `summary` 字段表达，
  状态统一为低权威 `generated`（可参与回答，不能单独支撑高置信事实）。`thread-doc` 保持
  「无 summary → draft / 有 summary → generated」。
- **审批链路加固**：会议笔记生成即做检索就绪校验；写回拒绝重复区块标题与无法解析的 anchor；
  逐字稿原件在处理前后逐字节不变。
- **`wb ask` 候选条数统一口径**（`router.routed_limit`）：CLI 过去写死 8、验收脚本与 App 面板
  默认 6、路由计划另为 12–16；现在由路由计划唯一决定，显式 `--limit` 仍可覆盖。
- **`wb vault check` 同时跑检索就绪契约**：`check_vault` 在 schema 之后追加
  `validate_retrieval_readiness`（`wb doctor` 复用），存量库文件里的重复 H2 /
  superseded 缺替代链接不再等到 SK 侧引用退化才暴露。
- **知识沉淀出处改为可解析的 `路径#区块`**：此前写回主题簇页的结论只带逐字稿时间戳
  （`出处：木子 00:03`），从检索侧看是**无法解析**的悬空指针；现在带
  `<会议笔记 source_id>#<区块> · <证据锚点>`（区块按候选类型映射到会议笔记固定区块），
  会议笔记文件缺失时退回证据锚点，不编造指向不存在文件的引用。
- **自动产物补 `area: work` 与 `title`**（`daily/`、`logs/`、`artifacts/` 三个写入端）：
  这两条是同一类缺陷——**写入端漏写字段，导致页面"索引了但看不见/不可读"**。
  - 缺 `area`：SK 侧综合类问题按 `area` 过滤「笔记总览」，于是当日简报与推进日志从总览
    清单里静默消失（向量/关键词检索仍召回得到，只是所有「总览」类问题看不见）。
    2026-09-15 真实提问实测：总览写「60 篇」，实际索引 62 篇。
  - 缺 `title`：SK 回退成文件名，总览里只剩《2026-09-14》《2026-09-14-001》，语义全丢——
    同一次提问自己把这条列为「命名纪律是弱项」。标题取各自正文 H1，未新造文字。
  - 三个写入端均补字段 + 三条测试断言 + 变异验证（去掉字段即变红）；存量两篇由真实库
    独立提交回填，work 索引重跑后 `note_metadata` 为 `area=work 62/62`、
    `title=晨间简报 2026-09-14 / 推进日志 2026-09-14（hr 等）`，总览清单恢复 62 篇。
  - 顺带对齐规范：`_vault/conventions.md` §2.1「机器写入页豁免」名单补入 `logs/`、`artifacts/`
    （它们与 `daily/` 同为程序生成，豁免理由相同），并写明豁免只免「必填」、不免
    `area`/`title` 这类影响检索可见性的字段。
- **文档**：新增 [`docs/contracts/WORK-KB-RETRIEVAL-CONTRACT.md`](docs/contracts/WORK-KB-RETRIEVAL-CONTRACT.md)；
  PRD §3.1.2/§3.1.3/§3.1.4/§3.1.6/§3.2.6 与 README、PROJECTDESC 的过时「不切片 / ripgrep」
  描述改为当前真实实现，并登记 T2 已满足、高级语义检索归属 SummitKnowledge。

### 界面收敛（2026-09-16）

- **工作台下线「第二大脑」与「指南」两个页签**，页签由六个收敛为四个（今日 / 审批 / 项目 / 设置）：
  - 前端：删 `features/ask/`（6 文件）与 `features/guide/`（2 文件）、`guide.md` 及其构建同步脚本，
    见 `shell.ts` / `tabs.ts` 的页签表与 `legacy-main.ts` 的组合根；
  - 后端：删 `webapp/routers/ask.py` 与 `webapp/ask_view.py`，SSR 看板去掉「问第二大脑」表单
    （状态 tile「已入第二大脑」改为「已入知识库」），路由契约同步重生成（移除 `/api/ask`、`/ask`）；
  - **保留**：`wb ask` CLI（计划里就是「轻量兜底」）、`answer_question` 编排、`/api/sources/read`
    与只读来源面板（**审批页的证据核查仍在用**，从已删的 ask feature 里独立成 `features/source-reader.ts`）；
  - 体积：前端模块 69→62、JS 162.3→122.7 kB、CSS 37.3→31.6 kB（另删 139 行问答/指南专属样式，
    全局响应式规则逐条保留）。
  - 理由：一个入口一个职责——看板归 SWB、语义问答归 SK；界面越窄，日常使用频率越高。

### 交付增量（2026-09-15 ～ 09-19）

补记 09-14 之后、直到交付 build `2026091923` 的全部批次（此前 CHANGELOG 未覆盖）。

**检索就绪与契约（09-15）**

- **`wb vault check` 增加检索就绪校验**（`validate_retrieval_readiness`）：重复 H2、`superseded`
  缺替代链接不再等到 SK 侧引用退化才暴露。
- **`work-log` 的 `status` 与两套形态解耦**（「日常手记」五区块 / 「推进日志」`## 原文`）：
  手写落 `active`、纯机器产物落 `generated`，机器生成的日志保持**事实可检索**。
- **知识正文写入前确定性规范化**；**知识沉淀出处改为可解析的 `路径#区块`**（不再只留时间戳）。
- 新增并固化 [`docs/contracts/WORK-KB-RETRIEVAL-CONTRACT.md`](docs/contracts/WORK-KB-RETRIEVAL-CONTRACT.md)
  （写入路径与校验点、状态与权威顺序）；配套契约测试把该文档与实现锁在同版本。

**今日页与 Markdown 展示（09-16）**

- 「今日」页由长列表收敛为**五个内容模块**（含空状态引导）；用户正文在所有展示入口统一走
  安全 Markdown 规范化，脏 Markdown 用例入测试。
- **下线「第二大脑」与「指南」两个页签**：页签由六个收敛为四个（今日 / 审批 / 项目 / 设置）；
  语义问答归 SummitKnowledge（`/api/ask`、SSR 问答表单、`features/ask`、`features/guide` 一并移除，
  `/api/sources/read` 与只读来源面板保留）。

**可靠性与同步（09-16 ～ 09-18）**

- 会议导入**可续跑**（中断后重跑只处理未完成项）；外部动作（飞书任务）中断后可安全恢复、不重复创建。
- 有界请求与有界原生服务关停；业务时间统一用**北京时间**；飞书凭据预检与打包前置校验加固。
- **SSH（SCP 形状）remote 的 push 修复**：`git@host:path` 不含 `://`，此前被误判为"不存在的本地
  路径"，联网前就报 `remote-unavailable`；新增跨后端守卫。
- **原生壳恢复 Dock 图标**（`LSUIElement=false` + `.regular`，`WB_DOCK_ICON=0` 可退回菜单栏模式）。

**模型侧（09-18）**

- **逐能力显式配置**：`max_output_tokens` 是「思考 + 答案」共用预算，抽取/摘要/分类一律
  `thinking="disabled"`；**长逐字稿结构化失败的真因是输出预算被推理吃光**（不是上下文长度），
  并修掉把长文档摘要压到 10 秒的硬编码超时；新增 `digest` 能力。

**内容契约与界面偏好（09-18）**

- **会议笔记不再生成 `## AI 建议`**（九区块减为八区块）；决策页新增「只记业务结论」硬规则与机器
  守卫 `scripts/kb_check_decision_hygiene.py`。
- 设置页主区只留 工作区 / AI 模型 / 飞书 三张卡（每张一行），自动化与模型参数移入「高级与维护」。

**写入入口与收件箱提升（09-19，契约 §4.10 / §10）**

- **`POST /api/journal/log`「日常手记」**：`did` / `remaining` / `reflection` / `blockers` 至少填一段，
  落 `logs/<日期>-<seq>.md`、`status: active`，单块 > 1500 字符拒绝。
- **`POST /api/journal/thought`「工作思考」**：三段必填，落 `thinking/<YYYYMMDD>-<slug>.md`，
  落盘前过 schema + 检索就绪 + 叠加必填。
- **收件箱提升通路**：`GET /api/inbox` 纯读、本地启发式、**绝不调模型**；三种目标
  `project` / `feishu-task` / `thought` 各复用既有落盘实现，提升后条目**移出收件箱、不留占位行**、
  与目标写在**同一个提交**；只有显式按钮 `POST /api/inbox/suggest` 才调一次模型。
- 【今日】页新增「写工作日志」「写工作思考」两个入口，以及「收件箱（N 条）」块与「提升为…」弹层。

**批次 A 语料边界与自检（09-19）**

- 简报与周复盘改落**本机程序目录**（不再写知识库），`daily/`、`reviews/` 从库内移除；
  检索类型与来源白名单对齐契约（补 8 个主线项目目录与 `thinking`，去 6 个死目录）。
- 新增 `scripts/kb_check_contract.py`（`conventions.md` 声明的目录/类型 vs 库内实际，FAIL/WARN 分层）；
  修 `kb_verify_links.py` 的裸锚点覆盖回归（来源上下文改为扫全篇标记行）。

**验证纪律与门禁（09-19）**

- **`WB_NO_AUTO_PUSH=1`**：写入照常 commit、**不自动 push**，响应里显式标注 `auto_push.skipped`
  （绝不记成同步成功）——起因是一次验证动作被运行中的 App 自动推送进了 `origin/main`；
  同时新增 AST 结构守卫，把"唯一自动推送出口"钉成白名单。
- **跨端回归闸门 `scripts/kb_three_end_gate.py` 扩到 8 步**：工作树干净、`_signals/` 未回跟踪、
  逐字稿与 `inbox.md` 不进语料、精排生效、原件与 `daily`/`weekly-review` 不进语料、来源白名单、
  `journal/log` 与 `inbox/promote` 写路径（后两步不调模型、不花钱）。
- **dulwich 后端的 `log_grep` 改为正则匹配整条消息**：打包 App（固定 dulwich）里「撤销历史」面板
  此前恒为空。
- `--no-push-cleanup` 取代易误读的 `--no-push`；pre-push 钩子的 Swift 步骤改为 `env -u SDKROOT`
  （macOS git 包装器注入的 `SDKROOT` 会让 `xcrun swiftc` 报"SDK 与编译器不匹配"）。
- **两处用户可见修复**：写回固定区块不再与自己的空行叠成双空行；手工写进 `inbox.md` 的条目也能按
  正文 `#项目` 走默认目标（此前一律默认判成「一篇工作思考」）。

**代码简化重构（09-19，尚未打包）**

- 后端纯拆移/收敛：`routers/settings_connections.py`、`routers/sync_conflicts.py`、
  `webapp/feishu_authorization.py`、`repositories/thought_notes.py`、
  `domain/knowledge_normalization.py`；前端下沉 `features/diagnostics.ts`、
  `features/projects/actions.ts`、`features/review/actions.ts`。
- `web/src/legacy-main.ts` 964 → **922 行**（只剩类型契约、跨域状态、`render()`、全局派发与
  `mountLegacyWorkbench`）。拆分蓝图已归档，`docs/implementation/LEGACY-*-SPLIT-PLAN.md` 只留指路 stub。

### 验证与产物

- `0.4.9` build **42**（`git_commit=70f6753`、前端 `v2026.09.14-70f6753-4d072dbb`）已构建并安装到
  `/Applications`；DMG SHA-256 `de7cb309e07ddd4307ae85ca72b1aad10f9f46e17a6909ecd54686a8ab02d350`。
- build → 提交对照：36/37 `f202d3e` · 38 `6ba2f60` · 39 `1ba837d` · 40 `425dff3` ·
  41 `288f13d` · 42 `70f6753`。
- 证据在 `docs/acceptance/evidence/`：`kb-acceptance-2026-09-14.txt`、
  `kb-acceptance-installed-2026-09-14-build41.txt`、
  `kb-round-2026-09-14-verbatim-and-sources-read.txt`。
- **DMG 文件名里没有 build 号**——认包请核 SHA-256，或看设置页的 build 号。
- **2026-09-19 起 build 号改为 `yyyyMMddNN`**；本版最终交付 **build `2026091925`**
  （`git_commit=e62d3a3`、前端 `v2026.09.19-d1a8ace7`）已构建并通过 13 项发布检查
  （`test-manifest.json` 状态 `passed`）；App SHA-256
  `ca58c8466a7e195fe23a38d485fa1de0791771fa56610725815789619275557b`、
  DMG SHA-256 `6c31855d4f42c82fc247755c2d955a0354dd5ea58d6066015ffd0d1f42506243`。
  同提交上远端 CI 4/4 job 全绿（run `35444857578`）。
- 本版内交付序列：`2d1cf3a` → `2026091917` · `a49bb42` → `2026091918` · `f710aca` → `2026091919` ·
  `7b7df74` → `2026091920` · `375ce98` → `2026091921` · `e1700e2` → `2026091922` ·
  `0c9ff4f` → `2026091923`（装机过）· `c9b3fc5` → `2026091924`（只进 dist，未装机、未入档）·
  **`e62d3a3` → `2026091925`（本次交付）**。
- **CI 的 `macOS arm64 contract` 之前每次必红**：账单停摆恢复后第一次真跑暴露——该步默认要求内置
  飞书凭据，而凭据只在 `release` environment（部署策略仅允许 `v*` 标签），`main` 上的手动 CI 取不到。
  修法：该步显式 opt-in 无凭据开发构建（两个开关成对）+ 守卫禁止该 job 上传产物；
  详见 `docs/RELEASING.md` 与 `tests/contract/test_ci_contract.py`。
- 本版末次全量门禁（`e62d3a3`）：`pytest -q` → **1396 passed / 1 skipped**、`--cov` → **84.54%**。
- **`v0.4.9` 已发布到更新通道**（2026-09-19）：tag `v0.4.9`（提交 `5204abf`）触发 `release.yml`
  （run `35446664234`，`workflow-lint` + `release` 两 job 全绿）→ `yifeng93/SummitWorkbench-Updates`
  的 **Latest** 发布：**build `23`**（= CI run number）、DMG SHA-256
  `f5c3b65f67b46641de2468cfcb5948558c1a7ce43bc31e3c31c53705d86676a4`、
  `update-feed.json` **带签名**（含 `public_key`）、`test-manifest.json` 13 项 `passed`。
  **发布前置（这次踩到了）**：`release` environment 的 `UPDATE_DOWNLOAD_URL` 必须等于按 tag 算出的
  期望值，它原本钉在 v0.4.8，不同步会在 `Prepare protected update configuration` 步直接 FAIL。
  **两套 build 编号**：tag 发布用 CI run number（本版 `23`；历史 19/24/29/…/50 同口径），
  本机 INTERNAL-DEV 包用 `yyyyMMddNN`（本版 `2026091925`），别混。

### 已知不足（未解决，透明记录）

- **Q3 的 `it/clusters/enrollment#关键结论` 仍未召回**：加「主题通道」后它由「同篇不同块」变成
  未召回（净效果 6→7）。
- **同篇多结论块互相竞争**：分析笔记有 19 个「结论N」块，`max_chunks_per_note=3` 下哪 3 个进上下文
  仍偏字面相关度。
- **度量是 16 项二值指标**，个别项会随权重微调翻转 → 不适合当单一调参目标。要再动权重，应先建更
  可信的度量（按「答案里是否出现关键结论、出处是否可解析」分档）。
- **Air 侧 GUI 点击与系统权限弹窗仍未验证**（必须在另一台机器上做）；Studio 侧的接入路径已验过。
- `kb_verify_quotes.py` 的页尾判据只放行「以 `## 关联` 开头的尾巴」，**在 `## 关联` 之后再追加
  内容不会被它抓到**——与旧判据在「`---` + `## 关联`」页面上的行为一致，属有意不改的边界。

## [0.4.8] - 2026-09-13

> 工作知识库重建 + 第二大脑纯文本检索做深。**不破**「无向量库 / 无 RAG / 不加第三方依赖」硬边界；
> 不引云服务端、不引守护进程。

### 新增

- **工作知识库规范 v2**（库内 `conventions.md`）：修好指向 MyKnowledge 上游规范的相对路径；
  明确「工作层叠加」字段（`workstream` / `source` / `people` / `org` / `confidential`）、
  目录归属判定（项目主页留在顶层 `projects/`）、决策集中 `decisions/`、附件 1MB 分界、
  双链规则、`路径#区块` 检索约定、机器目录隔离。
- **vault schema 加法**（`domain/vault.py`）：新增 6 个 `type`（`workstream` / `note` / `decision` /
  `source` / `index` / `long-form-thought`）与 1 个 scope `free`（绑定关系可为空，但不得 `project`
  与 `projects` 并存）。既有 type 与 scope 行为未变。
- **只读来源白名单加法**（`webapp/knowledge_sources.py`）：新增 `hii` / `it` / `community` / `hr` /
  `decisions` / `index`，否则 `路径#区块` 引用在来源面板点不开。
- **检索索引层**（`repositories/kb_index.py`）：frontmatter 结构化表 + 按 `##` 分块的
  **SQLite FTS5(trigram)** 全文索引；`(path, mtime, size, hash)` 增量 + 全量重建；
  FTS5 **先探测再决定**，不可用时退化为自带纯 Python BM25。索引库放
  `Application Support/SummitWorkbench/kb-index.sqlite`（**vault 之外**，不入 Git）。
- **查询路由**（`workflows/ask/router.py`）：点查 / 综合 / 回溯 / 决策 / 回顾五类，
  启发式（关键词加权 + 问句形态 + 时间词）兜底，模型判定为可选增强且故障时自动回落。
- **多信号融合**（`workflows/ask/fusion.py`）：FTS 正文/区块标题/标题分权 + frontmatter 过滤与
  元数据命中 + 类型权威加权（索引/MOC/决策优先）+ **双链扩展 1–2 跳**（别名可解析）+
  时间加权 + 去重 + **同源去重**（`source` 原件与其派生笔记同时命中时优先派生笔记）+
  导航型区块降权 + 单篇块数上限；每条命中都带「为什么命中」。
- **`路径#区块` 级引用**：`source_id` 升级为 `路径#区块标题`，与 Obsidian `[[文件#标题]]` 语法一致，
  Workbench 与 Obsidian 双向可点；`/api/sources/read` 支持按区块切片（响应新增 `anchor` / `heading`）。
- **检索轨迹**：`wb ask` 打印命中块、双链扩展链、被排除原因；问答页渲染为可折叠的
  「检索轨迹」区块。**逐字稿不进初始召回**，但通过会议笔记的 `## 证据索引` 在轨迹里显式暴露，
  使 `笔记 → 会议笔记 → 逐字稿` 可走通。
- **CLI**：新增 `wb kb index|status|route`；`wb ask` 新增 `--index/--no-index`、`--trace/--no-trace`、
  `--config-file`，并在默认配置缺失时回退到本机 active workspace 的 profile。
- **入库工具**：`scripts/kb_intake.py`（幂等 + 内容哈希去重 + 同 ref 冲突即停）、
  `scripts/kb_verify_quotes.py`（逐字引用校验 + **原件逐字保留**校验）、
  `scripts/kb_acceptance.py`（真实问题回归清单的可重复端到端验收）。
- **包内检索能力探针**：`server_entry.py --kb-diagnostic`（+ `kb_index.runtime_diagnostic()`）
  在**已构建的包**里实测 SQLite 版本、FTS5/trigram 可用性与「块级检索是否真的命中」。
  开发机 venv 支持 FTS5 不算数——冻结进 App 的解释器才是分发环境。探针对 FTS5 可用与不可用
  **两种结果都断言**：可用必须命中 `路径#区块`；不可用则自建 BM25 必须命中。此外还会在
  **同一进程里把 FTS 强制关掉**再跑一次，证明「打包环境真的缺 FTS5」时走的那条兜底分支
  在这台机器上也活着（只报告「FTS5 可用」证明不了这件事）。
- **人员索引再生成脚本**（`scripts/kb_index_people.py`）：`index/people.md` 正文写着「由聚合脚本
  重生成，不需要手工维护条目」，但那个脚本当时写在 `/tmp`、没有进仓库，页面因此不可复现。
  现在固化进 `scripts/` 并有 `--check`（页面与 frontmatter 不一致即非零退出）。
- **已安装 App 的端到端验收脚本**（`scripts/kb_acceptance_installed.py`）：通过**装到
  `/Applications` 之后那个 App 自己的本地服务**（`POST /api/ask`，即「第二大脑」面板调用的同一
  路由）发问，并用 `/api/sources/read` 逐条打开返回的 `路径#区块` 引用，验的是「装完到底能不能用」
  而不是「源码能不能跑」。会话令牌由 App 自己持有（原生启动器注入 bundle server），脚本从
  server 进程环境读取，**绝不打印、绝不落盘**。因为面板是受管 WKWebView、脚本无法可靠驱动，
  这条 API 口径是等价且可重复的替代（面板只负责渲染 `/api/ask` 的返回）。

### 修复

- **`install-macos-app.sh` 的 readiness 假失败与安全检查失效**（安装 build 35 时实测踩到；
  归档文档 §6.2 曾把它记为「踩过的坑」但一直没修）。打包 App 的 runtime record 落在
  `<app_support>/runtime.json`（原生启动器经 `WB_RUNTIME_RECORD` 注入，见
  `native/SummitWorkbench/RuntimeRecord.swift`），而 `wb web` CLI 落在
  `<app_support>/profiles/*/runtime/runtime.json`；脚本**三处**都只查后者，导致
  ① App 正在运行时检测不到，会绕过安全检查直接替换运行中的 App；
  ② 服务其实已就绪却误报「服务未在 readiness 窗口内启动」，退出码 1 并把
  `SummitWorkbench.app.previous` 留在原地。现在统一走 `runtime_records()`（与 Swift 侧
  `RuntimeRecord.candidateURLs` 同口径），readiness 遍历所有候选记录并在成功时打印实际使用的
  record 路径。真机复验：运行中拒绝安装（EXIT 1）、退出后干净安装（EXIT 0 且清理 `.previous`）。
- **损坏的索引库不再让问答直接崩**（`repositories/kb_index.py` / `workflows/ask/retrieval.py`）。
  实测复现：索引文件是垃圾内容时 `KnowledgeIndex.__init__` 抛
  `sqlite3.DatabaseError: file is not a database`，而模块文档承诺的是「索引损坏时降级检索」。
  现在三种真实失败形态都被妥善处理：垃圾文件 → **删掉重建**；旧版本残留 / 表结构不匹配
  （`CREATE TABLE IF NOT EXISTS` 修不了这种）→ **删表重建**；索引库根本建不出来（只读目录、
  路径不可写）→ 抛 `IndexUnavailableError`，`retrieve_via_index` 外层兜底**退回纯 Markdown
  子串扫描**并在检索轨迹里写明降级原因（`Trace.degraded`，问答页同步渲染）。FTS 影子表在
  查询期坏掉也会退化为自建 BM25。**索引是纯派生数据，坏了不能连累问答。**
- `wb ask` 此前完全看不到 App 配置的 workspace（provider 配置在
  `profiles/<workspace_id>/config.toml`），表现为「App 里配好了模型、命令行说配置不存在」。
- `scripts/kb_intake.py` 归档时标题降级未跳过围栏代码块，会把模板示例里的 `# 标题` 变成真实的
  `##` 区块，从而污染检索分块与引用锚点。
- 来源笔记 `id` 原先一律 `<date>-src`（同日多份会撞），改为由目标路径派生的稳定 4 位十六进制。
- `scripts/kb_acceptance.py` 的裁决逻辑抽成可测纯函数（`audit_case` / `evidence_chains`）：
  证据层只认 `meeting-transcript` 与 `source`。**会议笔记是派生摘要，不算证据层**——早先版本
  把它算进去，「笔记 → 会议笔记」这条链就能让验收通过，看起来走到了证据，其实停在摘要上。

### 测试

- 新增 `tests/unit/test_ask_chunking_terms_router.py`、`test_kb_index.py`、
  `test_ask_fusion_index.py`、`test_kb_scripts.py`、`test_vault_schema_kb.py`、
  `test_vault_templates.py`；`test_webapi.py` / `test_vault_repo.py` 增补。
- 关键信号均做**代码级变异验证**（删掉 source 降权 / 同源去重 / 类型权威加权 / 导航区块降权 /
  单篇块数上限 / 双链扩展，对应用例必须变红）。
- **真实问题回归清单从 2 题扩到 8 题**（`scripts/kb_acceptance.py`）：覆盖 ① 回溯 / ② 决策 /
  ⑤ 回顾三个优先场景，外加点查与综合。只有 Q1/Q2 真调模型，其余只验检索，**不增加 token 成本**。
- 新增 `tests/unit/test_ask_regression_questions.py`：同样 8 题跑在合成 vault 上（进 CI），
  每题断言「关键证据被召回 + 引用是块级 + ≤2 跳走到证据层」。问题清单**直接从 `kb_acceptance.CASES`
  取**，并有守卫测试防止两组清单漂移。
- 新增 `tests/unit/test_kb_acceptance.py`：锁住裁决者自身的判据，含「会议摘要不得冒充证据层」的
  回归（这条对应一次真实踩坑），以及编造区块 / 缺块级引用 / 缺追溯链 / 该有逐字稿却没走到。
- 新增 `tests/unit/test_kb_people_index.py`：排序（条目数降序、同数按名字升序）、前 4 篇预览与
  `（共 N 篇）`、模板与机器目录排除、`--check` 在页面过期时必须红。
- `tests/unit/test_kb_index.py` 增补四类失败形态：索引文件是垃圾内容、只读目录、表结构不匹配、
  FTS 影子表损坏。
- **prompt 版本锁定**：`qa-answer` 升到 v2 后没有任何测试锁住文件版本，`test_ask_workflow.py`
  还停在 `Prompt(version=1)`。现在断言文件为 `qa-answer@v2`、正文含 v2 的 `路径#区块标题`
  契约，并让编排测试的 stub 与文件同版本。
- `tests/integration/test_packaged_app.py` 增补包内 `--kb-diagnostic` 探针断言（FTS5 可用与否
  都必须证明块级检索可用）。

### 2026-09-13 · 交付包 build 34：D9/D10/G1/G2/G3 收口 + 仓库与冗余代码清理

> 按 `docs/implementation/HANDOFF-NEXT-DELIVERY-AND-CLEANUP.md`（已归档到
> `docs/archive/plans/`）执行：先修完未决项，再打交付包，最后做等价清理。
> 交付包 **build 34**（`0.4.7` / arm64 / `INTERNAL-DEV`，源码 `8b7767d`，
> `frontend_build = v2026.09.13-8b7767d-ae564ff2`，DMG SHA-256
> `3ca3aae74577264e2c106e81599bb32d272eddf80725c29264c8cb7a8a4fa73d`，
> app SHA-256 `fd702441093ba670837a0e26e6dbeffae47461c61a6413b626854be38066a829`，
> **内置飞书凭据**、`REQUIRE_BUNDLED_FEISHU=true`）。真机逐条核验证据见
> `docs/acceptance/OPEN-VERIFICATION-ITEMS.md` §R。

#### 修复

- **D9 · 恢复提交后的 push 被误判为非快进**：dulwich 的 `graph.can_fast_forward` 用
  **commit_time 剪枝**挑公共祖先，远端父提交比本地提交新（跨机时钟偏差）时会把真快进判成分叉
  （`porcelain.DivergedBranches` ⇒ `non-fast-forward`）。现在 `DulwichGitBackend.push` 捕获它之后
  用**不看时间戳的图可达性**（`_is_ancestor`，只沿 parents 做 BFS）复核：确认远端 tip 是本地 head
  的祖先时，才用 `_push_refspec`（远端 ref 取 `branch.<name>.merge`）**只对这一个分支**显式强推一次；
  复核不通过仍是 typed `GitNonFastForward`。**绝不无条件 force。** 测试构造两跳时钟偏差（恢复+审计）
  并前置断言确实落在 dulwich 的坏区，另加真分叉对照用例；变异验证：去掉图复核 ⇒ 前者失败，
  `_is_ancestor` 恒 True ⇒ 后者失败（远端被覆盖）。
- **D10 · 「连接已有工作台」把角色一律写成 secondary**：`connect-local` 与 remote clone 都无条件写
  `secondary`，而 `automation_gate` 只在 profile 为主设备且 claim 匹配时放行定时 writer ⇒ marker
  指定的主设备上定时自动化根本不跑，界面又没有改角色的入口。新增
  `automation_primary.connect_device_role`：声明 device 是本机 ⇒ `AUTOMATION_PRIMARY`；声明属于
  别的设备 ⇒ `SECONDARY`（**绝不抢占**）；无声明/损坏/异 workspace ⇒ 沿用既有默认 `SECONDARY`。
  变异验证：恒 `SECONDARY` / 恒 `AUTOMATION_PRIMARY` 分别让对应用例失败。

#### 新增

- **G1 · 主设备的声明/接管与降级入口**：设置页「高级与维护」新增「定时自动化主设备」区块——
  显示本机 device id、当前主设备 + generation、本机角色；尚无声明⇒「声明本机为主设备」，
  别的设备持有⇒**勾选确认 + 二次确认 + `expected_generation`** 才能「接管主设备」，
  本机角色为主设备⇒「降级为备用设备」。后端 `/api/sync/primary/claim` 成功后同步本机 profile 的
  `device_role`，并新增 `POST /api/sync/primary/downgrade`（只改本机 profile，vault 内的声明不动）；
  route contract 快照随之重新生成。失败按稳定错误码映射成人话
  （`primary_already_claimed` / `primary_generation_conflict` / `primary_state_corrupt` …）。
- **G2 · 首次发布到空远端**：没有任何 origin 的工作台此前只能手工 `git remote add` / push。
  新增「首次发布到远端」区块与 `POST /api/settings/git/remote/publish`：只接受 HTTPS 与**空**远端，
  先在临时克隆里 `ls_remote` 核对并真推一次证明可推送，再 `add origin` → 首次 push → 写
  profile/Keychain → 最后写 upstream；push 之前失败一律 `remove_remote` 回到"没有远端"。
  为此给 `GitBackend` 增加 `remove_remote` / `set_upstream`（等价 `git remote remove` / `push -u`），
  dulwich 与 system 两个后端行为一致并有 conformance 覆盖。
- **G3 · 同步失败落盘**：新增 `observability/server_log.py`，把同步/推送失败写进
  `~/Library/Logs/summitworkbench-server.log`（JSONL、0600、5 MiB 轮转，与 launcher 的 panel 日志
  分开）。只写稳定原因码、计数与异常**类名**；事件名/reason 分别经 snake_case、kebab-case 白名单，
  不合形状的替换为占位符并只报"丢了几条"；日志写入 best-effort（只吞 `OSError`）。D9 的
  "图复核通过 ⇒ 强推成功"也落一行。**绝不写进 vault**。测试用一个含 URL + 凭据 + 用户路径的假异常
  跑一遍并断言日志文本里没有它们。

#### 变更（清理，等价、不改行为）

- **磁盘产物**：删除 `dist/releases-local-v0.4.4*`（14 个）、`b25`、`b33` 与
  `SummitWorkbench-0.4.6-arm64-INTERNAL-DEV.dmg`，以及 `.coverage`/`htmlcov`/`.mypy_cache`/
  `.pytest_cache`/`.ruff_cache`/`.hypothesis`/`__pycache__`/`.DS_Store`。仓库 2.0 GB → 346 MB，
  `dist/` 只剩 build 34。b25 里的 `feishu-defaults.json` 已先留档到仓库外
  （`~/Library/Application Support/SummitWorkbench/secrets-backup/feishu-defaults.json`，0600）。
- **文档**：已执行完毕的交接文档归档到 `docs/archive/plans/` 并在原路径留一行指针；其余实现/验收
  文档仍有 CHANGELOG/README/PROJECTDESC/ADR/测试注释的入引用，按铁律不动（逐文档引用统计见
  `docs/acceptance/OPEN-VERIFICATION-ITEMS.md` §R）。
- **冗余代码**：vulture 2.16（经 `uvx` 临时运行，未写入依赖）在 src+tests+scripts 命中 4 条 @80%，
  逐条 grep 后删除三处：`legacy_app.py` 不可达的重复 `return app`、
  `_FeishuClientPool.tenant_client`（全仓零引用）、`test_llm_client.py` 未使用的 `capfd`。
  `config/settings.py` 的两个"未使用变量"是 pydantic-settings 的**按关键字**调用形参，保留。

#### 发布

- 门禁：`tsc`、14 个前端脚本、`pytest --cov`（**971 passed / 1 skipped，覆盖率 83.54%**）、
  `ruff check`、`ruff format --check`、`mypy`（340 files）、`scripts/secret_scan.py`、
  `web/scripts/verify-build.mjs`、打包冒烟（`WB_PACKAGED_APP=/Applications/SummitWorkbench.app`）
  全绿；`scripts/release-macos.sh` 完整跑通并产出 DMG（含内置凭据结构校验）。
- 真机（Studio）：安装 build 34 后 `runtime.json.frontend_build` 为新包、
  `/api/sync/status` = `ready` / ahead-behind `0/0`、`acceptance-preflight` **11/11 PASS**
  （含 `automation-role: automation-primary`）、`POST /api/sync/run` 对真实 HTTPS 远端成功、
  两个新路由存在、服务日志按 0600 落盘。
- 真机（Air，**全新机器从第一步配置**）：同一个 DMG 从零走完向导（克隆 → 模型 → 飞书，
  飞书用**包内内置凭据**、本机零预置），`frontend_build` 与 Studio 一致、
  `device_role = secondary`（D10 真机：marker 指向 Studio ⇒ 全新 profile 不抢占）、
  服务日志 0600 且**零 `sync_failed`**。
- **真机双机冒烟（通过）**：Air 捕捉「测试」⇒ `598a285 wb: capture [b8a7633e-…]`（只改
  `inbox.md` +4 行）⇒ Studio 自动拉取（`last_sync_at 03:40:32Z`）并手动 `POST /api/sync/run`
  复核 ⇒ `HEAD == origin/main == 598a285`、`ahead/behind 0/0`、`pending 0`、vault 工作树 clean、
  线性快进无保护态；Studio 的主设备声明未被改写（仍为 `51885d3d-…` / generation 1）。
  逐条证据见 `docs/acceptance/OPEN-VERIFICATION-ITEMS.md` §R.7。
- **开放项（已闭合）**：两个演练仓库由使用者在 GitHub 网页删除，代理复核 `gh repo view` 均 404，
  本地残留（含 `/tmp` 里前几轮遗留的会话令牌 `.t3`–`.t8`）一并清除，见 §R.6.1。
- 远端 CI：本轮提交按要求全部带 `[skip ci]`（未自动触发），收尾时经使用者同意手动触发一次
  `workflow_dispatch` 验证当前 HEAD ⇒ **全绿**（`quality-gate`：actionlint/ruff/format/mypy 340 files/
  pytest 971 passed·83.55%/tsc/前端测试/build+verify/secret scan/native；`macOS arm64 contract`：
  构建 + 打包冒烟 1 passed；`x86_64` 按预期拒绝）。
  run <https://github.com/SummitYifeng/SummitWorkbench/actions/runs/34746739863>（HEAD `70f236e`，2m18s）。
- **开放项（使用者明确决定不做）**：G2 的"真实 GitHub 空仓库 → 绑定 → 首次 push"成功分支未做
  端到端（其余已覆盖：单测 + API 契约 + 真机非 HTTPS 拒绝路径 + 两后端一致性）；需要时按
  §R.6.3 的 4 步现场确认。
- 真机（Air ⇄ Studio，G1 接管闭环，**通过**）：Air 在界面里勾选接管（必须先勾选，未勾选被拒）
  ⇒ generation 1→2、Air 变主设备 ⇒ Studio 侧自动化被门控关掉（`not-primary`，零写入、声明哈希不变）
  ⇒ Studio 用**过期** generation 接管被拒（409 `primary_generation_conflict`、零写入）⇒ 用当前
  generation 接管回来（→3）⇒ Air 降级为备用设备后其「立即运行」返回绿色 `not-primary`，且远端
  **没有**任何 `wb: brief 2026-09-13` 提交被偷偷写入。逐条证据见 §R.8。

### 2026-09-13 · 双机复跑发现的缺陷修复（D1–D6）

> Studio + Air 现场复跑「第二台机器接入 + 冲突恢复」时逐个撞出来的问题，全部已修并逐个做了
> 变异验证；A6/A7 的现场结论与证据见 `docs/acceptance/OPEN-VERIFICATION-ITEMS.md` §N。
> 内部产物 **build 29**（`0.4.7` / arm64 / `INTERNAL-DEV`，源码 `d2b07bd`，DMG SHA-256
> `bfe7fb504f94afe5803493bf8be8d34b9e554b2c6d6d49cab0c3a44647e1de2b`）。

#### 新增

- **顶部栏「⇅ 立即同步」+ 空闲自动拉取（D6）**：此前 `/api/sync/run` 只能从同步横幅的
  「立即重试」触发，而横幅在状态 ready 时是隐藏的 ⇒ 干净、只读为主的设备**没有任何拉取入口**，
  会一直显示旧数据，且它下次写入时必然撞上分叉。现在顶部栏按钮随时可点；启动时、切回窗口时
  以及每分钟都会在**工作树干净且无保护态**时自动拉一次（脏工作树绝不自动合并的既有保护不变）。
  按钮与自动拉取共用在途守卫，连点不会撞 workspace 锁。

#### 修复

- **新工作台纳入版本管理（D1）**：`新建我的工作台` 此前从不 `git init`，导致「系统写回自动
  git 留痕」静默失效（`commit_paths` 返回 `NOT_GIT`），且设置页「预览 HTTPS 转换」直接
  `500 internal_error`（日志为 `GitError: 不是 git 仓库`）。现在创建时经 P0-09 backend 初始化
  仓库并落一个 `wb: onboarding create` 提交；分支固定 `main`（不再继承 dulwich 的 `master`）。
  历史非 git 工作台会得到稳定错误码 `vault_not_a_repository` 与可执行说明，而不是 500。
- **转换 remote 后无需重启（D2）**：`ActiveWorkspaceContext` 在启动时冻结，而 `git_username`
  是「确认并转换」写进磁盘 profile 的 ⇒ 同一进程内点「立即重试」必然失败（凭据按空用户名查找），
  只有重启才好。同步现在从磁盘读当前 `git_username`（读不到回退快照）。
- **同步失败会说原因（D3）**：拉取路径此前 `detail` 恒为空、写路径把 `str(exc)` 原文写进状态，
  而 `GitCredentialsUnavailable` 没有分类分支 ⇒ 缺凭据与代理故障都表现为裸 `error`。现在每个
  失败给一个**稳定原因码**（`credentials-missing` / `proxy-unreachable` / `tls-failed` /
  `auth-rejected` / `non-fast-forward` / `offline` …）与中文短句，写进 `sync-state.json` 与横幅；
  原始文本（可能含 URL/主机/路径）绝不落盘；缺凭据归类为 `auth-required`。
- **向导收尾干净（D5）**：进入工作台时清掉安装级草稿（此前从不 DELETE，`step:'done'` 会留着，
  同一台机器下次空安装会停在第 3 步）；草稿里的 `~/…` 路径按给定 home 展开成绝对路径，不再与
  同一份草稿里的 `work_root` 不一致。
- （D4 随 build 28）私有 clone 的失败原因此前被兜底吞掉：`GitCredentialsUnavailable` /
  `GitProxyError` 无分支、兜底只给「请检查凭据、网络或 TLS」；现在各有稳定码，兜底带异常类名，
  向导也会显示 `details.reasons`。

#### 测试与验收

- 每个缺陷都配了行为测试与**变异验证**（去掉修复即失败）：D1 创建后 `is_git_repo()`、
  D2 同步用磁盘用户名、D3 失败码可见且无原文泄漏、D5 路径展开与草稿清除、D6 只在 ready 时
  自动同步且连点只发一次。
- 门禁：`tsc` 干净、14 个前端脚本全绿、`pytest` **941 passed / 1 skipped**
  （覆盖率 83.46%）、ruff / format / mypy / secret scan 全过。

### 2026-09-13 · 冲突恢复的可重复执行与可诊断性修复（D7/D8）

> 双机复跑收尾（A6 完整闭环的第 5–6 步）时撞到的两个问题，都在**冲突恢复**这条路径上，
> 且互为因果：界面上看不到原因（D7），而真正的原因是恢复**对同一文件不可重复执行**（D8）。
> 源码提交 `fd19603`，附单元/契约测试与变异验证；随内部产物 **build 30** 出包
> （`frontend_build = v2026.09.13-b31c3ac-c7517c5a`，DMG SHA-256
> `8a87044ba839ba2c291013a5b6d373b7834e9f1596259da9fa89fda0a131b645`），
> 并在真机上复验 D8 通过（见下）；
> 完整复现步骤与证据见 `docs/acceptance/DUAL-DEVICE-REHEARSAL.md` 文末「附」。

#### 修复

- **预检被拒时会说清原因（D7）**：冲突恢复弹层的「预检并写入」失败时，后端其实已经把原因放在
  `preparation.error_code`（例如 `preserve_both_path_collision`），但前端只读 `data.reason`，
  读不到就落回写死的「恢复准备未完成。」——用户看不到任何可执行信息。现在按错误码给
  **可执行的提示表**（`RECOVERY_FAILURE_HINTS`：快照过期 / 工作树脏 / 选择不完整 / 选择非法 /
  同名远端副本已存在 / 投影重建失败 / 远端内容缺失），未知码退化为带码文案
  「恢复准备未通过（<code>）：请重新打开冲突详情后重试。」，`data.reason` 仍然优先。
- **「保留双方副本」可重复执行（D8）**：第一次恢复把远端内容写到 `<path>.remote` 后，第二次对同一
  路径再选「保留双方副本」会因为 `target.exists()` 直接
  `raise ValueError("preserve_both_path_collision")`，**整次恢复被拒**——而「先保留双方、之后
  再合一次」正是最自然的动作。现在兄弟名带远端 revision 短码（`<path>.remote.<rev7>`）：同一份
  远端内容仍落同名（可重复预检、不产生垃圾），不同内容天然不同名（**绝不覆盖**那份唯一副本），
  并把实际落盘的相对路径回填进 `candidate_paths`，让预检报告与写回结果一致。

#### 测试与验收

- D7：`web/scripts/test-sync-render.mjs` 用**真实的被拒响应体**（`preparation.error_code` +
  `recovery.error_code`）断言弹层含具体原因、且不再出现「恢复准备未完成」；变异验证（去掉查表）
  复现旧文案。
- D8：`tests/unit/test_sync_conflict_recovery.py::test_second_preserve_both_uses_a_revision_suffixed_sibling`
  连做两次「保留双方」并断言两份副本内容都在；变异验证（恢复旧的 `raise`）复现
  `status='rejected'` + `preserve_both_path_collision` + `candidate_paths=()`。
- 门禁：`tsc` 干净、14 个前端脚本全绿、`pytest` **942 passed / 1 skipped**（覆盖率 83.47%）、
  ruff / format / mypy / secret scan 全过。
- 登记了本轮顺带确认的三个**能力缺口**（非缺陷，见
  `docs/acceptance/OPEN-VERIFICATION-ITEMS.md` §N）：界面无 `automation-primary` 接管入口、
  无「把已有本地工作台首次发布到新远端」的路径、同步失败仍不落盘到 `~/Library/Logs`。
- 现场代价与 build 29 的逐条复核见 §O：D8 在真机上把用户从「保留双方」逼成「保留本机」，
  远端那条捕捉最终只剩第二父提交 `f013de6` 一个副本（工作树里 `grep -rl 离线-A2` 已找不到）。
- **D7 第一版只接了一条路径（真机复验当场发现，`7bfe40b` 修）**：恢复失败有**三条**路径——
  `selection/validate` 的拒绝（不带 `reason`，第一版直接把 `error_code` 当消息显示，使用者在弹层里
  看到的就是裸的 `conflict_snapshot_stale`）、`recover` 的预检分支、apply 分支的
  `恢复未提交：<code>`。现在三条共用 `recoveryFailureMessage(reason, code, fallback)`，
  弹层「临时预检未通过 · 原因：」也显示同一句人话；`web/scripts/test-sync-render.mjs` 为 selection
  路径补了真实响应形状的 stub + 断言（变异验证：改回裸码形态立刻渲染出
  `<div class="msg err">conflict_snapshot_stale</div>`）。修复随 **build 31** 出包
  （`frontend_build = v2026.09.13-7bfe40b-9517f794`，DMG SHA-256
  `0cff5d1c5633d296515203894801beeedfc5183af0fbad25ac5fe211fad36b3c`），并在真机上复验通过。
- **真机复验（build 30/31，见 §P）**：在装好的 build 30 上重造分叉（本地 `wb: capture [d8-local-verify]`
  vs 远端 `wb: capture [d8-remote-verify]`，且 vault 里本来就躺着第一轮的 `inbox.md.remote`），
  走真实恢复接口选「保留双方副本」：预检 `status=validated / error_code=null`（不再被拒），
  写回 `applied_paths = ["inbox.md.remote.09aebd7"]`，第一轮的 `inbox.md.remote` 哈希不变
  （`13bfc790…`），本机与远端两份内容同时在位。

### 2026-09-13 · 双机复原收尾（Phase 6）

Studio 与 Air 都回到**真实工作台**（`bf22c8d2-…` / `YifengWorkKnowledge`），两台 HEAD 相同
（`86cc529`）、各自 `ready`、ahead/behind `0/0`：

- **Studio**：清空档案后由向导重新连接 `~/Documents/Work/_vault`，重做 HTTPS 转换；
  设备角色修正为 `automation-primary`（见 §Q.1 的 D10），App 自带 11 项 `acceptance-preflight` 全 PASS。
- **Air**：原 profile 已丢失（`real-bak` 并不存在），按**新设备**重建——空档案 +
  「从另一台 Mac 克隆」拉取真实 vault，得到**新 device id** 并落为 `secondary`；
  模型/飞书沿用 workspace Keychain，git 凭据由克隆流程写入。
- 日常使用包 **build 33**（含 D11 与内置飞书凭据）；Studio 侧演练残留与中间构建产物已清理。

### 2026-09-13 · 修复：已 typed 的远端错误不再被文本兜底重分类（D11）

`_classify_remote()` 只按异常**文本**匹配，从不检查传入的是不是已经是我们自己的稳定类型。
于是 `fetch()`/`push()` 里 `transport_kwargs()` 抛出的 `GitCredentialsUnavailable`
（"缺少 workspace-scoped Git 凭据配置"）被同一个 `except Exception` 接住后重新包装成
`GitBackendRuntimeError` ⇒ 原因码 `unclassified`、状态裸 `error`，界面只说
「未分类的同步失败（unclassified）」——**恰好把 D3 想说的"本机缺凭据"说没了**。
（2026-09-13 复原机器时实测到：`/api/sync/status` 就是这个文案。）

修法：`_classify_remote()` 开头 `if isinstance(exc, GitError): return exc`——已经脱敏且已分类的
错误原样抛出，只有真正的未知异常才走文本映射与兜底。两个新测试（typed 原样返回 +
`credentials-missing`/`AUTH_REQUIRED`；注入抛 `GitCredentialsUnavailable` 的 resolver 后
`fetch()` 仍是 `credentials-missing`）都做过变异验证（去掉守卫即失败）。真机复核：同一路径修复前
是 `GitBackendRuntimeError`/`unclassified`/裸 `error`，修复后是
`GitCredentialsUnavailable`/`credentials-missing`/`auth-required`。随内部产物 **build 33**
（`989ce9c`、`frontend_build = v2026.09.13-989ce9c-9517f794`、DMG SHA-256
`29e3ae3d8b5aeb952200144432bb313e83e11b72be8036f7c9f82afc4cd32a6a`，同样内置飞书凭据）出包；
`_vault` 上的 App 自带 11 项 `acceptance-preflight` 全部 PASS（含 `automation-role: automation-primary`）。

### 2026-09-13 · 内部产物 build 32（补回内置飞书凭据）

`build 27–31` 为测试包，构建时未导出 `WB_FEISHU_APP_ID` / `WB_FEISHU_APP_SECRET`，也没有
`~/.config/summitworkbench/config.toml` 兜底 ⇒ 在这几个包上飞书拿不到 app_secret。日常使用包
**build 32** 用 build 25 包里那份凭据（仅经环境变量传入构建，不落仓库）重打，凭据回退链恢复为
「显式配置/Keychain > 内置默认」。源码 `1bd8572`、`frontend_build = v2026.09.13-1bd8572-9517f794`、
DMG SHA-256 `15a57239cc8836d61031f72f6305da43ab43ad62a5b54c761e857f65e2920df5`。
**生产包要用 `REQUIRE_BUNDLED_FEISHU=true` 构建**，缺凭据就直接失败，而不是悄悄出一个不能授权飞书的包。

### 2026-09-13 · 已修（build 34）：恢复提交后的 push 可能被误判为非快进（D9）

> 只在 build 30 真机复验时暴露：**dulwich 判定"能否快进"用的是提交时间戳剪枝，不是图可达性**。
> 当远端父提交的 committer time 晚于本地恢复提交（跨机时钟偏差，或任何把提交时间写晚的来源），
> 恢复本身成功、推送却被拒，workspace 卡在 `diverged-protected`，而 git 自己的
> `merge-base --is-ancestor` 认为这是一次干净快进。**已在 build 34 修复**（图可达性复核 +
> 单 refspec 显式强推，见上文「2026-09-13 · 交付包 build 34」块）。

- **复现（build 30 真机）**：远端父 `09aebd7`（`commit_time = 01:50:00Z`）、本地恢复提交
  `001df9a`（`01:47:21Z`）+ 审计 `f0a51bc`（`01:47:22Z`）⇒
  `dulwich.graph.can_fast_forward(repo, 09aebd7, f0a51bc) = False`，而
  `git merge-base --is-ancestor 09aebd7 HEAD` = **YES**；`porcelain.push` 抛
  `DivergedBranches(b'09aebd7…', b'f0a51bc…')`，App 归类为 `non-fast-forward`。
  同一对提交用系统 git（走代理）推送**成功**（`09aebd7..f0a51bc`），证明远端接受这次快进、
  拒绝完全来自客户端的前置检查。
- **直接子提交不触发**：`can_fast_forward(09aebd7, 001df9a) = True`——多一跳（审计提交）才踩到
  时间戳剪枝，所以"恢复提交 + 审计提交"这个固定组合正好落在坏区里。
- **为什么真机也会遇到**：本次是人工造的远端提交时间偏晚触发的，但同样的形状在**两台机器时钟
  有偏差**（哪怕几分钟）时天然成立——对端"未来"的提交 + 本机按真实时间生成恢复提交。
- **修法方向**：在 `DulwichGitBackend.push` 里捕获 `porcelain.DivergedBranches` 后，用**不依赖
  时间戳的图可达性**复核（从本地头沿 parents 走到远端 ref）；只有确认真快进时，才对该 ref
  显式 `force=True` 重推一次，并把"图复核通过"写进状态原因。不做无条件 force。


## [0.4.7] - 2026-09-12

> 分发版：让**同事拿到 DMG 装完就能用**——飞书授权从「需要管理员在每台机器上预置
> config.toml 与 Keychain」变成「点一下『授权飞书』」。做法是把飞书 app_id 与
> app_secret 作为**默认值**在构建时写进包内资源（`Contents/Resources/feishu-defaults.json`），
> 并在运行时按「显式配置/Keychain > 内置默认」的顺序回退。产品行为与数据格式未改动。

### 新增

- **内置飞书默认凭据（分发包）**：新增
  `providers/feishu/bundled.py`，从包内 `feishu-defaults.json` 读取 app_id / app_secret /
  redirect_uri；文件由 `scripts/build-macos-app.sh` 在**签名之前**从环境变量
  `WB_FEISHU_APP_ID` / `WB_FEISHU_APP_SECRET` 生成，仓库内不存在该文件（`build/`、`dist/`
  均被 git 忽略），因此密钥永不进版本库。
- **配置回退链**：`load_feishu_config()` 现在按「配置文件里的 `[feishu]` 表 → 包内内置默认值 →
  显式报错」解析。显式写了 `[feishu]` 却漏字段时仍**严格报错**，不会被内置默认值掩盖。
- **凭据回退链**：`FeishuSession._app_secret()` 按「workspace 作用域 Keychain → 旧命名
  Keychain（一次性迁移）→ 包内内置默认值」解析；内置值**只读不写**，不会把厂商秘密复制进
  用户 Keychain，用户自己存的条目始终优先。
- **发布门禁**：`REQUIRE_BUNDLED_FEISHU=true` 时，构建缺少内置凭据即失败；
  `verify-macos-release.sh` 对包内凭据文件做结构化校验，并在通用 secret scan 中把它列为
  **显式例外**（该文件是唯一有意内置的秘密，见 `docs/RELEASING.md`）。
- **授权失败不再「只说失败」**：分发包内置凭据后同事本机没有任何可改的配置，失败时必须由
  界面告诉他找谁、做什么。现在令牌端点的失败码会被翻成可执行提示（`20010` → 「你的账号还没有
  这个应用的使用权限：请联系管理员把你加入应用『可用范围』」、`20002` → 「内置的应用凭据无效
  （可能已轮换）：请联系管理员重新发布安装包」、`20003/20004/20065` → 重新授权），并透传到
  向导界面（此前只显示「飞书授权未完成，请重新点击授权」，同事只能反复点）。用户点「拒绝」时
  也区分文案。原始错误码保留在消息里便于审计，**凭据与授权码绝不回显**（有专门测试断言）。
  授权状态（`feishu-auth-state.json`）新增可选 `reason` 字段；查询状态不消费原因，App 重启后
  仍能看到解释。**设置页的「重新授权」回跳也补上了提示**：此前 `?feishu=failed` 完全没被处理，
  失败后静默回到设置页（而指南恰恰让用户用这条路径从令牌失效中恢复），现在会取回原因并按
  `textContent` 安全显示（不引入转义风险），查询串随即清掉以免重复提示；前端契约测试新增
  三条守卫并做过变异验证（把取回原因的端点改坏即报出对应断言）。**拿不到会话 cookie 的静态
  回退页同样说明原因**（`_panel_redirect`：没有 state / 状态失效 / 已记录失败 / 用户取消各有
  对应文案），该页会把未信任的 `error` 参数拼进 HTML，因此做了转义并有专门断言。
- **修复 provider 设置的丢段竞态（现场发现）**：`update_provider_settings` 原本是无锁的
  读-改-写，而向导会先后写「模型」段与「飞书」段（模型验证与授权回调可能几乎同时到达）。
  并发时后写者会基于自己读到的旧快照落盘，**静默丢掉另一段**——现场表现正是「授权成功、
  Keychain 有可用 refresh_token，但设置页显示未连接」。现在整段 load→改→save 持有
  per-workspace 锁（锁根在 `Application Support` 下的 `locks/<workspace_id>`，刻意不放在
  profile 目录里，避免失败路径造出空 profile）；并补了**确定性并发交错测试**：无锁时该测试
  必然报出「模型段被并发写入覆盖」（已做变异验证）。
- **测试**：新增 `tests/unit/test_feishu_bundled.py`（15 例）、
  `tests/unit/test_feishu_authorization_reason.py`（14 例，含「被拒绝 → 向导显示原因」的
  端到端用例与静态回退页的注入转义用例）、
  `tests/unit/test_profile_settings_concurrency.py`（3 例，含并发丢段回归）与
  `tests/unit/test_feishu_session.py` 的 3 例，覆盖回退链两个方向、显式配置优先、
  显式配置缺字段仍报错、内置文件损坏、无内置时保持原有报错文案，以及**打包运行时契约**：
  按 `WB_STATIC_DIR` 与 server 可执行文件相对路径两条查找路径都能命中内置凭据文件、
  显式覆盖优先、空串覆盖＝显式关闭。这些测试都做过**变异验证**（删掉 `WB_STATIC_DIR`
  分支、让空串覆盖不再禁用探测、去掉 provider 设置的互斥，都会被对应测试抓住），确认不是空转。
- **端到端验证（真实凭据，2026-09-12 现场）**：在**清空 Application Support + 移走
  `~/.config/.../config.toml` + Keychain 无任何凭据**的干净机器上，从 DMG 安装 0.4.7 后由
  使用者本人走完向导三步：连接已有 `_vault` → 粘贴 DeepSeek API Key（现场验证成功）→
  点「授权飞书」并在浏览器同意。结果：workspace 作用域 Keychain 出现真实 refresh_token
  （1771 字符），用它可以成功刷新出 access_token（1703 字符）——**零预置、点一下即可完成
  授权**这一目标达成；Keychain 中没有 app_secret 副本，证明用的是包内内置值且只读。
  另外用包内 secret 换 `tenant_access_token` 成功，证明凭据在飞书侧有效。
  此前的占位 secret 构建则用于验证：授权 URL 取自包内 app_id、真实飞书失败会翻成可执行提示、
  静态回退页与状态端点都会带上原因。

### 为什么必须内置 app_secret

飞书 `authen/v2/oauth/token` 的 `client_secret` 是**必填**，`code_verifier`（PKCE）只是可选的
额外保护，**不能替代** client_secret（官方文档：<https://open.feishu.cn/document/authentication-management/access-token/get-user-access-token>）。
分发包里没有可代持秘密的后端，所以「零预置 + 点一下就能授权」与「秘密不进客户端」二者不可兼得。

### 已知代价（明示，不做隐瞒）

- 拿到 DMG 的人都能提取出这个 app_secret（它是**应用级**凭证），可据此以应用身份调用飞书
  API、读取该应用已授权范围内的数据。这只在「内部自建应用 + 信任圈子」前提下可接受。
- 若要消除该风险，需要把令牌换取搬到管理员自建的后端代理（app_secret 只留在服务端），
  属于后续可选改动，本版不做。
- 飞书开放平台侧仍需管理员保证：应用「可用范围」包含每位同事、`offline_access` 等 scope
  已开通、重定向 URL 已登记 `http://localhost:8765/callback`。

### 发布

- tag `v0.4.7` → release run
  [#34670529202](https://github.com/SummitYifeng/SummitWorkbench/actions/runs/34670529202)（success，
  2m20s；含 secret scan、打包集成测试、P1-07D 双机验收门与发布步骤），产物发布在
  <https://github.com/yifeng93/SummitWorkbench-Updates/releases/tag/v0.4.7>，`latest` 已指向
  `v0.4.7`（公开 `update-feed.json`：version 0.4.7 / build 21 / arm64）。
- DMG SHA256：`ea9651182f4baaa38556068dbdb5d3ef7d69a8051d5a4bc65e3184791108e930`
  （49,431,182 字节）。构建号为 **21**，由 CI 的 `github.run_number` 决定。
- 发布构建需要仓库 `release` environment 下的 variable `WB_FEISHU_APP_ID` 与 secret
  `WB_FEISHU_APP_SECRET`；stable 通道还要求 `UPDATE_DOWNLOAD_URL` 指向当前版本的 DMG
  （本次已从 `v0.4.6` 更新到 `v0.4.7`），否则 `release.yml` 按设计直接失败。
- **双机现场验收（发布后）**：在一台**从未安装过**的 Mac 上完成——直接跳转飞书授权并成功、
  配置 DeepSeek API 成功、进入界面后生成简报成功。这一条同时反证了 CI 产物内内置凭据正确
  （发布前只能核验 feed/metadata 与本地同源构建，无法字节级核验 CI 产物）。
- 本机（该 workspace 的原机器）另有本地预发布构建 build 25，仅用于开发期验证；对外的可分发
  产物是上面这个 build 21。

## [0.4.6] - 2026-09-12

> 补丁版：修掉 `v0.4.5` 留下的、指南首页那行版本标记的显示瑕疵。**产品行为同样未改动**——
> 只改了指南开头一句文案并重建前端。

### 修复

- 指南首页原本硬编码 `适用版本：v0.4.5 build 19`。这类写死的版本号**每次发版都会过期**：
  指南正文是构建时打进的静态文本，不随 App 升级自动更新，而 `v0.4.5` 的产物里它恰好还是
  发布前误估的 `build 13`。现在不再写任何具体版本号，改为指引读者看**窗口顶栏右上角的实时状态**
  （形如「界面 v… · 服务 x.y.z · 已同步」）——那里读的是运行中的真实值，**永远不会漂移**。
  这同时修掉了"标记写错"与"标记必然过期"两个问题，而不只是把 13 换成 20。

### 说明

- 因指南是构建输入（`web/scripts/sync-guide.mjs` → `web/src/guide.md`），文案改动会改变前端
  `source_hash` 与构建身份，故前端静态产物随之重建并单独提交；`verify-build.mjs` 通过。
- 已发布并装机的 `v0.4.5`（build 19）产物身份保持不变，本版在其之上只做这一处文案修正。
- 无新增测试：本次改动是纯文案 + 产物重建。已完成的门禁与 `v0.4.5` 相同
  （890 passed / 1 skipped、覆盖率 82.33%、ruff、mypy strict、`tsc`、前端契约测试全绿）。

## [0.4.5] - 2026-09-12

> 交付前最后一轮审查与清理版。**首要目标是不改变行为**——v0.4.4 的验收刚刚结束，本轮所有改动
> 都属于删除无引用内容、文档更正与文案重写，**未触碰任何产品行为逻辑**（路由、写回边界、锁语义、
> outbox、schema/迁移一律未动）。基线为 `v0.4.4` build 12。

### 变更

- **「指南」页重写为任务导向**：`docs/product/WEB_USAGE_GUIDE.md` 从按页签/架构组织改为按
  「我想做什么」组织（记一件事 / 处理今天待办 / 处理审批 / 导入会议 / 看项目进展 / 问第二大脑 /
  多设备同步 / 撤销 / 排障），默认只显示步骤，原理与边界条件收进引用块，面向不读代码、不开终端
  的账号所有者。渲染器未改动，指南渲染契约测试（本地搜索、目录、H2/H3 分组、筛选跟随）原样通过。
- 更新现状类文档：`README.md`、`PROJECTDESC.md`、`docs/product/WEB_WORKBENCH.md` 的版本/构建号与
  质量门数字由过期的 build 9 更正为当前基线（890 passed / 1 skipped、覆盖率 82.33%）。
- `docs/archive/` 增加归档标注（历史记录、结论可能过期、当前状态以
  `docs/acceptance/OPEN-VERIFICATION-ITEMS.md` 为准），**归档正文未改动**。

### 移除

- 删除 4 个完全空的目录：`docs/architecture/`、`docs/background/`、`docs/design/`、`docs/plans/`
  （`ls -A` 确认连隐藏文件也没有，且均未被 git 跟踪）。目录本身为空，不涉及任何文件。
- 更正一处失效路径引用：`tests/unit/test_ci_contract.py` 实际位于 `tests/contract/test_ci_contract.py`。

### 说明

- **本轮未删除任何 Python/TypeScript/Swift 代码。** 死代码判定执行「三重证据」标准
  （① 静态引用扫描 ② 测试与构建产物引用 ③ 运行时可达性），vulture / ruff 的全部高置信度候选
  经逐条核对后**均为误报**（Typer 装饰器命令、Pydantic 模型与校验器、FastAPI 路由、
  `settings_customise_sources` 签名参数等）。逐条判定见
  `docs/implementation/DELIVERY-CLEANUP-REPORT.md`。
- 新增两份拆分方案（**只写方案，未改代码**）：`docs/implementation/LEGACY-APP-SPLIT-PLAN.md`
  （`webapp/legacy_app.py`）与 `docs/implementation/LEGACY-MAIN-SPLIT-PLAN.md`
  （`web/src/legacy-main.ts`）。
- 保留未删（证据不足）：`providers/feishu/calendar.py:list_events`（有契约测试引用，
  生产路径已改用 `list_events_between`）、4 个空的 `web/src/features/` 子目录
  （ADR 0036 明确保留为空入口边界）、`docs/contracts/`（仍是当前生效的 web 路由契约）。

### 发布

- tag `v0.4.5` → release run
  [#34664646655](https://github.com/SummitYifeng/SummitWorkbench/actions/runs/34664646655)（success），
  产物发布在 <https://github.com/yifeng93/SummitWorkbench-Updates/releases/tag/v0.4.5>。
- **`latest` 已正确指向 v0.4.5**（此前停在 `v0.4.2`；历史 rc 均为 prerelease，stable 通道未被污染）。
- DMG SHA256：`79a64f36871cd0d8a2ac187d7028d21c653970d10e77702b049172f126852d80`
  （49413832 字节；与 `update-feed.json`、`SHA256SUMS`、`release-metadata.json` 四处一致）。
- 构建号为 **19**——由 CI 的 `github.run_number` 决定（`release.yml` 传
  `BUILD_NUMBER: ${{ github.run_number }}`），不是手工 bump 的值。
- 本机从 DMG 安装并启动验证：`CFBundleShortVersionString 0.4.5` / `CFBundleVersion 19`，
  `/api/version` 返回 `server_version 0.4.5 / build 19 / git_revision 749eeef`，六页签可达，
  无 crash loop（本次启动仅 1 条生命周期事件、0 条 error/warning）。
- 已知显示瑕疵（不影响行为）：已发布 DMG 内的指南首页版本标记写作 `build 13`（发布前按
  "build 12 顺延"误估），仓库文档已统一更正为 `build 19`；为避免已发布产物与仓库静态产物漂移，
  未为此重建前端。详见 `docs/implementation/DELIVERY-CLEANUP-REPORT.md` §5.2。
  **该瑕疵已在 `v0.4.6` 修复**（见上文 `[0.4.6]` 的「修复」）。

### 2026-09-12 · 前端拆分收尾与第二台机器接入

#### 新增

- **连接向导支持第二台机器接入**：向导第一步新增「**从另一台 Mac 克隆**」——填私有 HTTPS
  仓库地址、目标文件夹（必须尚不存在）、GitHub 用户名和 PAT，先 `remote/stage` 暂存并核对
  workspace marker（显示工作区短码与兼容性），再 `remote/confirm` 落盘，本机作为 **secondary**
  加入。PAT 只活在 stage 与 confirm 之间：不进草稿、不进 `sessionStorage`、不回显、只写进
  workspace 级 Keychain，仓库历史里也没有。此前这些后端接口（P0-09C）**没有任何调用方**，
  新机器只能靠手工配置接入。入口只在空安装向导出现（完整 app 里没有这些受限路由）。

#### 修复

- **设置页恢复「移除此 Mac 上的工作台」入口**：`data-action="profile-remove"` 的派发分支与动作
  实现一直都在，但 `cb1bd34` 清理旧设置页时把唯一的渲染入口一并删掉了，此后本机 profile
  **无法从界面移除**（只能删目录）。现在每个工作台条目都能移除，**包括当前工作台**
  （后端早已支持并返回 `restart_required`，移除当前工作台后按提示重启即生效）；提示明确写出
  只影响这台 Mac——vault、远端仓库与 Keychain 凭据都不动。同时补上该请求缺失的
  `Content-Type: application/json` 头（与其它设置写请求一致），并把它从"只有派发分支"变成
  **契约测试锁定渲染入口**（此前正是这类"有 handler 无入口"的空洞逃过了守卫）。

#### 变更

- **前端整体拆分完成**（`docs/implementation/LEGACY-MAIN-SPLIT-PLAN.md` Steps 0–9）：
  `web/src/legacy-main.ts` **3395 → 964 行**，收敛为纯组合根（类型契约、跨域状态、`render()`、
  全局 click/submit 派发、`refresh*`、`mountLegacyWorkbench`），其余全部归入 `features/*`
  或既有 `src/{api,core,lifecycle}`。**行为不变**：不改文案、DOM 结构、请求路径与请求头、
  键盘/焦点行为；路由契约快照与每步全量门禁均通过。
  - 与计划的偏差已记录并给出实测依据（同文件附录 C）：刷新编排取 §4.3 方案 B；
    400–500 行目标实测不可达（派发器本身 340 行 / 57 分支，下限约 750 行）；
    §3.1 把簇 5 放到 `lifecycle/*` 在 §4.1 分层下不成立（会形成 L0 → features 反向依赖）。
  - 前端测试脚本从 7 个增至 14 个，全部布局无关。

#### 测试与验收

- **同步冲突恢复请求链**改为可执行断言：stub `fetch` 驱动
  `详情 → 逐文件选择 → 选择校验 → 临时预检 → 确认恢复`，锁定"选择校验请求不得携带 `confirmed`"、
  预检 `confirmed: false`、只有确认才 `confirmed: true`、`opaque-binary` 只能 `preserve-both`、
  未选完时预检按钮禁用；并做过变异验证（给校验请求加上 `confirmed` 会被抓出）。
- **A6 状态更正**：双设备冲突恢复**已在 build 29 / `697c239` 双机验收通过**（证据见
  `docs/archive/acceptance/P2-02-BUILD-25-STUDIO-AIR-RUNBOOK.md` 与 ADR 0043），当前待办是把
  结论重新锚定到本 build。实测差异：同步后端与 11 条 `/api/sync/*` 契约自 build 29 起**逐字节
  未变**，前端唯一用户可见变化是 `ee561f5` 的"读取失败不静默隐藏保护态"。复跑范围据此缩减为
  差异点抽查，见 `docs/acceptance/DUAL-DEVICE-REHEARSAL.md`。
- 本次收尾实测门禁：`tsc` 干净、14 个前端脚本全绿（73 个源文件）、`pytest --cov`
  **931 passed / 1 skipped，覆盖率 83.39%**、ruff / format / mypy / secret scan 全过；
  手动触发 CI 两次（阶段边界与本次功能）均 4/4 job 绿。

### 2026-09-11 · 远端 CI、前端工具链与交付门禁补强

> 远端 CI、前端工具链与交付门禁补强，并产出 build 11 内部包。build 9 的历史产物身份不变。

#### 修复

- 修复 macOS framework 版 Python（python.org 安装包）下的 runtime record 身份误判：framework 构建会
  re-exec 到 `Python.app/Contents/MacOS/Python`，真实进程路径与 `sys.executable` 永不相等，导致
  `_same_server_executable()` 把活着的 server 当作复用 PID，删除活着的 runtime 记录并绕过
  `server_entry.py` 的重复实例保护。现在同时接受 `sys.executable`、`sys._base_executable` 与
  `sys.base_prefix/Resources/Python.app/.../Python` 三个合法镜像，并新增回归测试。
- 修复 `wb review apply` 缺少会议创建器：CLI 只注入 `task_creator`，面板则同时注入
  `task_creator` 与 `meeting_creator`，导致 `feishu-meeting` 落点在 CLI 下必然失败
  （`缺少飞书日历会议创建器`），同一份审批页只能在面板应用。已补齐并让两个 creator 都透传
  `operation_id`，附回归测试。
- 修复 `scripts/install-macos-app.sh` 的自我误报：旧启动器探测对整条命令行做正则匹配，会匹配到
  探测自身的 `awk` 进程（其命令行含同一 target 字符串），使安装随机失败在「检测到运行中的
  SummitWorkbench」。改为对 `comm`（可执行文件路径）做精确相等比较。
- 修复 `web/scripts/*.mjs` 的幽灵依赖：6 个脚本直接 import `esbuild` 但清单从未声明，一直靠
  Vite 提升；Vite 8 移除 esbuild 后全部 `ERR_MODULE_NOT_FOUND`。已显式声明并加契约测试。
- 修复审批创建的任务**没有负责人**：飞书只把调用者记为 `creator`，不会据此设为 `assignee`，
  因此任务虽在「全部任务」可见，却**永远不会进入用户自己的任务清单**——而今日简报正是用
  `list_tasks` 读这份清单，导致「审批批准 → 建任务」的闭环在最后一步断掉。现在新建任务带上
  `members[{role:"assignee"}]`（当前授权用户），CLI 与面板两处调用点均已接入，并加契约测试；
  真实验证为「我的任务」3 → 4 条，且修复前建的那条仍不在列表（前后对照）。
- 修复 10 MiB 逐字稿上限**只覆盖 web 路径**：CLI 的 `wb meeting import` / `backfill` 此前完全
  没有体积检查，能把任意大文件直接送进模型（实测 12 MiB 文件预估 419 万 input token、约 4.24 CNY）。
  现在 `MAX_TRANSCRIPT_BYTES` 是 workflow 层的单一真源，两条路径共用同一数值；CLI 会显式列出
  被跳过的文件而不是静默丢弃。修复后同一目录的预估 token 从 419 万降到 12。

#### 构建与交付

- **build 12 内部包（当前装机版本）**：`0.4.4` / build `12` / arm64 / `INTERNAL-DEV`，前端
  `v2026.09.11-e8ed6f7-6e6e0c91`；DMG SHA-256
  `71958a14f72caccc0822ff839ba854538bcecde001ae1863b777abade35dd1c0`。包含本版全部修复
  （runtime record、安装脚本自我误报、CLI 会议创建器、飞书任务 assignee），已装机替换 build 11。
  产物目录 `dist/releases-local-v0.4.4-build12/0.4.4/arm64/`。
- build 11 内部包（历史留档）：`0.4.4` / build `11` / arm64 / `INTERNAL-DEV`，前端
  `v2026.09.11-1abcebe-6e6e0c91`；DMG SHA-256
  `da7ae2ab7685da5f53e8509b9c85cd4cd97a410df87e8c650ed707f8bcec972e`。它从 `1abcebe` 构建，
  **不含其后的四项修复**（尤其是面板侧任务 assignee），不要再用作验收基线。
- build 11 之前完成 D/E 真实写回验收（真实模型 + 真实飞书）：导入与幂等重跑、零写入预演、
  `project-main` / `feishu-task` / `feishu-meeting` 三种落点写回与回读、部分失败可见性。
  证据与发现（CLI meeting creator 已修、任务 assignee 已修、10 MiB 上限只在 web 层未修）见
  `docs/acceptance/OPEN-VERIFICATION-ITEMS.md` §K。验收用的合成数据已清理：vault 回退到
  `8dba623d`，飞书上两条测试任务已删除（测试日程未删，见 §K）。

- 仓库迁移到组织 `SummitYifeng/SummitWorkbench`：Actions 分钟数按**仓库所有者**计费，组织 Team 额度
  对个人账户名下的仓库不生效；迁移后远端 CI 恢复，secrets、`release` environment 与 releases 均保留。
- `packaged App smoke` 接入 CI 的 arm64 构建矩阵（`WB_PACKAGED_APP`），不再只在本地执行。
- 两个 workflow 的 action 升级到 node24 大版本（`actions/checkout@v7`、`actions/setup-node@v7`、
  `actions/upload-artifact@v7`、`astral-sh/setup-uv@v10.1.0`），项目 Node 工具链由 20 升到 24。
- 远端 CI 全绿：workflow lint、macOS arm64 contract、macOS x86_64 负向 contract、quality-gate
  （844 passed / 1 skipped，覆盖率 81.19%）。
- **前端工具链升级**：`vite 6.4.3 → 8.3.0`（打包器由 esbuild/Rollup 换成 Rolldown）、
  `typescript 5.9.3 → 7.0.2`、`esbuild 0.25.12 → 0.28.2`（Vite 8 声明
  `peerOptional esbuild ^0.27||^0.28`，故 esbuild 必须随 Vite 大版本同步抬升）。
  产物 `v2026.09.11-6ff10a6-6e6e0c91`，JS 143.18→139.55 kB、CSS 35.07→34.86 kB。
  合并前在真实浏览器完成 A/B/C/F/G 验收（含 C 的弹层初始焦点：两分支各 3 次机器测量一致），
  并以无头 Chrome 比对 Vite 6/Vite 8 产物 DOM 逐字相同。
- **修复前端脚本的幽灵依赖**：`web/scripts/` 下 6 个脚本直接 import `esbuild`，但清单从未声明它，
  一直靠 Vite 提升；Vite 8 移除 esbuild 后全部 `ERR_MODULE_NOT_FOUND`。已显式声明，并新增契约测试
  `test_frontend_scripts_only_import_declared_packages` 防止复发。

## [0.4.4] - 2026-09-10

> UI/UX 优化与交付稳定性维护版：初始界面方案于 2026-09-08 落地，build 9 于 2026-09-10 完成本地打包和真实工作区 Computer Use 验收；GitHub Actions 因账户付款或额度问题未启动。

- 今日简报置顶，快速捕捉并入简报快捷行，会议导入收进抽屉；宽屏简报采用两栏布局，窄屏自动单列。
- 设置页改为工作区、AI 模型、飞书、自动化四张白话卡；高级功能默认折叠，连接成功显示绿色 ✓。
- 新增可跳过、可恢复的“工作区 → AI 模型 → 飞书”三步向导、模型现场验证、飞书一键授权回调及设置页重新进入口。
- 保留 workspace-scoped 凭据、审批/同步保护、旧入口与数据格式兼容；刷新 Web route contract 并提交生产静态产物。
- 兼容旧版飞书凭据：首次读取时安全迁移到当前 workspace scope；设置页读取同一作用域的授权状态，成功统一显示绿色 ✓。
- 原生 App 生命周期加固：仅接管自身且身份匹配的服务；PID 被系统复用或运行记录过期时忽略旧记录，避免误判 crash loop。
- 修复网页端“现在生成/重新生成”：生成成功后显式提交并推送本次产生的简报、快照、用量和授权状态文件，绝不使用 `add -A` 带入其他用户改动。
- build 9 arm64 `INTERNAL-DEV` DMG 已通过离线发布验证和实际 vault 交互验收：`v2026.09.10-df4ba1f-1cb9c2eb`；DMG 位于 `dist/releases-local-v0.4.4-brief-fix-df4ba1f/0.4.4/arm64/`，SHA-256 为 `d6104112cfce8598457c04126d355112d85e3957bb07bf6268f4a9411adbcdc8`。
- 本地门禁：Ruff、格式检查、mypy、`pytest tests/unit`（762 passed，5 warnings）、route contract（51 passed，1 warning）、`npm run test:frontend`、生产构建和 packaged smoke 均通过；远端 CI 当时未启动，不在本节宣称 CI 全绿（后续已于 2026-09-11 跑通，见上文 `[0.4.5]` 的「2026-09-11 · 远端 CI、前端工具链与交付门禁补强」）。

## [0.4.3] - 2026-09-07

> P1-07D 已完成：Studio + Air 双设备真机验收闭环（同一候选包 build 23，SHA-256 见
> `release-metadata.json`），build 24 已在 Studio 与 Air 完成覆盖安装与增量冒烟，进入 P2-01B 的前置门已解除。

- 产品范围已重新确认：当前交付边界止于 P2-02。M3（带上下文启动与会话收尾）和 P2-03（组织级
  OAuth Broker/新增云服务）均不实施；后续仅处理现有功能的缺陷修复、稳定性维护和明确提出的增量需求。
- 当前实际使用能力保持不变：DeepSeek Flash 用于会议结构化、快速捕捉分类、简报/复盘与问答；
  `wb ask` 先按项目、路径、frontmatter 和全文在本地 Markdown 中确定性召回，再把选中的来源交给
  云端模型回答。会议审批结果可写回项目主笔记或项目 inbox；快速捕捉先进入全局 inbox 并保留项目标签。

- P2-01B 已完成：仅对既有 thread activity 接入 `shadow-read → dual-write`、确定性投影对比、
  差异诊断、一致性报告与回退开关；不迁移 inbox、会议决策或项目正文。
- P2-02 已完成：build 29 在 Studio + Air 通过双机退出验收，覆盖 Markdown、未知视图、binary、
  追加 event、已登记视图重建、脏工作树拒绝、脱敏审计、普通 push 与最终同 HEAD；P2-02 与
  ADR 0043 均已标记 `[x]`。第一轮审计计数为 `4/1/1`，第二轮为 `5/0/0`，最终 revision
  为 `ec00260`，双方 clean 且 ahead/behind `0/0`。
- build 28 现场追加 dual-write 时发现打包服务只提交 event、遗漏同事务的 legacy Markdown；已在
  `run_local_mutation` 增加主返回路径兜底并补 Dulwich 回归测试，build 29 重新打包，P2-02 现场验收
  改用 build 29。
- build 29 双机主路径与保护分支均已通过：Air 普通双父恢复 `c95b6c1`、脱敏审计 `8a6a543`，
  事件/登记视图自动处理计数为 `4/1/1`；脏工作树现场返回 `current_worktree_dirty`，清理后
  产生双父恢复 `af662d5` 与审计 `ec00260`。隔离验收副本验证审计失败仍保持 `committed` 并
  报告 `recovery_audit_failed`；Studio 快进后双方同 HEAD 且 clean。
- 当前主线质量门独立复核：`826 passed, 1 skipped`，覆盖率 `82.15%`，另有 packaged App smoke
  `1 passed`；ruff、格式检查、mypy、前端契约与生产构建、依赖锁、release 验证和 secret scan 均通过。

- P2-02：未知 `_views/**` 不再误判为可自动重建；改为人工 `preserve-both`，保留确定性的
  `.remote` 副本，并在保护态 UI 只展示安全选项；已定义的 thread activity 视图继续在
  临时目录确定性重建。
- P2-02：恢复双父提交成功后，脱敏审计写入失败会单独报告为审计失败，不再把已完成的
  恢复误报为可重试失败；前端同时区分恢复提交、普通同步与审计状态。

- build 24 内部 arm64 DMG 已由干净提交 `ac97db4aebb53147a394d83a34d9ed978d42b91e` 生成并通过 App/DMG 离线验证；产物 `dist/releases-build24/0.4.3/arm64/SummitWorkbench-0.4.3-arm64-INTERNAL-DEV.dmg` 的 SHA-256 为 `ef02907d637be755fe825d60b58fea8e1f67fe47cebcf03e782d2caf6f0e6590`。Studio 与 Air 增量检查均确认 build 24、HTTPS remote、preflight、基础同步、secondary profile、简报/周报友好跳过及零写入。

- 修复 DulwichGitBackend `fetch()`/`push()` 传 URL 而非 remote 名，导致
  `refs/remotes/origin/*` 永不更新：push 成功后 `ahead/behind` 与 `pending_wb_commits`
  不再永久停留在 1（`local-ahead` 假象），状态机不再在 ready / local-ahead 之间回退。
- 修复打包 App 从 Finder/LaunchServices 启动时没有代理环境变量、dulwich 直连
  `github.com` 被阻断的问题：无 env 代理时回退 macOS 系统代理（`scutil --proxy`），
  TLS 校验保持 `CERT_REQUIRED` + bundled CA，绝不关闭校验。
- acceptance preflight 报告完整 build identity（`version/build/frontend_build/git_revision`）；
  fetch 失败输出稳定脱敏码（auth/tls/certificate/proxy/credentials-unavailable/network/
  backend）与 host/credential/CA/proxy 诊断，不含 PAT、完整 URL 路径或本机路径。
- 新增 `GitCertificateError` / `GitProxyError` / `GitCredentialsUnavailable` /
  `GitBackendRuntimeError` 与 `classify_git_error()` 稳定错误码，区分证书、代理、凭据缺失、
  后端运行时与网络不可达。
- Air「连接已有工作台」向导新增 PAT 输入：clone 使用短生命周期 credential_resolver，
  确认后才写入 workspace-scoped Keychain；新增 `connect-remote` 预检流，允许尚未存在的
  clone 目标目录；confirm 回填 profile 的 `git_remote_url`。PAT 绝不进 draft、日志或 URL。
- secondary 的自动化「立即运行」与手动简报/周报生成改为友好跳过提示（`200` + `ok=true`），
  不再显示红色 `ApiError`；写入仍被 automation 角色门控跳过，绝不执行。
- 同步发现不再把 onboarding 遗留的 `.summit-workbench-remote-*` staging 目录当 workspace
  仓库同步。
- 质量门：`823 passed, 1 skipped`；ruff check / ruff format / mypy 通过；build 23 打包集成与
  TLS 诊断通过。Studio（automation-primary）与 Air（secondary）用同一 DMG 完成 remote
  preview/apply、schema 迁移、preflight 全 PASS、Studio↔Air 双向同步、Air 离线写入恢复、
  双端离线冲突进入 `diverged-protected`（不 force/reset/rebase/stash、不丢数据）。

## [0.4.3-rc.5] - 2026-09-06

- 原生 App 重启时可根据 runtime record 与精确 server 可执行路径识别并终止自身遗留进程；
  未知进程仍不会被接管或终止。

## [0.4.3-rc.4] - 2026-09-06

- 修复设置中心 remote preview/apply/rollback 请求缺少 JSON `Content-Type` 导致后端拒绝的问题。

## [0.4.3-rc.3] - 2026-09-06

- 允许旧 schema 的只读工作区执行受控 remote preview/apply/rollback，打破“迁移要求 HTTPS、
  HTTPS 转换又被只读门阻止”的循环；其它写入仍保持只读保护。

## [0.4.3-rc.2] - 2026-09-06

- 候选 release 的 feed 与 DMG URL 改为按 tag 自动推导，继续使用 draft/prerelease 且不更新
  `latest`。

## [0.4.3-rc.1] - 2026-09-06

> 候选版本，尚未稳定发布；等待一次 Studio + Air 双设备真机验收。

- P1-07D：生产同步正式限定 HTTPS remote；SSH/scp-style remote 明确返回
  `remote_scheme_unsupported`。
- 设置中心新增可预览、可回滚的 GitHub SSH → HTTPS 转换事务与脱敏 acceptance preflight。
- 修复 Dulwich clean-worktree 判定，补充 ignored directory、未跟踪文件、已跟踪删除和双设备
  schema/sync/divergence 回归。
- 候选 release 使用 draft/prerelease 渠道，不更新 `latest`；公开更新仓库只提供完整性，不
  提供保密性。

## [0.4.2] - 2026-09-06

修复 macOS 自包含 App 首次创建 workspace 时找不到 PyInstaller 内置 vault 模板的问题；
补充 packaged App 的真实 workspace 创建集成测试。

## [0.4.1] - 2026-09-04

维护加固发布（稳定性审计 P0/P0'/P1，ADR 0027）。核心问题不变（外置执行管理层 + 第二大脑）；本版收掉三类真问题：**写路径并发丢更新、全库无撤销、停滞点名被机器活动刷失明**。

### 修复

- **写路径并发加固（P0）**：全库所有「读文件 → 变换 → 整文件原子重写」的 RMW 原语（审批页裁决/批量/修改与 refresh、inbox 与项目档案追加、set_project_status、当日笔记与周复盘、当日快照镜像、线程日志/产物、项目建档/激活/归档、review sweep、审批页状态收口）整体放入工作区锁（workspace_lock(vault_dir.parent)，与 publish_brief / sync 同一把 .wb.lock；**锁只包文件临界区，绝不跨 LLM/网络调用**；锁忙对用户可见——CLI 输出「工作区忙，稍后重试」并 exit(1)，面板返回可见失败）。裸 write_text 全量改 atomic_write_text（当日笔记可能含用户锚点外手写内容，断电/kill 不再留半截文件）。审批 apply_meeting_review 收尾改**乐观合并**（P0-5）：apply 执行外部写回期间用户在审批页的并发勾选/编辑不再被整页重写吞掉——收尾重读最新页，只移除本次执行且最新页中未变的候选，被并发改动的候选留在页上（账本幂等，下次 apply 清理不重复执行）。幂等账本（_signals/review-actions/log.jsonl）改逐行 Pydantic 容错读（ExecutionRecordRow），一条半截行只告警并隔离进 .quarantine，不再让 apply 幂等判定整体崩溃。线程日志/产物序号分配与落盘同锁且写前重查目标存在，并发写入不再算出同一序号静默覆盖。
- **系统写回自动留痕 + 面板撤销（P0'）**：每次系统侧写回成功后自动 git 提交（**显式路径**、绝不 add -A、消息带 wb: 前缀、非 git 仓库优雅降级不抛错、失败转可见状态不阻断写回）——覆盖面板捕捉（inbox）、推进日志/产物与关联档案、状态确认、审批应用（写回目标 + 审批页 + 审计归档）、项目建档/激活/归档/改名、任务完成/编辑与会议编辑（当日快照镜像）、逐字稿导入，以及 wb review sweep --apply（CLI 顺带）；launchd brief/weekly 沿用既有 publish，不重复提交。顶栏新增 **「↩ 撤销」**：最近 N 次 wb: 自动提交（含触碰文件）→ 单提交 before/after 差异预览 → 一键还原（等价 git revert，只作用于 vault 文件；**飞书侧已产生的副作用——已建任务/会议、已完成状态——不可撤销**，按钮旁与确认弹层文案明示；目标文件有未提交人工改动时拒绝还原）。新增 repositories/autocommit.py 与 GET /api/undo/history、GET /api/undo/diff、POST /api/undo/revert。
- **停滞信号语义修复（P1）**：档案 frontmatter updated 收窄为**实质更新**，只在建档/激活/归档/改名与用户显式确认的状态写回（threads/state）时刷新；日志/产物等机器活动改刷新新字段 **activity_at**（活动痕迹，读侧经 meta_date_iso 归一，project_scan / project_view / /api/state 载荷与前端同步）。首页线程卡「最近活跃」读 activity_at（缺省回退 updated）；「>14 天未更新」提示与周复盘停滞点名继续读 updated——AI 收尾的高频自刷新不再让停滞点名失明。

### 质量

- 新增并发写（T1–T6：并发裁决/apply 乐观合并/inbox 追加/线程序号/简报×完成镜像/坏账本行）、自动提交与撤销（U1–U4）与停滞语义（S1/S2）测试，另加**跨进程互斥**集成测试（两个真实子进程并发写当日笔记 + 快照，无交错）；全套 **514 项全绿**（较 491 净增 23）。ruff + format + mypy strict（200 文件）+ 前端 strict TS + Vite 构建通过；桌面 App 已重新打包装机。M3（带上下文启动与收尾）仍是下一步。

## [0.4.0] - 2026-09-03

发布版。核心问题不变（外置执行管理层 + 第二大脑），v0.4.0 完成需求再梳理结论 R2-A+ 的落地：**业务线程 = vault 一等公民**——知识线程（FinanceOps / CoachFinance / EnrollmentProduct / ERPExplore 等试点）不再依赖 Work 文件夹与 git，以 `_vault/projects/*.md` 档案建档即入工作台；线程有自己的推进日志（work-log）、AI 产物（thread-doc）、收件箱与**线视图**（档案区块 + 时间线聚合），信号（下一步 / 阻塞 / 未闭环跟进 / 长期无更新）进入晨间简报与**周复盘停滞点名**，第二大脑可按线程检索。桌面 App（LSUIElement）补上原生文件选择与编辑快捷键。质量门 491 项全绿。M3（带上下文启动与收尾）仍是下一步，未在本版开始。

### 新增

- **知识线程 = vault 一等公民（P0）**：线程**无需 Work 文件夹 / git**，`POST /api/projects/create` 直接在 `_vault/projects/` 建档（`type: project-main`）即入工作台；registry 全集（`scan_all_projects` = 文件夹项目 + 线程档案合并）统一进首页推进卡、「项目」页与审批「目标项目」建议下拉；下划线前缀目录（`_vault`、`_transcripts-inbox` 等）是系统内部目录，不进项目视野。已建档 4 条试点线程（FinanceOps / CoachFinance / EnrollmentProduct / ERPExplore，含中文别名解析）。归档/恢复只动档案 frontmatter，文件夹与 git 零触碰。
- **审批路由扩展（P0，承接 L22）**：审批「目标项目」下拉与写作候选现支持已建档的**知识线程**；新落点 **「跟进事项」**（`project-followup`）把他人行动项写成主档案 `## 跟进事项` 下的**待闭环责任记录**（`- [ ] ` 复选框，人工勾选闭环，不进本人待办）；老档案首次写回自动补区块；知识线程的 inbox 落 `_vault/inboxes/<project>.md`（`type: project-inbox`），仓库项目仍写文件夹内 inbox。
- **✎ 推进日志（P1）**：线程/项目卡与线视图内「✎ 日志」粘贴推进文本（与谁沟通、定了什么、下一步），可勾选**多个线程/项目** → AI 消化为摘要（`prompts/log-digest.md`：摘要/涉及人/类型/下一步/决策）→ 写 `_vault/logs/YYYY-MM-DD-NNN.md`（`type: work-log`，`projects:[...]` 多线程 scope）；模型不可用只存原文（`status: draft`），绝不丢。
- **存产物（P1/P3）**：视图内「存产物」把与 AI 长对话产出的**阶段总结 / PRD / 背景包 / 时间线**全文存进所选线程（`_vault/artifacts/<project>-NNN.md`，`type: thread-doc`，frontmatter 自动命名 + `title/summary/kind` 摘要索引），之后第二大脑按线程可检索；产物弹窗支持 **📄 选择本地文件**（.md/.txt，`runOpenPanel`）与**拖放**（全环境可用），存量文档零成本收进线视图；勾选「同步更新主档案当前状态」可把产物摘要一键写为档案「当前状态」草案（`POST /api/threads/state`，显式确认后写回并刷新 `updated`）。
- **线视图（P2）**：点项目/线程名打开 = 档案区块（当前状态 / 下一步 / 阻塞 / 跟进事项 / 决策记录，跟进带「N 条待闭环」徽标）+ **时间线**（该线程的 logs / artifacts / meetings 按日期聚合，一屏看全）；视图内可直接「✎ 日志 / 存产物 / 刷新」。日志或产物入库自动刷新关联档案 frontmatter `updated`（首页卡「更新 X」即时）。
- **线程信号进简报与周复盘（P2/P3）**：线程「下一步」进今日简报**主线推进**、「阻塞」进**防止停摆**、未闭环跟进聚合为「跟进 X：…（共 N 条）」主线推进；已归档线程不产生信号。线程卡 >14 天无更新显示「⚠ N 天未更新」；**内容停滞检测进周复盘**——线程距复盘周截止日 >14 天无更新（`THREAD_STALL_DAYS`，与卡片同口径）且档案仍有阻塞/未闭环跟进时，周复盘「停滞项目」点名并派生「推进停滞项目 X」提议。
- **项目显示名（P3）**：`POST /api/projects/rename` 写档案 frontmatter `title`（显示名，不改规范 ID / 别名 / Work 文件夹 / git）；卡片/项目页/审批建议/第二大脑范围/日志与产物选择器统一显示显示名（不同于档案 ID 时标注 ID）；线视图内「✎ 显示名」行内改名。
- **桌面 App 原生壳（LSUIElement）**：`runOpenPanel`（自绘 NSOpenPanel）解决 WKWebView 在 accessory 应用下 `<input type="file">` 不弹系统面板；补最小「编辑」主菜单（⌘V 等路由第一响应者）；窗口焦点交 webView。

### 修复

- **frontmatter `updated` 读取归一（P3 内容停滞检测依赖）**：建档/写回产生的 `updated: 2026-09-03`（未加引号）会被 YAML 解析成 `date` 对象，`project_scan`/`project_view` 的 str-only 判断会把它当空丢弃 → 新增 `repositories/vault.py::meta_date_iso` 统一归一到 `YYYY-MM-DD` 字符串（str / date / datetime 同值同型），线程卡「更新」、>14 天未更新提示与周复盘停滞判定由此都能读到真实的最后更新时间。

### 质量

- 线程扫描 / 审批落点 / 线视图 / 简报线程信号 / 显示名与状态 / 周复盘停滞检测等新增测试，全套 **491 项全绿**；ruff + format + mypy strict（src 119 文件）+ 前端 strict TS + Vite 构建通过。P0/P1/P2 与 P3 第一批经真机验收并装机（前端 `215658a3`）；内容停滞检测进周复盘（本版代码完成，随本版装机后生效）。

## [0.3.0] - 2026-09-03

发布版。核心问题不变（外置执行管理层 + 第二大脑），v0.3.0 把「工作台 → 飞书」的**双向写回**补全：在 v0.2 只读呈现（读任务/日历进简报）之上，现在可以在工作台**一键完成 / 行内编辑**飞书任务、**行内编辑**日历会议，并能在审批时把会议结论落成**新建日历日程事件**；飞书始终是任务与日程状态的唯一真源，本地只镜像当日渲染快照、vault 简报 Markdown 一字不动。日历权限由只读升级为**读写**（`calendar:calendar`，需重新授权），全部写回端点经真机验证（2026-09-03：建日程 / 改会议标题与起止时间 / 改任务标题与截止 / 一键完成契约修正）。质量门 457 项全绿。M3（带上下文启动与收尾）仍是下一步，未在本版开始。

### 新增

- **工作台内一键完成飞书任务（反向写回）**：v0.2「待办任务」默认只读、完成必须去飞书；现在每行最右新增小圆钮「✓」——点击即 `PATCH` 设置任务 `completed_at`（毫秒时间戳，`update_fields=["completed_at"]`，真机收敛的完成形态）把任务在**飞书侧**标记完成（真源），成功后把当日**渲染快照**镜像一致（该任务从 `task_list` 移除并计入 `completion_list`「最近完成」、引用它的行动候选一并移除，避免以「需要行动」重新出现），前端刷新即消失；任务不在当日快照时完成照常成功（飞书为准）。vault 简报 Markdown 与 Obsidian 阅读体验一字不动。新增 `providers.feishu.complete_task`（FeishuClient 增 `patch`/`delete`，`delete_task` 供校验清理）、`repositories.signal_snapshot.mark_task_completed`、`POST /api/tasks/complete`（`TaskCompletePayload`）；快照镜像按 `task_id`↔`feishu-task:{guid}` 大小写不敏感匹配，旧格式快照零写入降级。前端 `web/src/brief-card.ts` 待办行渲染 + `main.ts` 点击处理 + CSS（`.bf-done` 小圆钮）；使用指南同步（「今日」页与 FAQ）。质量门新增 7 项测试（Feishu PATCH 契约、快照镜像仓储、`/api/tasks/complete` 端点含失败/缺 id/无快照分支），全套 **440 项全绿**；ruff + format + mypy strict 通过（顺带修复 mypy 2.3.1 下既有 6 处严格类型报错：`webapp/api.py` 简报载荷 3 处与 `test_brief_domain.py` 3 处）。
- **审批新增「新建会议」落点 + 今日任务/会议行内编辑（双向写回飞书）**：审批候选在「修改」里可选落点 **「新建会议」**（`RouteTarget.FEISHU_MEETING`），并填**开始/结束时间**（结束留空按开始 + 1 小时）；批准并「应用（写回）」即经日历 v4 `POST .../calendars/{id}/events` 在主日历**新建定时日程事件**（标题 = 候选正文，不邀请他人，按候选 ID 审计幂等）；无开始时间或未注入创建器时条目留在审批页并记可见失败。「今日」简报行内编辑：**待办任务行「✎」** 改标题/截止（清空截止 = 移除），**会议行「✎」** 改标题/起止时间——均 `PATCH` 写回飞书本体后镜像当日渲染快照（任务连同其 AI 行动候选同步标题/截止；会议更新标题/展示时间与原始 ts），刷新即生效；会议快照附加演进 `event_id/start_ts/end_ts`（旧快照无键则不显示编辑钮），全量事件不开放编辑。日历写权限：`DEFAULT_SCOPES` 把 `calendar:calendar:readonly` 升级为 **`calendar:calendar`（读写）**，需在开放平台开通并**重新授权一次**后才能真机写回（`wb doctor --online` 可查授权状态）。同时修正一键完成的契约（真机报错驱动、多形态实测收敛）：Task v2 的 `PATCH update_fields` 白名单**不含** `completed`，第三方文档所述 `POST .../tasks/{guid}/complete` 在本租户返回 404；完成正解为 `PATCH completed_at`（毫秒字符串）并列入 `update_fields`（`update_task` 的 `summary/due` 不受影响）。质量门新增 17 项测试（日历创建/更新契约、`update_task` PATCH 契约、`feishu-meeting` actionable 与审批页起止字段往返、apply 经 `MeetingCreator` 建事件与幂等/失败隔离、快照镜像编辑、`/api/tasks/update`·`/api/meetings/update`·审批编辑端点），全套 **457 项全绿**；ruff + format + mypy strict + 前端 tsc 通过。
- **真机核实（ADR 0025，2026-09-03）**：日历/任务写回端点、`update_fields` 契约与日历读写权限经真实飞书数据验证——建日程事件、改会议标题与起止时间（回读一致）、改任务标题与截止（改回原文）、一键完成 `PATCH completed_at` 契约（带 assignee 任务：建 → 完成 → 出现在已完成列表 → 删除，闭环通过）；日历 scope 升级后需重新授权一次（旧 token 不带新权限）。

## [0.2.0] - 2026-09-03

发布版。核心问题不变（外置执行管理层 + 第二大脑），交付面收敛：**用户日常入口 = 原生 macOS 桌面 App 内的本地 Web 工作台**。在 v0.1.0（M0/M1/M2 + 韧性/正式使用前加固）之上完成 Web 工作台产品化、桌面 App 正式化与晨间简报 v2 呈现改版；vault 内简报 Markdown 版式不变（Obsidian 侧与 G1 回归的唯一真源）。质量门 433 项全绿。

### 新增

- **macOS 桌面 App（自包含正式版）**：`.app` 从「Swift 启动器 + 外部 Chrome 面板」演进为**自包含 bundle**——PyInstaller 打包 bundle server + 原生 Swift/AppKit 壳 + **受管 WKWebView 面板**（同源加载本地面板，生命周期受监督：服务就绪握手、面板自动恢复、退出即优雅停服）。构建/安装/自更新原子化（`scripts/build-macos-app.sh` + `install-macos-app.sh`，替换失败自动回滚），前端构建身份（frontend_build + server_instance）随版本握手校验，面板不匹配自动重启自带服务；`wb web` 独立直跑形态保留（读仓库 static，重建+重启即生效）。安装位 `/Applications/SummitWorkbench.app`（桌面副本弃用，详见 `docs/DESKTOP_APP.md` 与 ADR 生命周期方案）。
- **晨间简报 v2（ADR 0024 / PRD L49）**：Web 面板把简报从纯文本清单升级为**日程优先的组件化视图**——会议时间列（过去淡化）+ 待办任务按截止紧迫度排序（今天到期红 / 剩 1–2 天琥珀 / 一周内蓝 / 更远灰，语义色倒计时徽章）；AI 选中的任务行叠加「分类 · 排名」注解并与待办清单**合一**（精确关联 `task_id`↔`feishu-task:{guid}`，消除事实区/行动区重复展示）；清单之外的行动（git 未提交 / 项目下一步 / inbox 积压）单列「需要行动 · 任务清单之外」；AI 提议与最近完成默认折叠带计数。数据经**信号快照附加演进**（`as_snapshot()` 增 `meeting_list/task_list/proposal_list/completion_list/health_reasons` 等明细）由 `/api/state.brief` 下发；旧快照自动回退 Markdown 视图、存量零迁移。前端设计令牌全局换新（Linear 型 zinc + 靛紫主色，深浅双色精修，`web/src/style.css` CSS 变量集中）。`web/src/brief-card.ts` 纯字符串渲染模块 + 静态预览生成（`web/scripts/preview-brief.mjs` → `docs/archive/design/brief-v2-preview.html`）。

- **首页卡片一键归档 + 内置「指南」页签**：首页每个项目推进卡右下角新增「归档」按钮（带确认，归档即离开首页、可在「项目」页恢复）；顶部新增第 5 个页签「指南」，把 `WEB_USAGE_GUIDE.md`（日常使用 + FAQ）在构建时同步内置进前端（`npm run sync-guide`），离线可看，FAQ 折叠为可展开条目——用户日常入口是 Web 面板，不必翻仓库文档。
- **项目推进精选（ADR 0023）**：首页「项目推进」不再平铺 `work_root` 全部文件夹，只显示已建档（`_vault/projects/*.md`）且 `status: active` 的项目；未建档的新文件夹在项目区顶部以邀请横幅出现（逐条「加入工作台 / 归档」）；新增第 4 页签「项目」= 全部项目视图（搜索 + 排序 + 行内加入/归档/恢复）。`/api/state` projects 增 `registered/status` 字段；新增 `POST /api/projects/activate`、`POST /api/projects/archive`（写 `_vault` 档案 status，幂等，校验必须是 work_root 直接子目录）。归档/恢复只动 frontmatter，文件夹与 git 历史零触碰。
- **Web 工作台（SPA）**：`wb web` 由服务端渲染面板升级为「今日工作台」单页应用（Vite + 原生 TypeScript，无组件库；FastAPI 新增 `/api/*` JSON 端点；构建产物存在时 `/` 服务 SPA，否则回退 SSR，旧路由与 CLI 语义完全保留）。
  - 「今日」页：顶部快速捕捉（回车记入全局 inbox）、待确认审批卡片（积压置顶 + 一键跳转）、会议逐字稿拖拽导入区、项目推进卡（未提交/落后/下一步/inbox 积压）、今日简报（未生成时给出空状态引导）、问第二大脑。
  - 「审批」页：即时批准/拒绝/改回 + 原地修改 + 预演/应用弹窗，不再整页刷新；状态 60s 自动刷新。
- **Web 端会议导入**：`POST /api/meetings/import` 拖拽上传 `.md/.txt` 逐字稿 → 复用 `wb meeting import` 链路全自动归档 + 结构化 + 生成审批候选，报告处理/跳过/失败/候选数与预估费用（软预算只提示不阻断，PRD 提醒线语义不变）。
- **快速捕捉智能分类**：新增 `capture` 模型能力位与 `prompts/capture-classifier.md`；`POST /api/capture` 先分类（承诺/想法 + 截止日期，单次调用、8s 超时）再入 inbox，分类以稳定标记写回（`wb-capture-kind/due/project`）；`#项目` 标签本地解析到已建项目，不经模型；模型不可用/超时/输出非法一律按「想法」兜底，录入永不丢数据。
- **通知闭环**：`wb status --notify` 评估出的预算/积压/定时任务告警真正发到 macOS 通知中心（此前只打印到 stdout，launchd 调用时不可见）；`wb web --open` 一条命令：服务未运行时后台拉起，再打开浏览器直达面板。
- **审批批量操作**：「审批」页每个会议分组新增「✓ 全批 / ✗ 全拒」按钮（只作用于该组待确认条目），工具栏新增「一键拒绝过期项」（截止早于今天的待确认条目批量置为拒绝）；待确认条目截止日期早于今天时在元信息里标注「已过期」。后端新增 `POST /api/review/batch`（`repositories.review_edit.set_decisions` 单次解析 + 单次原子重写，未知 ID 幂等跳过）。
- **`wb review sweep` 清理命令**：一键退役测试/旧会议——审批页候选批量拒绝、笔记 frontmatter 置 `ignored`（正文原文保留）、任务状态收口 `ignored`；支持 `--before YYYY-MM-DD` 只清理旧会议，默认 dry-run 零写入（与 `wb review apply` 同款安全姿态）。
- **会议提取门槛收紧**：`prompts/meeting-processor.md` v2→v3——`decisions` 只收已拍板结论，`action_items` 只收「谁、何时前、做什么」明确的承诺；拿不准的一律降级到 `facts` / `open_questions` / `ai_suggestions`，减少审批页噪音。

### 修复

- **入口页禁缓存（根治“点了没更新”）**：`/` 响应加 `Cache-Control: no-cache`——前端每次改版都换带哈希的资源名，若入口 index.html 被浏览器启发式缓存会一直指向旧资源，呈现旧界面/旧标签；现在刷新或重开 App 必取最新入口。
- **弹窗遮罩常驻屏幕（亮条 + 整页变灰 + 点击无效）**：`.modal-backdrop` 的 `display: grid` 覆盖了 `hidden` 属性（作者样式优先于 UA 的 `[hidden]{display:none}`），导致未打开的弹窗遮罩从一开始就铺满全屏——中间的空白弹窗呈「很亮的矩形条」，背后整页被 45% 黑色遮罩压灰，且遮罩拦截所有点击（`closeModal` 因样式覆盖而失效）。已在 `web/src/style.css` 加 `[hidden]{display:none!important}` 防御规则并重建前端产物。
- **程序坞图标无限弹跳 / 打开报「无响应」**：`.app` 主程序原本是 bash 脚本，常驻进程从不向系统报告「启动完成」——前台形态 Dock 图标无限弹跳，改 `LSUIElement` 后台形态后 macOS 又报「不能打开…没有响应」。根治方案：主程序换成**原生 Swift/AppKit 启动器**（`scripts/summit_launcher.swift`，构建时 `swiftc` 编译），注册正常的应用生命周期；`LSUIElement=true` 不占 Dock，打开/退出全部由原生进程管理（拉起 `wb web` 子进程 + 打开 Chrome 面板窗口，周期探测 `/api/state`，服务停止即自动退出）。退出面板用网页顶栏「退出」按钮 → `POST /api/shutdown`（带 `X-WB-Shutdown` 自定义头防任意网页误关，跨站预检被无 CORS 配置拦截）优雅停服并关窗。（该「启动器 + Chrome 面板」形态随后被**自包含原生 App（受管 WKWebView）**取代：删除 `scripts/summit_launcher.swift`，`.app` 直接烘焙 bundle server 与面板，见上方「macOS 桌面 App（自包含正式版）」条目。）

### 构建

- 前端源码在 `web/`（`npm install` + `npm run build`），产物打进 Python 包 `src/summit_workbench/webapp/static/`，`wb web` 开箱即用；开发模式 `npm run dev` 经 Vite 代理直连本机 `wb web`。

### 质量

- 项目精选（ADR 0023）补齐单测：建档状态读写与幂等、`ProjectState` 分类（新/归档）、`/api/state` 字段、activate/archive 端点（含非法名/越界/幂等），全套 **374 项全绿**；ruff + format + mypy strict 通过（新增 Web API / SPA 测试见 `tests/unit/test_webapi.py`、`test_project_registry.py`、`test_brief_repositories.py`）。
- 新增 14 项 Web API / SPA 测试（`tests/unit/test_webapi.py`）与 2 项 `/api/shutdown` 测试，全套 389 项全绿；ruff + format + mypy strict 通过。
- 批量裁决（`set_decisions`）、`/api/review/batch`、`wb review sweep` 补齐单测，全套 397 项全绿；ruff + format + mypy strict 通过。
- 晨间简报 v2（ADR 0024）补齐快照附加演进与 `/api/state.brief` 契约测试（`test_brief_domain.py` / `test_webapi.py`），全套 **433 项全绿**；ruff + format + mypy strict 通过；前端 strict TS（tsc --noEmit）+ Vite 构建通过，预览页 headless DOM 抽查确认。

## [0.1.0] - 2026-09-02

首个发布版。M0 / M1 / M2 全部完成并经真实数据/真机验证，质量门 360 项全绿。

### 新增
