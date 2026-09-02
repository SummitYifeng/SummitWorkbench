# ADR 0023 · 首页「项目推进」精选清单 + 「全部项目」页（Web 工作台规模）

- 状态：✅ 已实现（离线全绿：ruff + ruff format + mypy --strict + pytest 374 项）；手测清单见「验收」节，待 `wb web` 复核
- 日期：2026-09-03
- 里程碑：v0.2.0 · Web 工作台扩展
- 依据：用户诉求「本地项目文件夹到 100 个量级后，工作台不能平铺 100 个项目」；承接 ADR 0011
  的项目注册表（`_vault/projects/*.md`）与 v0.2.0 Web 工作台

## 背景与问题

v0.2.0 Web 工作台「今日」页的**项目推进卡**当前来自 `scan_projects()`：
`repositories/project_scan.py:127` 把 `work_root` 下**所有直接子目录**（仅跳过 `_vault`）
按名称排序全量扫描；`webapp/app.py:283` 的 `/api/state` 把它们原样放进 `projects`；
前端 `web/src/main.ts:727` 的 `projectsHtml()` **一个不落全部渲染成卡片**。

设计隐含前提是「work_root 内文件夹数量少、且都是当前活跃项目」。一旦本地项目文件夹增长到
几十上百个（GitHub 仓库、历史项目、试验目录平铺在同一根下），首页将渲染全部项目卡：
信息淹没、没有重点，「工作台」退化成目录浏览器。用户原话：「假如以后我的本地项目文件夹有
100 个，那不能我的工作台也显示 100 个项目吧。」

## 决策（三轮选择题结论）

首页只显示**用户选择盯着的项目**；全量项目另设可浏览视图；「哪些上界面」由用户在界面里
显式管理。事实源复用既有 `_vault/projects/*.md` 项目主笔记（ADR 0011 注册表），**不扩
frontmatter schema、不加新词表**。

### 1. 首页显示集合 = 「已建档且 active」的项目

- `work_root` 直接子目录 `P`（≠ `_vault`）在首页显示，当且仅当
  `_vault/projects/<P>.md` 存在、`type: project-main`、且 `status: active`。
- `status` 词表本就含 `active/archived/paused/ignored`（`domain/vault.py:17`），
  **零 schema 变更**。v1 规则只认 `active` 上首页；其余状态一律不上首页但保留在
  「全部项目」页。
- 语义：**「加入工作台」= 建档动作**（有 active 主笔记）。现有 `wb project new` 建的笔记
  默认 `status: active`（`project_registry.py:108`），存量用户**零迁移**：已建档项目照旧上
  首页，唯一行为变化是「无笔记的文件夹不再混进首页卡片」。
- 文件夹名 == 规范项目 ID == 笔记文件名（join key 沿用 `project_scan._next_step_for`
  的现有查找方式），不引入新映射。

### 2. 新文件夹 = 首页顶部「邀请横幅」，不占卡片位

- 未建档文件夹（无 `_vault/projects/<name>.md`）视为**新项目**：首页项目区顶部渲染一条
  邀请（如「3 个新文件夹 · 加入工作台 / 归档」），不渲染成卡片，处理完即消失。
- 动作二选一，都**落盘建档**、可反悔：
  - **加入工作台**：无笔记 → 复用 `create_project_note` 建 active 档案（完整模板）；已有
    archived 笔记 → 改回 `active` 并刷新 `updated`。幂等：已 active 则 no-op。
  - **归档**：建/改 `status: archived` 的档案。之后在「全部项目」页可一键恢复。
- 被忽略的文件夹因此**有档案可循**（不再是每次刷新都提示的新项目），同时也不上首页。

### 3. 新增「项目」页签 = 全部项目页

- 现有页签 `今日 | 审批 | 第二大脑`（`main.ts:214-216`）扩为四页签，新增
  `今日 | 审批 | 第二大脑 | 项目`。
- 「项目」页列出 `work_root` 全量文件夹（含未上首页的），每行：名称、git 动静/积压摘要、
  状态徽标（在工作台 / 新 / 已归档 / 其它）、下一步摘要；提供**搜索过滤**（名称）与
  **排序**（名称 / 需关注）。行内操作：加入工作台 / 归档 / 恢复。
- 首页项目区标题行放「管理全部 →」入口跳转该页签。

### 4. API 与数据流

