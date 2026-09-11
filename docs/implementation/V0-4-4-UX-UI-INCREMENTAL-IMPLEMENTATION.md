# v0.4.4 UX/UI 增量改造实施记录

## 基线

- 历史审计起点：源码 `b2faecb`（2026-09-10）；本轮继续工作的交接基线是 `6c910cc`（`main`）。
- 本轮最新静态 frontend build：`v2026.09.10-4abe7fb-350853f1`；已验收 App build 9 的身份不在本轮改写。
- 本轮范围止于源码、前端构建产物与本地验证；不安装/替换 App、不操作真实飞书数据。导入抽屉关闭焦点修复及交接文档已提交并推送到 `origin/main`；隔离审计稿已随历史资料归档并纳入版本控制。
- 保留六页签、今日简报置顶、相对 API 地址、现有 feature 边界、审批与外部写回安全边界。

## 文档职责与读法（2026-09-11）

- 本实施记录按时间记录改动阶段、U01–U19 问题状态、用户可见变化、测试证据和未验证项；后续阶段继续追加，不承担当前产品规格的权威职责。
- [`V0-4-4-UX-UI-HANDOFF.md`](V0-4-4-UX-UI-HANDOFF.md) 保留当前交接快照、不可破坏边界、真实验证结论和后续执行顺序；发生阶段交接或验证边界变化时更新，不重复粘贴完整实施过程。
- 当前规则仍以 `docs/product/`、`docs/decisions/`、当前验收文档和代码为准；本记录与交接档案只解释本轮增量工作的状态和证据。

## 当前复盘（2026-09-10）

- 当前继续工作的交接基线是 `6c910cc`（`main`）；本轮改造作为增量提交到 `origin/main`，早期 `ce0b27e` / `d11ec56` 仅作为历史记录保留。
- 完整交接档案见 [`V0-4-4-UX-UI-HANDOFF.md`](V0-4-4-UX-UI-HANDOFF.md)，其中保留最初阶段 0–7 计划、U01–U19 审计问题和后续 agent 的执行顺序。
- 已完成的主要可靠性闭环包括：捕捉失败保留原文、刷新失败可见、审批先预演再写回、批量候选资格限制、部分失败/未知外部结果可见、来源只读核查、问答结构化回答、项目显示名搜索、产物状态二次确认、指南本地搜索、设置连接状态语义和同源草稿保护。
- 既有 CUA 真实浏览器回归已覆盖今日、审批、项目、指南、第二大脑和设置主流程；本轮隔离 Chrome 又验证了审批筛选/选择/按选中批量决定、分叉横幅、冲突详情与只读预检、项目内嵌详情入口和今日返回焦点。审批预演仍未确认写回，设置页及高级区的既有无横向滚动结论保持。
- 本轮继续保持：不替换已安装 App、不执行真实模型调用、不操作真实飞书写回、不导入真实会议文件、不把动态 loopback 端口之间的历史迁移写成已支持。

## 阶段 0：文档校准

- [x] 记录审计起点与本轮范围。
- [x] 对齐简报置顶、捕捉快捷行、导入抽屉的说明。
- [x] 明确“批准只标记，应用后写回”。
- [x] 区分读取本地快照与重新生成简报。
- [x] 说明同 origin 草稿/历史恢复范围，不承诺动态端口迁移。

## 阶段 1：操作状态与草稿保护

- [x] 捕捉成功/失败结果与并发提交保护；失败和请求期间的新文字不会被清空。
- [x] 刷新分区结果与外部写回读取失败可见；局部刷新失败保留旧数据并提供重试。
- [x] 审批写回必须先完成本页预演，结果按完成/部分完成展示，并返回结构化 applied/rejected/failed 计数。
- [x] 补齐 workspace-scoped 的实体草稿：问答线程、审批候选、日志、产物分别保存；刷新/重绘不会覆盖已有审批草稿，存储失败会显式提示。
- [x] 增加 workspace generation、状态/审批刷新 request sequence；过期响应不再覆盖新工作区或新结果，局部读取失败保留上次成功数据和时间。
- [x] 问答失败不写入下一次检索历史；外部写回失败保持可见；产物草稿在实际提交成功后才清理。
- [x] 普通编辑弹层关闭前检查未保存内容，支持确认放弃；成功/失败路径均保留可恢复草稿边界。
- [x] 自动化 worker 将简报返回的显式持久化路径（用量/授权状态/简报）与运行心跳一起提交，避免系统信号制造 `dirty-protected`。
- [x] 设置页“立即运行”使用强制执行语义，不会被当天已执行过的调度记录误判为“当前不在任务执行时间”。
- [x] 顶部“刷新”同时刷新工作区数据与同步横幅，避免实际已恢复后继续显示旧的 `dirty-protected` 状态。
- [x] 项目线视图等专用弹层复用统一焦点初始化；打开后焦点进入弹层，嵌套日志/产物弹层不覆盖原始返回焦点，Escape 关闭后归还到触发按钮。
- [x] 产物保存与“同步当前状态”拆成两步：保存产物后先展示最终摘要预览，确认才覆盖主档案，取消只保留产物。

## 阶段 2：导航、弹层与视觉

- [x] 完成 tablist 关联、方向键/Home/End、跳转主内容和统一焦点环。
- [x] 收敛主色、字号、按钮热区、窄屏布局、消息类名与 reduced-motion。
- [x] 设置页双列卡片、自动化控件与高级维护区在真实浏览器中无横向溢出；长路径与窄容器可安全收缩/换行。
- [x] 普通弹层与项目线视图支持初始焦点、Tab 约束、Escape/背景关闭保护提示和关闭后焦点归还。
- [x] 同步冲突专用弹层接入同一套草稿关闭保护、初始焦点、Tab 约束、Escape/背景关闭和返回焦点；人工选择按 workspace 保存，成功恢复后清理。
- [x] 本轮涉及的主色、字号、按钮热区、窄屏布局与消息类名已收敛；尚未做真实 WKWebView 视觉回归。

## 阶段 3–7

