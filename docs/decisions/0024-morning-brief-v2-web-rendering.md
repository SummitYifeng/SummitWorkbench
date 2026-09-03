# ADR 0024 · 晨间简报 v2——Web 面板组件化日程视图（快照附加演进 + 全局设计令牌换新）

- 状态：✅ 已实现（离线全绿：ruff + ruff format + pytest 433 项；strict TS 构建通过；DOM 渲染抽查与真实数据预览确认）
- 日期：2026-09-03
- 里程碑：v0.2.0 · 晨间简报 v2（对应 PRD 决策台账 L49）
- 依据：用户对本地面板「观感一般，尤其晨间简报——会议/待办/需要行动都是 plain text」；经三轮选择题对齐呈现方案（详见本 ADR「决策」节）

## 背景与问题

`wb brief` 产出的简报正文是确定性 Markdown（`workflows/brief/render.py`），Web 面板把 `_vault/daily/YYYY-MM-DD.md` 锚点区块经 `mdToHtml` 原样渲染：会议、任务、行动全部是同一字号、同一字重的圆点列表；分类方括号、截止括号、状态 emoji、依据全部内联在一个长句里——元数据没有分层编码，扫读成本高，且「需要行动」与「待办任务」两区大量重复（同一条飞书任务既列在事实区又在行动区）。

后端其实一直持有干净的结构化对象（`domain.brief.Brief`：category / evidence / due_date / project / source_ref / task_id 全部现成），但 `/api/state` 只下发 Markdown 字符串，把数据降维成了文本——这是改版的杠杆点。

## 决策（三轮选择题结论）

1. **数据通路：结构化快照附加演进 + 前端组件化**（用户采纳推荐）。`/api/state` 增加结构化 `brief` 载荷；数据源是既有**每日信号快照**（`_vault/_signals/YYYY-MM-DD.json`，ADR 0019 版本化机制内）——`Brief.as_snapshot()` 附加 `meeting_list / task_list / proposal_list / completion_list / health_reasons` 与行动条目 `title/due_date/detail` 字段（**纯附加**，计数键与旧键原样保留，老读者不报错）；`webapp/api.py::brief_payload` 把快照转前端载荷；**旧快照（无 `*_list`）返回 None，前端自动回退既有 Markdown 视图**——存量数据零迁移，重新生成一次当日简报即写入新快照。
2. **vault Markdown 一字不动**：渲染层（`render.py`）与每日笔记版式不变，Obsidian 阅读体验与 G1 回归（同输入同输出）不受影响；Web 呈现与 vault 版式解耦。
3. **信息架构 = 日程优先（用户修正，推翻「行动置顶」初案）**：任务和日程是晨间第一眼；「需要行动」不再是独立大字区，而是**与待办清单合一**——AI 选中的任务行叠加「分类 · 排名」注解 chip；精确关联靠 `task_id` ↔ 行动 `source_ref` 的 `feishu-task:{guid}`（`TaskFact` 补 `task_id` 字段，采集层透传飞书 guid，不做标题猜测）。真正在清单之外的行动（git 未提交 / 项目下一步 / inbox）才单列「需要行动 · 任务清单之外」次级区。
4. **组件形态**：会议=时间列对齐紧凑清单（过时会议淡化）；任务=截止语义色 + 倒计时徽章（今天红 / ≤2 天琥珀 / ≤7 天靛紫 / 更远灰，无截止占位对齐）；提议与最近完成默认折叠为带计数入口。
5. **全局设计令牌换新（Linear 型）**：`web/src/style.css` 的 CSS 变量集中换新——zinc 中性底 + indigo 主色（呼应 logo），浅色为主 + 深色精修（跟随系统）；组件级重构只做简报，其余页签随 tokens 自动换肤。
6. **范围**：本期只读展示；「打勾完成 / 点依据跳转」涉及执行系统写回（飞书）与文件打开，留待后续（PRD 写回需确认的语义不变）。

## 落地位置

- 领域/快照：`src/summit_workbench/domain/brief.py`（`TaskFact.task_id`、`as_snapshot()` 附加键）、`workflows/brief/collect.py`（透传 guid）
- API：`src/summit_workbench/webapp/api.py`（`brief_payload`）、`webapp/app.py`（`/api/state` 新增 `brief`）
- 前端：`web/src/brief-card.ts`（纯字符串组件渲染，无 DOM 依赖）、`web/src/main.ts`（接入 + 旧快照回退）、`web/src/style.css`（tokens + v2 组件样式）
- 预览/验收：`web/scripts/preview-brief.mjs` → `docs/design/brief-v2-preview.html`（真实当日数据 + 状态示例，headless DOM 抽查通过）
- 测试：`tests/unit/test_brief_domain.py`（快照附加演进断言）、`tests/unit/test_webapi.py`（`/api/state` 结构化载荷 / 旧快照回退）

## 验证

- 质量门 433 项全绿（ruff + ruff format + pytest）；`web` strict TS + Vite 构建通过。
- 真实 vault 重新生成当日简报后，`/api/state.brief` 返回 2 会议 / 6 任务（各带 task_id）/ 5 行动；预览页 DOM 抽查确认任务按紧迫度排序、注解 chip 与截止徽章位置正确。