- `GET /api/state` 仍**全量返回** `projects`（100 项一次返回，纯本地毫秒级；v1 不做
  服务端分页），每项**新增** `registered: bool` 与 `status: str | null`；「是否上首页 /
  是否新」由前端推导（`registered && status === 'active'`；`!registered` = 新），避免
  冗余字段。首页与全部项目页共用同一份数据、同一 60s 刷新周期。
- 新增写端点（与 CLI/既有 repository 共用事实源，meetings.md 原则不变）：
  - `POST /api/projects/activate` `{name}` —— 加入/恢复（幂等）
  - `POST /api/projects/archive` `{name}` —— 归档（幂等）
  - 校验：`name` 必须是 `work_root` 的直接子目录名（防越界/臆造）；非法则返回明确错误。
- 前端改动集中在 `main.ts`（Tab 类型、`renderProjects`、`projectsHtml` 过滤 + 横幅、
  事件绑定）与 `style.css`（横幅/徽标样式）；产物重构建进
  `src/summit_workbench/webapp/static/`。

## 实现（已落地，2026-09-03）

- `repositories/project_registry.py`：新增 `read_project_registration`（(registered, status)）、
  `ensure_project_active`（无档案则建档、archived→active、幂等）、`archive_project`
  （active→archived；未建档则先建档再归档）、`project_note_path`；`updated` 随状态改写刷新为
  当日（复用 `note_status.update_note_status`，新增可选 `extra` 参数一并写回）。
- `repositories/project_scan.py` / `ProjectState`：新增 `registered`、`status` 字段；读档与
  「下一步」合并为一次 `_project_registry_state`（档案口径与 registry 一致）。
- `webapp/app.py`：`/api/state` projects 增 `registered/status` 字段；新增
  `POST /api/projects/activate`、`POST /api/projects/archive`（`_project_dir` 校验必须为
  work_root 直接子目录）。`webapp/api.py` 增 `ProjectPayload`。
- `web/main.ts` / `web/src/style.css`：第 4 页签「项目」（全部项目视图：搜索 + 排序
  在工作台/新/归档 + 行内加入/归档）；首页推进卡只渲染 active 档案；新文件夹邀请横幅
  （逐条「加入工作台 / 归档」）；「管理全部 →」入口；toast 反馈沿用审批操作风格。
- CLI 对称（`wb project archive/activate`）**不在 v1**，见遗留。

## 验收

- 单测：档案状态读写与幂等（无笔记建档 active、archived→active、active 再 activate
  no-op、归档未建档文件夹建 archived 档案、同名非档案文件拒绝）；`ProjectState` 新增字段
  分类（新/归档）；`/api/state` 字段暴露；`/api/projects/activate|archive`（正常、非法名、
  非直接子目录、幂等）；扫描仍跳过 `_vault`。
- 前端：`tsc --noEmit` + `npm run build` 通过（产物已进 `webapp/static/`）。
- 质量门：ruff + ruff format（改动文件）+ mypy --strict（113 源文件）+ pytest **374 项全绿**。
- 手测（`wb web` 面板，待复核）：今日页出现「新文件夹」邀请横幅 → 加入后项目卡出现 →
  归档后从首页消失且不再提示 → 「项目」页可见全部文件夹（含归档）可搜索、可恢复 → 60s
  自动刷新不丢状态。

## 稳定性收益

- 首页从「全量平铺」收敛为「我盯着的项目」，百级文件夹下仍是清爽的推进视图；新文件夹
  通过横幅**有感知地**进入决策，不会静默混入也不会被遗忘。
- 事实源单一：建档状态同时驱动首页显示、`#项目` 标签解析、审批路由（ADR 0011）与
  「全部项目」管理，一处维护处处生效；归档只动 frontmatter，文件夹与 git 历史零触碰。

## 遗留

- **忽略语义细化**：v1 的「归档」即横幅上的处置动作；若日后需要「不提示但也不建档案」的
  轻忽略，可另加 `ignored` 档案或忽略名单，本期不做。
- **CLI 对称**：`wb project archive/activate` 本期不做，Web 端点先落地；需要时补 CLI
  命令与测试。
- **SSR 兼容层**（`webapp/views.py`，非默认入口）：本期不同步；如首页卡片被 SSR 渲染，
  旧行为（全量）保留在兼容路由。
- **孤立档案**：有笔记但文件夹已移出 `work_root` 的孤儿笔记（registry 漂移）本期不清理。
- **paused 等其它状态**：v1 一律不上首页；若日后要「暂停但仍盯」再加语义。