- [x] 审批安全入口、导入持续回执、项目显示名搜索与“未发现同步提醒”语义已补入本轮增量。
- [x] 本轮实现收口完成：审批筛选/批量选择、同步冲突弹层统一保护、项目页内详情/返回上下文和导入多文件回执均已补齐；证据阅读、问答结构化展示、指南目录与设置状态已分别完成。
- [x] 审批页增加全部/待确认/已批准/已拒绝状态筛选、待确认复选框、当前筛选与已选范围摘要；切换筛选会清空选择。
- [x] 按选择批量批准/拒绝复用 `/api/review/batch` 决定入口；批准仍只纳入“有依据 + 有落点”的候选，保留 100 条上限，未增加旁路写回。
- [x] 审批批量批准只纳入“有依据 + 有落点”的待确认候选；按钮显示实际范围，缺失项保留待处理；单批超过 100 条时前端拦截并提示缩小范围。
- [x] 审批来源可从卡片直接打开只读文本；服务端校验路径位于当前 vault 内，并对缺失、越界、非文本与超大来源返回明确状态。
- [x] 问答响应保留结构化 `QaAnswer` 与旧 `answer_html/source_ids`；界面分开展示结论、事实、冲突、建议、无法作答，以及实际引用/仅召回来源。
- [x] 问答与审批共用 vault 范围只读来源面板；返回来源 ID、标题、日期、正文，禁止越界/非知识路径并保留旧会话 HTML 兼容。
- [x] 窄屏问答提供可聚焦的会话下拉选择器；指南页提供随包内置的本地目录、搜索与无结果清除，不引入网络依赖。
- [x] 设置页按原始 provider 状态显示未配置/未连接、已配置/已授权、验证失败与需重新授权；不把验证失败伪装成成功连接。
- [x] 审批页的状态筛选、复选框选择和“按当前选择批量处理”已实现；按会议全批/全拒、资格过滤、单批 100 条限制和统一预演入口保持不变。
- [x] 项目详情已迁移到项目页内渲染，提供返回今日/项目列表，并保存查询、筛选和滚动上下文；本轮真实浏览器已验证项目列表查询恢复，以及今日 → 内嵌详情 → 返回今日的入口焦点恢复。

## 验证记录

| 阶段 | 测试 | 结果 | 未验证/限制 |
|---|---|---|---|
| 基线 | `npm --prefix web run test:frontend` | 通过；含新增浏览器交互契约 | 仅源码契约/纯渲染，不等同真实浏览器点击布局验证 |
| 阶段 0–2 | `npm --prefix web run build` | 通过；生成 `v2026.09.10-9bdee5f-3def1d9d` | 未执行 App 重启/WKWebView 真机验证 |
| 阶段 0–2 | `UV_CACHE_DIR=/tmp/summit-workbench-uv-cache uv run --no-sync pytest tests/contract/test_web_route_contract.py` | 1 passed | — |
| 阶段 0–2 | `UV_CACHE_DIR=/tmp/summit-workbench-uv-cache uv run --no-sync pytest tests/unit` | 763 passed, 5 warnings | 警告来自第三方依赖弃用提示与非 loopback 开发配置 |
| 阶段 0–2 | `UV_CACHE_DIR=/tmp/summit-workbench-uv-cache uv run --no-sync ruff check .` / `ruff format --check .` | 通过 | — |
| 阶段 0–2 | `UV_CACHE_DIR=/tmp/summit-workbench-uv-cache uv run --no-sync mypy` | 通过；312 个源码文件 | — |
| 阶段 0–2 | `node web/scripts/verify-build.mjs src/summit_workbench/webapp/static` | 通过；`v2026.09.10-9bdee5f-3def1d9d` | — |
| 阶段 0–2 | `git diff --check` | 通过 | — |
| 阶段 1 | 本机 `127.0.0.1:8797` 真实界面验收 | 通过；设置页立即运行成功，显式信号已提交，刷新后顶部同步横幅恢复隐藏/`ready` | 未执行真实飞书写回 |
| 阶段 2 | 本机 `127.0.0.1:8797` 专用弹层焦点验收 | 通过；项目线视图焦点进入“✎ 日志”，Escape 关闭后归还 `demo-project` 触发按钮 | 未执行 App/WKWebView 独立回归 |
| 阶段 4 | 产物状态同步保护 | 通过源码契约、前端构建和真实界面只读验收；同步主档案前增加最终摘要确认 | 未提交真实产物，不执行真实 vault 写入 |
| 阶段 3 | 审批批量资格与范围 | 通过纯渲染、浏览器交互契约、前端构建与构建产物校验；批准范围排除缺依据/落点候选，100 条上限在请求前拦截 | 未执行真实审批写回 |
| 阶段 3 | 审批证据阅读路由 | 通过 API 单元测试、纯渲染、浏览器交互契约与路径越界测试；来源仅读且限制在当前 vault | 未执行真实审批写回 |
| 阶段 6 | 问答结构化回答与来源面板 | 通过结构化 API 单元测试、前端契约、完整单元测试、mypy 与构建校验；不改变模型调用次数 | 未执行真实模型调用与真实写回 |
| 阶段 7 | 指南目录/搜索与窄屏问答 | 通过前端契约、完整单元测试、mypy 与构建校验；真实本地浏览器验证搜索只显示匹配章节，目录链接同步过滤；搜索仅作用于内置内容，窄屏会话切换不新增数据源 | 未执行 320/390px 独立 App 快照回归 |
| 阶段 7 | 设置连接状态语义 | 通过前端契约、构建与 `git diff --check`；未配置、验证失败、飞书需重新授权使用不同状态徽标 | 当前 profile API 仍只产生已配置/未配置；现场验证失败以操作结果区即时呈现，未新增持久化失败状态 |
| 阶段 7 | 本机 `127.0.0.1:8797` 真实浏览器回归 | 通过 CUA 验收今日/审批/项目/指南/问答/设置主流程；审批预演显示 `DRY-RUN（零写入）` 且批准写回、拒绝归档、失败均为 0；设置页及高级区 `scrollWidth=clientWidth`，无横向滚动条 | 未点击“确认应用（写回）”、未执行真实模型调用、真实飞书写回或文件导入；测试产生的 1 个空问答会话仅存在浏览器本地状态 |
| 本次复核 | `uv run --no-sync pytest tests/unit` | 通过；766 passed，5 warnings | 警告来自第三方依赖弃用提示与非 loopback 开发配置 |
| 本次复核 | `uv run --no-sync pytest tests/contract/test_web_route_contract.py` | 通过；1 passed | 不等同真实远端服务验证 |
| 本次复核 | `uv run --no-sync ruff check .` / `ruff format --check .` / `uv run --no-sync mypy` | 全部通过；393 个文件已格式化，312 个源码文件无类型错误 | — |
| 本次复核 | 前端契约、纯渲染、生产构建、`verify-build.mjs`、`git diff --check` | 上一轮同一源码状态全部通过；构建身份为 `v2026.09.10-828f18b-6a84f57f` | 未重新打包或替换 build 9 App |
| 本次审批筛选增量 | `node web/scripts/test-review-render.mjs` / `npm --prefix web run test:frontend` | 通过；新增状态筛选、复选框、选择摘要和交互契约覆盖 | 仍需真实浏览器验证筛选切换、一次点击一次请求及 0/1/100/101 条矩阵 |
| 本次审批筛选增量 | `uv run --no-sync pytest -q` | 838 passed，1 skipped，5 warnings | skip 为 packaged App smoke；未执行真实审批写回 |
| 本次审批筛选增量 | `npm --prefix web run build` / `node web/scripts/verify-build.mjs src/summit_workbench/webapp/static` | 通过；构建身份为 `v2026.09.10-6c910cc-34da6f93` | 未重新打包或替换 build 9 App |
| 本次审批筛选增量 | `uv run --no-sync ruff check .` / `uv run --no-sync ruff format --check .` / `uv run --no-sync mypy` / `git diff --check` | 全部通过；394 个文件已格式化，312 个源码文件无类型错误 | — |
| 本次冲突弹层增量 | `uv run --no-sync pytest tests/unit/test_sync_conflict_recovery.py tests/unit/test_webapi.py tests/contract/test_web_route_contract.py tests/unit/test_web_security.py -q` | 67 passed，2 warnings | 合成分叉 workflow/API 已回归；未执行真实远端同步或写回 |
| 本次冲突弹层增量 | `npm --prefix web run test:frontend` / `npm --prefix web run build` / `node web/scripts/verify-build.mjs src/summit_workbench/webapp/static` | 全部通过；构建身份为 `v2026.09.10-6c910cc-5a228f90` | 尚未用 CUA 验证冲突弹层的真实焦点与关闭保护 |
| 本次冲突弹层增量 | `uv run --no-sync ruff check .` / `uv run --no-sync ruff format --check .` / `uv run --no-sync mypy` / `git diff --check` | 全部通过；394 个文件已格式化，312 个源码文件无类型错误 | — |
| 本次项目详情增量 | `node web/scripts/test-project-render.mjs` / `npm --prefix web run test:frontend` | 通过；新增项目详情页内渲染、归档筛选和返回入口覆盖 | 仍需 CUA 验证从今日返回后的查询/筛选/滚动位置 |
| 本次项目详情增量 | `npm --prefix web run build` / `node web/scripts/verify-build.mjs src/summit_workbench/webapp/static` | 通过；构建身份为 `v2026.09.10-6c910cc-67b1c911` | 未执行 packaged App/WKWebView 回归 |
| 本次导入回执增量 | `uv run --no-sync pytest tests/unit/test_webapi.py -q` | 47 passed，1 warning；覆盖成功、部分失败响应和无模型配置时的幂等跳过 | 未执行真实模型/API 或真实用户文件导入 |
| 本次导入回执增量 | `node web/scripts/test-today-import-render.mjs` / `npm --prefix web run test:frontend` | 通过；覆盖多文件队列、成功/部分/失败/处理中、软预算、关闭重开和幂等文案渲染 | 尚未用 CUA 做真实拖入与关闭重开操作 |
| 本次导入回执增量 | `npm --prefix web run build` / `node web/scripts/verify-build.mjs src/summit_workbench/webapp/static` | 通过；构建身份为 `v2026.09.10-6c910cc-a9f3d921` | 未执行真实模型调用、飞书写回或真实会议导入 |
| 本轮最终自动门禁 | `uv run --no-sync pytest -q` | 通过；840 passed，1 skipped，5 warnings | skip 为 packaged App smoke；未执行真实外部服务/真实写回 |
| 本轮 route/security | `uv run --no-sync pytest -q tests/contract/test_web_route_contract.py tests/unit/test_web_security.py` | 通过；12 passed，2 warnings | 不等同真实远端服务或原生 App 验证 |
| 本轮前端/构建 | `npm --prefix web run test:frontend` / `npm --prefix web run build` / `node web/scripts/verify-build.mjs src/summit_workbench/webapp/static` | 全部通过；构建身份为 `v2026.09.10-6c910cc-7c3becef` | 未重新打包或替换 build 9 App |
| 本轮静态门禁 | `uv run --no-sync ruff check .` / `ruff format --check .` / `mypy` / `git diff --check` | 全部通过；394 个文件已格式化，312 个源码文件无类型错误 | — |
| 本轮隔离 CUA Chrome | 合成 vault + 合成 Git 分叉；审批筛选/复选框/选择摘要/按选中批量批准/切换筛选清空选择；分叉保护横幅；项目列表内嵌详情与返回项目列表 | 已观察到真实 UI 状态与结果；审批没有触发“检查并写回”；同步没有执行恢复/同步写回 | CUA 随后因 Mac 锁屏中断；未完成冲突导出/临时预检最终确认、Tab/返回焦点闭环、导入拖入、宽度/缩放/主题全矩阵 |
| 本轮隔离 CUA 冲突弹层 | 合成 `conflict.md` 本地/远端同路径分叉；详情弹层初始焦点落在人工选择；选择“保留本机”后按 Escape | 浏览器真实弹出未保存草稿关闭确认：“当前弹层里有未保存内容。继续关闭并放弃草稿吗？” | CUA 在处理确认框时焦点通道超时并被锁屏；未把取消后的返回焦点、Tab 约束或导出写成通过 |

| 本轮解锁后 CUA 响应式矩阵 | 真实隔离 Chrome 设置 `1280×820`、`960×640`、`768×640`、`390×700`、`320×700`，检查 `body/document scrollWidth` | 五档均无整体横向溢出：分别为 `1265/1265`、`945/945`、`753/753`、`375/375`、`305/305`（body/client） | Chrome 原生缩放快捷键在当前 CUA 扩展不改变浏览器 zoom；未宣称 200% 原生缩放通过；深色当前窗口可见，浅色/系统 reduced-motion 未切换实测 |
| 本轮解锁后 CUA 项目路径 | 合成中文显示名项目；真实键盘打开详情并返回，另验证项目页搜索值恢复 | 今日 → 项目详情显示“返回今日”，返回后中文项目入口获得焦点；项目页搜索 `中文验收项目` 后进入/返回保留查询值 | 项目页路径的 CUA AX 在部分 Playwright 点击/重绘后回报页面根节点，不能把该路径的返回焦点单独记为稳定通过；今日路径是稳定通过 |
| 本轮解锁后 CUA 冲突路径 | 合成分叉；详情初始焦点、人工选择“保留本机”、临时预检、Tab 环、Escape 草稿保护 | 初始焦点落在人工选择；预检显示“临时预检通过”且明确“确认后才会写回”；Tab 从最后按钮回到选择；Escape 弹出未保存保护，取消保持弹层 | 没有点击“确认恢复并创建提交”；冲突包导出动作曾尝试但下载事件未取得确定证据；确认框关闭后的 AX 返回焦点受原生对话框缓存影响，不单独宣称通过 |
| 本轮解锁后 CUA 导入路径 | 真实打开导入抽屉、关闭/重开；隔离合成 `.md/.txt/.pdf/空文件` 通过本地 API 投递 | 抽屉关闭后可重开且保留可选状态；本地 API 对合成 Markdown 返回“模型未配置”失败、PDF 返回类型错误、空文件返回内容为空；没有真实模型调用 | 当前 CUA `filechooser.setFiles` 返回 `Not allowed`，原生文件面板虽能看到临时合成目录但未完成实际选中；未把浏览器文件导入回执记为通过 |
| 本轮最后自动门禁 | `uv run --no-sync pytest -q`；route/security；`npm --prefix web run test:frontend`；build + `verify-build.mjs`；ruff/format/mypy/diff | `840 passed, 1 skipped, 5 warnings`；route/security `12 passed, 2 warnings`；前端脚本、构建、产物、静态门禁全部通过；最终身份 `v2026.09.10-cb1bd34-ebdc777c` | skip 为 packaged App smoke；未执行真实外部服务、原生 App/WKWebView、真实写回 |

## 冗余清理后复核（2026-09-10）

- 当前 HEAD：`cb1bd34`（`main` = `origin/main`）；本轮验证未执行真实外部写回。
- 覆盖率门：`uv run --no-sync pytest --cov=summit_workbench --cov-report=term-missing --cov-fail-under=80 -q` 通过，`840 passed, 1 skipped, 5 warnings`，总覆盖率 `81.12%`。
- `cd web && ./node_modules/.bin/tsc --noEmit`、`uv lock --check`、`uv run --no-sync python scripts/secret_scan.py` 均通过。
- `bash scripts/test-native-updates.sh` 与 `bash scripts/test-native-automation.sh` 均通过；更新协调器测试夹具补充合成 workspace compatibility marker，未改变生产 Swift 代码或 fail-closed 语义。
- `uv run --no-sync pytest -q tests/integration/test_packaged_app.py -m integration`：`1 skipped`；未设置 `WB_PACKAGED_APP`，不能替代 packaged App/WKWebView 验收。
- `npm --prefix web run build` 与 `node web/scripts/verify-build.mjs src/summit_workbench/webapp/static` 通过，静态产物身份为 `v2026.09.10-cb1bd34-ebdc777c`。
- CUA 浏览器通道本轮连续两次超时并自动重置，未取得新的真实页面状态；先前隔离 Chrome 证据仍按原记录保留，不把本轮 CUA 记为通过。

每个阶段完成后更新本表，并记录下一阶段起点。未执行的真机、WKWebView、真实飞书操作不宣称通过。

## 本轮 CUA 续测与窄屏修复（2026-09-10）

- 真实发现并修复 320px 设置页 4px 整体横向溢出：原因是自动更新说明标签强制 `white-space: nowrap`；先在 `web/scripts/test-browser-contract.mjs` 增加窄屏换行契约，确认旧 CSS 会失败，再在 `web/src/style.css` 的 `max-width: 380px` 内允许 `.automation-enabled` 换行并按词/字符断行。生产产物已重建，最终身份为 `v2026.09.10-cb1bd34-60122c81`。
- 真实发现并修复项目详情返回焦点误落 `body`：今日推进和项目页存在同名入口时，旧 helper 只检查入口自身的 `display`，会选中隐藏祖先中的重复按钮；先补契约断言，再在 `web/src/legacy-main.ts` 加入 `getClientRects().length > 0`，只选择实际占据布局的可见入口。
- 隔离 CUA 环境：`127.0.0.1:8798`、临时 `HOME`、临时 workspace/vault；不含真实凭据、真实飞书、真实模型或真实业务资料。CUA 真实完成 onboarding 新建工作台 → 跳过模型/飞书 → 重启后进入工作台；设置高级维护默认折叠/展开；六页签 Home/End/方向键循环；审批状态筛选、复选框、切换筛选清空选择、单选批量批准；中文显示名与 `·` 特殊字符搜索、项目归档/恢复、项目页内详情返回查询与入口焦点；导入抽屉关闭重开和两个合成 `.md/.txt` 文件的原生 file chooser 选择。
- CUA 响应式复测：`1280×820`、`960×640`、`768×640`、`390×700`、`320×700` 的 `body/document scrollWidth` 均等于 client width（分别 `1280/1280`、`945/945`、`753/753`、`375/375`、`305/305`）；320px 页签内部仍有预期的可横向滚动 tablist，不构成页面整体溢出。
- CUA 导入结果：file chooser 在 IAB 中可用且报告 `multiple=true`，两份合成文件均显示明确的“模型未配置”失败回执；关闭后重开仍保留两条回执。成功、部分失败、软预算提醒和重复完成导入仍未执行，因为隔离环境没有配置模型/本地 mock 模型服务。
- CUA 项目结果：修复后返回焦点稳定落在中文项目入口，搜索值保留；本次 fixture 页面高度等于视口，未形成可移动滚动位置，因此滚动位置恢复单独记为未验证。审批单次批量操作已观察到一次按钮点击后的结果，但当前浏览器通道未提供可靠的 POST 请求计数面板，不把“一次点击一次请求”网络证据写成通过。

| 本轮 CUA 续测 | 结果 | 未验证/限制 |
|---|---|---|
| 320px 溢出回归 | 通过；先失败契约后修复，最终 `305/305` | 仅验证页面级溢出；tablist 内部滚动保留 |
| 项目返回焦点 | 通过；隐藏祖先重复入口不再抢焦点，查询值保留 | 本次 fixture 无可移动页面滚动，滚动位置未验证 |
| 原生多文件导入 | 通过文件选择与失败回执；两条回执关闭重开保留 | 模型未配置，成功/部分/软预算/幂等完成导入未验证 |
| 审批真实交互 | 通过筛选、选择、清空和单选批量批准 | 未取得网络请求计数；0/1/100/101 条完整矩阵未验证；未执行检查并写回 |
| 全宽度页面溢出 | 通过；1280/960/768/390/320 无整体溢出 | 浅色主题、原生 200% 缩放、系统 reduced-motion 未切换 |

## 导入抽屉关闭焦点续测（2026-09-10）

- U09/U10：先在 `web/scripts/test-browser-contract.mjs` 增加“关闭导入抽屉后焦点回到触发按钮”的契约断言；确认旧实现缺少该行为后，在 `web/src/features/today/index.ts` 的统一 `setOpen(false)` 路径补充 `#btn-import-meeting` 焦点恢复。没有改变导入队列、回执、幂等或 API 契约。
- 隔离 CUA IAB 真实操作：打开抽屉后关闭按钮，抽屉隐藏且焦点回到“＋ 导入会议纪要”；再次用触发按钮打开/关闭，结果相同。导入回执仍保留在工作区状态中。
- 本阶段构建身份：`v2026.09.10-a07f1bc-350853f1`；`npm --prefix web run test:frontend`、`cd web && ./node_modules/.bin/tsc --noEmit`、生产构建与 `verify-build.mjs` 已通过。

| 导入抽屉返回焦点 | 通过；关闭按钮和触发按钮切换关闭都返回 `#btn-import-meeting` | 成功/部分失败/软预算/完成导入幂等仍因未配置隔离 mock 模型而未验证 |

## 提交后隔离 CUA 复核（2026-09-10）

- 提交 `a07f1bc` 推送后，隔离 `127.0.0.1:8798` 重新加载的真实页面显示构建身份 `v2026.09.10-a07f1bc-350853f1`；随后提交 `1a773c8` 只校正交接文档与构建产物记录，没有改变运行时代码。
- CUA 真实复核设置页：四个主要设置分组可见，高级与维护默认折叠，点击后可展开工作台切换、Git 同步、健康检查和诊断区；未触发在线检查、令牌提交或外部连接。
- CUA 真实复核项目路径：从项目列表打开页内详情，看到“返回项目列表”，返回后焦点回到中文显示名项目入口；没有通用详情弹层或外部写回。
- CUA 真实复核导入路径：打开抽屉时焦点在触发按钮，点击关闭后抽屉隐藏且焦点回到 `#btn-import-meeting`；此次没有重新选择文件或触发模型处理。
- 针对本阶段边界的合成回归：冲突/导入/API/安全 `80 passed, 2 warnings`；审批/项目/工作区 `58 passed, 1 warning`；会议/onboarding `26 passed, 1 warning`；前端契约与纯渲染全部通过。CUA 视口能力在本次新会话不可用，因此没有把新的宽度数字扩展为本轮证据；既有 1280/960/768/390/320 页面级无溢出记录保持不变。

| 提交后隔离 CUA 复核 | 通过设置高级区、项目页内详情返回焦点、导入抽屉关闭返回焦点；合成相关回归共 164 项通过 | 本次未新增 200%/浅色/reduced-motion/packaged App 证据；未触发在线连接、模型或写回 |

## 2026-09-11 继续复核

- 自动门禁：全量覆盖率测试 `840 passed, 1 skipped, 5 warnings`，总覆盖率 `81.12%`；route/security `12 passed, 2 warnings`；前端契约/纯渲染、TypeScript、ruff、format、mypy、锁文件、密钥扫描、原生更新与自动化测试均通过。packaged App smoke 仍为明确 skip。
- 构建门禁：`npm --prefix web run build` 与 `node web/scripts/verify-build.mjs src/summit_workbench/webapp/static` 通过，静态身份为 `v2026.09.10-4abe7fb-350853f1`；生成产物与页面显示身份一致。
- 隔离 CUA：在临时 `HOME`、workspace/vault、`127.0.0.1:8798` 上真实打开设置页，确认高级与维护默认折叠；重新打开 onboarding，跳过模型和飞书后显示“设置完成”，进入工作台成功；六页签使用 `End` 到“设置”、`ArrowRight` 回到“今日”；导入抽屉关闭后焦点回到触发按钮。没有执行在线检查、OAuth、模型调用、真实文件处理或外部写回。
- 本阶段没有新增代码问题；未把 CUA 本次不可用的 viewport 能力扩展为新的响应式证据，既有 1280/960/768/390/320 页面级无整体溢出记录保持不变。

| 2026-09-11 继续复核 | 全量自动门禁通过；最新构建真实 CUA 验证 onboarding、六页签键盘循环、设置折叠语义和导入关闭焦点 | 200%/浅色/reduced-motion/packaged App、真实外部服务及完整异常矩阵仍未验证 |

## 文档资产保守归档（2026-09-11）

- 按产品所有者选择的“保守整理”方案，将早期背景、旧架构图、已完成开发/生命周期/多设备计划、P2-02 build 25–29 runbook、简报 v2 静态预览和 ponytail 审计移入 `docs/archive/`；内容保留、路径可追溯，没有删除历史资料。
- 当前权威/操作文档仍保留在原位置：`docs/product/`、`docs/decisions/`、`docs/acceptance/V0-4-4-LOCAL-RELEASE-ACCEPTANCE.md`、`docs/implementation/`、`docs/DESKTOP_APP.md` 和 `docs/RELEASING.md`。
- `README.md`、`PROJECTDESC.md`、PRD、相关 ADR、产品说明和 `CHANGELOG.md` 已改用归档路径；`web/scripts/preview-brief.mjs` 继续可运行，但只生成到 `docs/archive/design/brief-v2-preview.html`。
- 归档不是当前规格：如果历史材料与 PRD、ADR 或现行代码冲突，以当前权威文档和代码为准。

## 下一阶段起点与未完成清单

### 优先继续优化的实现项

本轮四项实现均已完成；本轮已在解锁后的隔离 Chrome 补齐主要证据，后续只做未验证项的独立验收，不扩展产品范围。

1. 若需要继续，单独补冲突包下载的确定性证据、项目页路径返回焦点以及浏览器原生多文件选中；仍不得点击冲突恢复写回。
2. 继续完成 Chrome 原生 200% 缩放、浅色主题、系统 reduced-motion 和隔离问答/来源矩阵。

### 已有实现但尚未完成真实验证

- 320/390/768/960/1280 宽度已在隔离 Chrome 复测无整体溢出；原生 200% 缩放、浅色主题、系统减少动态效果下的完整布局与可读性仍未验证。
- 六页签 Home/End/方向键与冲突弹层初始焦点、Tab 约束、Escape 草稿保护已用 CUA 观察；日志/产物弹层、冲突原生确认框后的稳定返回焦点仍未作为本轮全部通过。
- 审批一次点击一次请求、部分失败保留失败项、unknown 不自动重试，以及审批页真实来源打开；本轮已验证筛选/选择/批量批准的真实 UI，未跑 0/1/100/101 条矩阵。
- 真实问答的冲突、无法作答、模型失败、来源失效和历史会话切换；当前只做了页面结构、离线契约和既有本地浏览器主流程验证。
- 项目日志/产物草稿、状态写入失败不重复保存、归档/恢复和返回位置的完整真实矩阵。
- 可见页 60 秒读取、隐藏页暂停读取，以及动态 loopback 端口变化后的同源边界。
- 隔离 packaged App / WKWebView smoke；当前真实 CUA 使用的是本地 Chrome 页面，不等同原生 App 黑盒验收。

### 明确不在本轮偷偷加入的独立事项

- 跨动态端口的历史/草稿迁移；需要独立的持久化存储设计。
- 审批事务协议、跨进程原子快照或新的外部结果重建机制。
- 真实 DeepSeek/API Key、飞书 OAuth、飞书任务/日历写回、真实 vault 导入和真实远端 Git 凭据验证。
- 新主题设置、命令面板、完整 URL 路由、向量库、新云服务和额外外部权限。

## 2026-09-11 隔离 CUA 浏览器验收（本阶段最新事实）

本阶段在临时 `HOME`、临时 workspace/vault、临时 bare Git remote 和合成资料上使用本地 In-app Browser 完成真实页面操作。运行时代码基线仍为 `cb1bd34`；本阶段没有修改运行时代码，只更新本记录与交接档案。没有连接真实飞书/OAuth、模型、远端凭据或真实用户资料，也没有点击任何恢复、审批应用或外部写回确认。

### 已通过

- 响应式页面级溢出：`1280×820`、`960×640`、`768×640`、`390×700`、`320×700` 五档均满足 `body/document scrollWidth <= innerWidth`，观测值分别为 `1280`、`945`、`753`、`375`、`305`；六页签在五档均存在且标签仍为“今日、审批、第二大脑、项目、指南、设置”。
- 六页签键盘巡航：`Home` 到今日、`End` 到设置、`ArrowRight` 从设置回今日，并逐项观察到今日 → 审批 → 第二大脑 → 项目 → 指南 → 设置 → 今日。
- 设置页：四个主要分组可见，高级维护默认折叠；展开后可见工作区切换、Git 同步、健康检查、诊断等维护内容，收起后 320px 页面仍无整体横向溢出。
- 项目：合成中文显示名和 `·` 特殊字符可搜索；详情在项目页内展示而非通用弹层；今日入口进入详情后可见“返回今日”，返回焦点落回项目入口；项目页搜索值可恢复；归档/恢复状态和按钮语义可见。
- 审批：合成 2 条候选完成状态筛选、待确认复选框、选择范围摘要、切换筛选清空选择、按当前选择批量批准；缺依据/缺落点候选的批准按钮保持禁用；批量操作仅改变决定并显示“点检查并写回才真正写回”。“检查并写回”打开零写入预演，未确认写回。
- 同步冲突：合成分叉显示 `diverged-protected` 横幅；详情弹层显示共同基线/本机/远端摘要和人工选择；选择本机/远端后“临时预检”显示通过且说明确认后才会写回；没有执行恢复提交。
- 冲突弹层可访问性：初始焦点进入人工选择；Tab 在弹层内循环，末尾按钮后回到选择控件。存在未保存选择时按 Escape 会先触发“继续关闭并放弃草稿吗？”原生确认，未直接丢弃草稿。
- 导入：打开/关闭/重开抽屉后回执仍在；原生 chooser 报告 `multiple=true`，隔离合成 `.md`/`.txt` 可选中；模型未配置时页面显示明确失败回执，重复选择会留下可区分的失败回执记录；切换页签后导入回执仍保留。
- 指南与问答：指南本地搜索无结果时显示“没有匹配”并可清除；第二大脑在未配置模型时显示 `ask_unavailable` 和“问题未加入下一轮上下文”，没有把失败问题写入下一轮历史。

### 失败或证据不足

- 冲突包导出：已在冲突详情中尝试“导出冲突包”，但 In-app Browser 的 `download` 事件在等待窗口内没有被观测到，弹层仍保持打开；因此记为“下载证据失败/未验证”，不是通过，也没有把响应内容当作文件成功。
- 冲突原生确认框后的稳定返回焦点：原生确认框出现已通过观察，但该次 CUA 通道在确认框处理后发生焦点/页面控制超时；返回焦点不宣称通过。

### 仍未执行或明确跳过

- Chrome 原生 200% 缩放、浅色主题、系统 `prefers-reduced-motion`、packaged App/WKWebView；本次视口尺寸使用浏览器 viewport override，不等同原生缩放或 App 黑盒。
- 审批 `0/1/100/101` 条完整矩阵、global inbox/个人日程的完整浏览器证据、部分失败/unknown 的真实 UI 流程，以及“一次点击一次请求”的网络计数；当前只能确认按钮结果与请求前边界，不能把 UI 点击观察当成网络计数通过。
- 冲突恢复提交、真实同步写回、真实模型成功/部分失败/软预算/完成导入幂等重复、真实 Feishu OAuth/任务/日历写回、真实远端 Git 凭据。
- 项目可移动滚动位置恢复：本次合成 fixture 高度没有产生可观察的滚动位移；查询/筛选恢复已观察，滚动位置仍未验证。
- 来源 404/非 Markdown/超长/路径穿越/符号链接越界和 workspace 隔离的完整真实浏览器矩阵；相关安全/API 契约仍以自动化测试为证据，不冒充 CUA 通过。

### 本阶段文档与门禁说明

- 修改文件：本文件、`docs/implementation/V0-4-4-UX-UI-HANDOFF.md`；没有新增运行时代码或依赖。
- 本阶段实际执行 `npm --prefix web run build` 与 `node web/scripts/verify-build.mjs src/summit_workbench/webapp/static`，构建身份为 `v2026.09.11-5efe838-350853f1`；因本阶段是文档-only 提交，构建生成的静态文件已恢复为提交前状态，没有把产物噪声混入本次提交。
- 既有最新自动门禁仍为：全量 `840 passed, 1 skipped, 5 warnings`，覆盖率 `81.12%`；route/security `12 passed, 2 warnings`；前端测试、TypeScript、build、`verify-build.mjs`、ruff、format、mypy、`git diff --check` 全部通过；packaged App smoke 的 1 个 skip 仍是条件未满足，不是通过。
- 本阶段 CUA 只补充真实页面交互证据；任何未执行的外部服务、原生 App、原生缩放、主题和模型链路继续按“未验证”记录。

## 2026-09-11 终审级代码审核与小步优化（本轮新增，含未提交改动）

范围：只做前端并发/焦点/范围可见性与文档同步的小步修复；不改 API 契约、六个页签、审批写回边界、外部事实源、锁、原子写、outbox、迁移与重试语义；不新增依赖；不做真实写回。分支 `main`，`HEAD` 为 `a9bbc4a`（最近运行时代码基线 `cb1bd34`）。以下改动在执行时**尚未提交**。

### 发现与修复（R01–R08）

**R01 · P1 · 项目详情过期响应会复活/覆盖用户导航**

- 用户场景：项目页点开项目 A（详情读取较慢）后立刻「← 返回项目列表」，或从今日进入后返回；旧响应随后到达。
- 现象与证据：`showProjectView` 没有请求序号，`finally` 只判断 `tab === 'projects'` 就 `render()`；`backFromProjectDetail` 清空 `projectDetail` 后，旧响应仍会把 `projectDetail` 写回并重绘详情，焦点也被抢到详情返回按钮。即使先返回今日，之后切到项目页也会直接看到 A 详情。
- 根因：`/api/state`、`/api/review` 已有 `latestStateRequest` / `latestReviewRequest` 乱序保护，详情读取路径缺失同类保护。
- 最小修复：新增 `latestProjectViewRequest`；请求取号，`try` 赋值前、`catch`、`finally` 三段都比对；`backFromProjectDetail` 自增使在途读取失效；工作区切换自增。
- 修改文件：`web/src/legacy-main.ts`。
- 测试：`web/scripts/test-browser-contract.mjs` 新增 4 条源码级交互契约（修复前失败）。
- 回归风险：低。只影响详情读取结果的采纳条件，列表/返回/滚动/焦点路径不变。
- 值得现在修复：是。

**R02 · P1 · 「确认应用（写回）」可被双击重复提交**

- 用户场景：审批预演弹层内双击「确认应用（写回项目/建任务/归档）」。
- 现象与证据：点击派发器每次点击都调用 `planApply(true)`，`reviewPlanReady` 在请求返回前不会清空，apply 按钮也不禁用 → 可能发出两次 `POST /api/review/apply`。
- 根因：唯一写回入口缺少单次在途保护（决定类操作幂等，但 apply 会触发真实外部写回）。
- 最小修复：新增 `reviewApplyBusy`，`exec` 前检查并置位、禁用弹层内 apply 按钮，`finally` 复位；`decide`/`batchDecide` 成功后置 `reviewPlanReady = false`，使旧预演失效；工作区切换复位。预演/确认两步与服务端 action 不变。
- 修改文件：`web/src/legacy-main.ts`。
- 测试：`web/scripts/test-browser-contract.mjs` 新增 3 条契约（修复前失败）。
- 回归风险：低。仅在客户端阻止重复触发，不改变服务端写回边界。
- 值得现在修复：是。

**R03 · P2 · 撤销弹层绕过统一 dialog 激活**

- 用户场景：仅用键盘打开顶栏「↩ 撤销」，或先开过带草稿的弹层再打开撤销。
- 现象与证据：`openUndoModal` 直接写 `modal.innerHTML` 并置 `backdrop.hidden=false`，没有初始焦点、dialog/aria-modal 语义与关闭按钮，Tab 会走到弹层背后的页面；上一个弹层的 `draftDirty`/`draftEntity` 残留，Escape 会弹出无关的「未保存内容」确认。
- 根因：专用弹层未复用共享 `activateModal/openModal`。
- 最小修复：全部内容分支改用 `openModal(...)`（含关闭按钮、dialog 语义、初始焦点、返回焦点），`#btn-undo` 成为稳定返回焦点；`openModal` 返回 `HTMLElement` 供后续查询。撤销列表、差异查看与还原请求不变。
- 修改文件：`web/src/legacy-main.ts`。
- 测试：`web/scripts/test-browser-contract.mjs` 契约（修复前失败）。
- 回归风险：低-中。新增关闭按钮属于增量；未改变还原语义。
- 值得现在修复：是。

**R04 · P2 · 设置页过期异步渲染覆盖新内容**

- 用户场景：设置页读取在途时保存模型触发刷新，或快速切走再切回设置。
- 现象与证据：`renderSettings` 无渲染序号；先发起的旧响应最后返回时会覆盖新内容，刚保存后的「已配置」可能被保存前的「未配置」盖回。
- 根因：设置页异步渲染缺少乱序保护。
- 最小修复：模块级 `settingsRenderSequence`；`Promise.all` 之后与 `catch` 中比对，过期直接返回。
- 修改文件：`web/src/features/settings/index.ts`。
- 测试：新增 `web/scripts/test-settings-render.mjs`，用 esbuild 打包 settings 模块并以受控 Promise 制造「旧响应最后返回」的真实并发；修复前断言失败（`the newer settings render must win`），修复后通过。
- 回归风险：低。正常串行渲染行为不变。
- 值得现在修复：是。

**R05 · P2 · 60 秒自动刷新在隐藏页继续读取**

- 用户场景：工作台标签页切到后台长时间放置。
- 现象与证据：`setInterval` 无条件每 60 秒请求 `/api/version` 与 `/api/sync/status`；回到前台只补一次版本检查。阶段 4 计划要求「可见页 60 秒读取、隐藏页暂停读取」，此前未落到代码。
- 根因：轮询未按 `document.visibilityState` 门控。
- 最小修复：两个 interval 在隐藏时跳过；`visibilitychange` 变为可见时同时刷新版本与同步横幅。
- 修改文件：`web/src/legacy-main.ts`；同步说明 `docs/product/WEB_WORKBENCH.md` 第 2 节。
- 测试：`web/scripts/test-browser-contract.mjs` 2 条契约（修复前失败）。
- 回归风险：低。可见页仍 60 秒刷新；隐藏页回到前台立即补齐一次。
- 值得现在修复：是。

**R06 · P2 · 同步横幅读取失败会静默隐藏保护态**

- 用户场景：处于 `diverged-protected` 保护态时 `/api/sync/status` 一次读取失败（服务重启/短暂不可用）。
- 现象与证据：`catch` 直接 `el.hidden = true`，保护横幅与「查看冲突详情」唯一入口一起消失，用户看不到冲突状态。
- 根因：失败路径按「无事发生」处理，而非「状态未知」。
- 最小修复：失败时若横幅当前可见，保留上次成功内容并追加「同步状态读取失败…」与新增的「重新读取」（`data-action="sync-refresh"`，只重读状态、不触发同步）；若横幅原本隐藏（多为启动期）则维持隐藏，避免启动噪声。
- 修改文件：`web/src/legacy-main.ts`。
- 测试：`web/scripts/test-browser-contract.mjs` 契约 + 反例断言（不再出现 `catch { el.hidden = true }`）。
- 回归风险：低。
- 值得现在修复：是。

**R07 · P3 · 服务端省略 `workspace_id` 时问答历史永不加载**

- 用户场景：`/api/version` 未返回 `workspace_id`（无活动工作区/回退场景）时打开第二大脑。
- 现象与证据：初始化哨兵 `'unknown'` 与回退 id 相同，`loadAskStore()` 从不执行，已存在 `wb.ask.threads.v1.unknown` 的会话历史不显示。
- 最小修复：哨兵改为 `null`（`let loadedAskWorkspace: string | null = null`），首次必然载入一次。
- 修改文件：`web/src/legacy-main.ts`。
- 测试：`web/scripts/test-browser-contract.mjs` 契约。
- 回归风险：低。有 `workspace_id` 的正常路径行为不变。
- 值得现在修复：是。

**R08 · P2 · 「一键拒绝过期项」范围不可见且任意筛选下可点**

- 用户场景：在「已批准」筛选下看到「一键拒绝过期项」，或列表里其实没有过期项。
- 现象与证据：按钮不显示影响条数、不受当前筛选/选择约束，容易误判范围；无过期项时仍可点。
- 根因：批量入口的操作范围未在动作前呈现。
- 最小修复：`reviewHtml` 计算 `expiredCount`，按钮显示「一键拒绝过期项（N）」，为 0 时 `disabled`，title 说明「不受当前筛选影响」；执行入口仍是 `batchDecide`（100 条上限、只改决定、不写回）。
- 修改文件：`web/src/features/review/render.ts`。
- 测试：`web/scripts/test-review-render.mjs` 纯渲染断言（修复前失败）。
- 回归风险：低。动作语义与请求路径不变。
- 值得现在修复：是。

### 记录但本轮不实施

- P3 文档漂移：`docs/product/PRD.md` L50/L51 仍写「日志/产物入库自动刷新 frontmatter `updated`」，与本轮确认的 P1 语义拆分（日志/产物只写 `activity_at`，`updated` 只由建档/激活/归档/改名/状态确认刷新）以及 `WEB_WORKBENCH.md` 4.4 不一致。涉及权威产品文档，本轮只记录。
- P3 历史只读入口 `/api/review/source` 仍注册在路由契约内，只校验「vault 内 + `.md/.txt`」，不限制知识目录；前端已改用 `/api/sources/read`（限制知识目录并拒绝非 Markdown）。不能删除该路由（契约），已把 `WEB_WORKBENCH.md` 4.3 改为描述真实路由。
- P3 `/api/sources/read` 恒返回 `truncated: false`（超过 256 KiB 直接 413），前端「正文已截断」分支实际不可达。
- P3 `refreshExternalActions` 没有请求序号；并发刷新时较旧的外部动作列表可能后到覆盖新列表（同一来源，影响极小）。
- P3 `submitArtifact` / `submitLog` / `submitRowEdit` 无在途保护：双击可能重复本地保存或重复 PATCH 外部本体。`/api/review/apply` 已加保护；其余属独立小项，未在本次一并改动。
- P3 `test-browser-contract.mjs` 是源码级交互契约，不是真实浏览器测试；本轮新增断言不得被当成点击/键盘/布局验收。

### 本轮验证结果（明确区分通过/失败/跳过/未执行）

| 项目 | 结果 |
|---|---|
| `UV_CACHE_DIR=/tmp/summit-workbench-uv-cache uv run --no-sync pytest --cov=summit_workbench --cov-report=term-missing --cov-fail-under=80 -q` | 通过：`840 passed, 1 skipped, 5 warnings`，总覆盖率 `81.12%` |
| `uv run --no-sync pytest -q tests/contract/test_web_route_contract.py tests/unit/test_web_security.py` | 通过：`12 passed, 2 warnings` |
| `npm --prefix web run test:frontend` | 通过：build identity、feature contract、项目/审批/今日导入/设置渲染纯测试、浏览器交互契约全部通过（含本轮新增 `test-settings-render.mjs`） |
| `cd web && ./node_modules/.bin/tsc --noEmit` | 通过（无输出即无错误） |
| `npm --prefix web run build` | 通过；静态产物身份 `v2026.09.11-a9bbc4a-5a34fb69` |
| `node web/scripts/verify-build.mjs src/summit_workbench/webapp/static` | 通过：`Build verified: v2026.09.11-a9bbc4a-5a34fb69` |
| `uv run --no-sync ruff check .` | 通过 |
| `uv run --no-sync ruff format --check .` | 通过（391 files already formatted） |
| `uv run --no-sync mypy` | 通过（307 source files，无错误） |
| `git diff --check` | 通过 |
| packaged App smoke（`tests/integration/test_packaged_app.py`） | **跳过**：未设置 `WB_PACKAGED_APP`；不是通过 |
| 真实浏览器（CUA）复测 | **未执行**：本轮没有可用浏览器通道 |
| 200%/浅色主题/reduced-motion、packaged App/WKWebView | **未执行/未验证** |
| 真实模型、飞书 OAuth、任务/日历写回、真实远端 Git、冲突恢复提交、真实审批写回 | **未执行**（本轮未点击任何写回确认） |

说明：R04 的测试是真实并发单元测试（受控 Promise 顺序）；其余交互类问题使用 `test-browser-contract.mjs` 源码级断言，修复前已实际失败、修复后通过，但它**不能**替代真实浏览器验证。

### 本轮修改文件

`web/src/legacy-main.ts`、`web/src/features/settings/index.ts`、`web/src/features/review/render.ts`、`web/scripts/test-browser-contract.mjs`、`web/scripts/test-review-render.mjs`、新增 `web/scripts/test-settings-render.mjs`、`web/package.json`、重新构建的 `src/summit_workbench/webapp/static/*`（`build-meta.json`、`index.html`、`assets/index-*.js`）、`docs/product/WEB_WORKBENCH.md`、本文件与交接档案。无新增依赖。
