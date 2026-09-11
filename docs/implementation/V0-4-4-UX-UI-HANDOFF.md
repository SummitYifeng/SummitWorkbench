# SummitWorkbench v0.4.4 UX/UI 增量改造交接档案

> 这份文档用于把本轮改造的起点、原始计划、已完成工作、真实验证边界和下一步执行顺序交给后续 agent。它不是新的产品需求，也不覆盖 PRD、ADR 或安全边界。

## 1. 当前上下文与事实来源

- 仓库：`/Users/yifengstudio/Documents/GitHub/SummitWorkbench`
- 当前分支：`main`
- 当前 `HEAD`/`origin/main` 为 `a9bbc4a`；交接基线提交为 `6c910cc`，最近运行时代码基线为 `cb1bd34`，其后为文档归档与验证记录提交。2026-09-11 终审轮的改动见第 8 节，记录时**尚未提交**。
- `d11ec56` 与 `ce0b27e` 是本档案之前的历史提交，不是本轮验证身份。
- 产品：SummitWorkbench v0.4.4，个人执行管理层 + 第二大脑，本地 Web 工作台由原生 macOS App 或 `wb web` 提供。
- 前端：Vite + 原生 TypeScript + CSS；入口是 `web/src/main.ts`，大量现有交互仍在 `web/src/legacy-main.ts`。不得迁移 React/Next.js，不引入新第三方依赖。
- 后端：FastAPI 与既有 workflow/repository 共用；不要把 `routers/` 目录误认为全部是完整业务实现。
- App 使用动态 loopback 端口；前端请求必须使用相对地址。动态端口变化不会自动共享 `localStorage/sessionStorage`，跨端口历史/草稿迁移是独立事项。

开始继续工作前，必须阅读：

1. `docs/product/PRD.md`
2. `docs/product/WEB_WORKBENCH.md`
3. `docs/product/WEB_USAGE_GUIDE.md`
4. `docs/decisions/0045-v044-uiux-delivery-hardening.md`
5. `docs/acceptance/V0-4-4-LOCAL-RELEASE-ACCEPTANCE.md`
6. `docs/DESKTOP_APP.md`
7. `docs/RELEASING.md`
8. `PROJECTDESC.md`、`README.md`
9. `web/package.json`、`web/src/main.ts`、`web/src/legacy-main.ts`
10. 本轮相关 feature、API、领域逻辑和测试

本档案对应的实施记录是 [`V0-4-4-UX-UI-INCREMENTAL-IMPLEMENTATION.md`](V0-4-4-UX-UI-INCREMENTAL-IMPLEMENTATION.md)，最新本地发布/浏览器记录是 [`V0-4-4-LOCAL-RELEASE-ACCEPTANCE.md`](../acceptance/V0-4-4-LOCAL-RELEASE-ACCEPTANCE.md)。

### 两份 v0.4.4 文档的职责

- 实施记录按阶段保留改动过程、问题状态、用户可见变化、测试证据和未验证项，作为可追溯的工作记录。
- 本交接档案只维护当前快照、不可破坏边界、验证结论和后续执行顺序，作为下一位执行者的入口；不替代实施记录，也不覆盖 PRD、ADR 或现行代码。
- 两份文档都保留在 `docs/implementation/`，后续以“实施记录追加过程、交接档案更新当前状态”的方式维护，避免合并后丢失证据或产生两份当前规格。

## 2. 最初的优化计划是什么

本轮最初不是“做一个更炫的页面”，而是基于现有产品做可预测、可核查、低认知负担的增量可靠性与 UX/UI 改造：保留功能边界和已有业务事实，把用户最容易误解、误操作、丢输入、重复写回和无法核查证据的地方收口。

### 不可破坏的产品决策

- 保留六个页签及顺序：今日、审批、第二大脑、项目、指南、设置。
- 今日简报是首页主区域；捕捉在简报快捷行；会议导入从抽屉进入；宽屏日程/任务两栏，窄屏单列。
- 设置保留工作区、AI 模型、飞书、自动化四组主要内容，高级维护默认折叠。
- 批准/拒绝只改变审批决定；只有“检查并写回”预演后再次确认，才执行本地/飞书写回和审计归档。
- 全局 inbox、新建个人日程可以没有已解析项目，但必须有有效依据；不能用“目标项目不能为空”粗暴阻断。
- 飞书任务/日历是外部事实源；旧简报 Markdown 与结构化快照兼容规则不变。
- `activity_at`（日志/产物活动）和 `updated`（实质状态更新）不能合并。
- 外部写回幂等、结果未知核对、工作区锁、同步保护、审计和本地撤销边界不变。
- 网页简报提交只使用 workflow 返回的显式路径，禁止 `add -A` 带入其他用户修改。
- 工作区凭据、OAuth 回调、原生服务身份验证复用现有实现。
- 不实施 M3、P2-03、向量库、新云服务或额外外部权限；不做跨端口历史迁移、完整 URL 路由、命令面板或审批事务协议重构。

### 设计方向

- 用户：同时管理多条工作线、需要快速恢复上下文的人。
- 首要品质：可理解、可预测、可核查、低认知负担。
- 视觉：克制的桌面工具感，列表优先、分组清晰、证据可展开。
- `DESIGN_VARIANCE = 2/10`，`MOTION_INTENSITY = 1/10`，`VISUAL_DENSITY = 6/10`。
- 保留系统中文字体，不下载字体；使用一致的浅/深色中性色、单一主色、清晰焦点环、至少 32px 常规热区和 44px 窄屏触控热区。
- 不添加 GSAP、视差、粒子或装饰性动画；动画只服务于状态反馈，遵守 reduced-motion。
- 不从零重写，不把 dashboard 做成固定左侧栏，不为“高级感”引入图片、渐变或新依赖。

### 阶段 0–7 原始计划

**阶段 0：校准文档与建立基线**

对齐首页顺序、批准/写回语义、导入抽屉行为、读取快照与重新生成简报的区别；合并指南重复章节；记录同 origin 草稿边界；只修改源码、文档、构建产物和本地验证。

**阶段 1：修复输入、操作状态与真实反馈**

捕捉失败不清空原文；提交期间禁止重复；请求失败/部分失败可见；刷新保留旧数据并显示失败分区；审批写回先预演；问答、捕捉、审批编辑、日志、产物按 workspace/entity 独立保存草稿；工作区代次/请求序号阻止旧响应覆盖新页面；弹层关闭保护未保存内容；自动化显式提交路径与运行心跳；刷新同步业务状态和同步横幅。

**阶段 2：导航、弹层、视觉与窄屏基础**

完成 tablist/tab/tabpanel、方向键/Home/End、跳转主内容、统一 focus-visible；弹层具备 dialog 语义、初始焦点、Tab 约束、Escape、焦点归还和草稿保护；顶栏与页签自适应；问答侧栏在窄屏变为选择器；统一 CSS 令牌、消息类名、按钮热区和 reduced-motion；覆盖 1280×820、960×640、768px、390px、320px、深浅主题、200% 缩放和同步错误横幅。

**阶段 3：审批安全闭环**

区分选择和决定；增加状态筛选与复选框；批量上限 100；按会议全批/全拒先展示范围；依据与 route 由服务端判断；保留单条批准/拒绝/改回/仅保存/保存并批准；唯一写回入口是“检查并写回”；预演和确认 action 分开；apply 返回 `applied/rejected/failed`；部分失败、unknown、撤销边界准确可见；拒绝在应用后才归档。

**阶段 4：今日与导入回执**

保持“简报头部与捕捉 → 日程/任务 → 折叠建议/最近完成 → 审批摘要 → 项目推进”的顺序；区分本地快照读取与重新生成；导入显示文件名、大小、处理/跳过/失败/候选数量和 estimate；限制 `.md/.txt`、非空、10 MiB；多文件明确提示；关闭不取消请求；部分失败可重试；任务完成提供文字确认；可见页面读取业务状态，隐藏页面暂停，不能自动生成简报或写飞书。

**阶段 5：项目列表与详情**

搜索同时匹配规范 ID 和显示名；分开类型、工作台状态、同步提示、活动日期和实质状态日期；项目列表使用平面行；详情保留五个档案区块和时间线；从项目页/今日进入详情有返回路径并恢复位置；日志/产物独立草稿；产物保存后再预览状态摘要，确认后才写状态；状态失败不重复保存产物；归档/恢复明确资料保留。

**阶段 6：第二大脑与证据阅读**

保留 10 会话上限、6 轮追问、项目范围、重命名和删除；回答呈现 summary/facts/conflicts/suggestions/unanswerable；实际引用与仅召回材料分开；问答失败不进入历史；各会话保存自己的输入和范围；来源点击打开 vault 范围内只读面板；拒绝绝对路径、路径穿越、越界符号链接、非知识文件和超大正文；历史 HTML 兼容，不新增自动写回。

**阶段 7：指南、设置收敛与交付**

指南提供离线目录、搜索、无结果清除和错误到章节的路径；设置保留四张白话卡和高级维护折叠；按真实 provider/OAuth 状态区分未配置、已配置/已授权、验证失败、需重新授权；构建同步指南；最后运行自动测试、真实界面验证、构建身份校验，并明确未执行的 App/WKWebView/真实外部服务门。

## 3. 初始审计问题 U01–U19 的当前状态

| 编号 | 初始问题 | 当前状态 |
|---|---|---|
| U01 | 捕捉失败仍清空输入 | 已修复并有前端/后端回归覆盖；真实失败网络场景尚未用浏览器复现 |
| U02 | 刷新失败仍提示成功 | 已修复；部分读取失败可见并保留旧数据，真实断网/局部失败界面仍待验收 |
| U03 | 写回确认存在重复请求路径 | 已修复为单一监听路径；需要真实浏览器网络面板或 mock 端点确认一次点击一次请求 |
| U04 | 应用可绕过预演 | 已修复；真实 CUA 已看到零写入预演，没有点击确认应用 |
| U05 | 批量范围与资格不清 | 已完成：状态筛选、复选框、当前选择范围摘要、切换筛选清空选择、按选择批量决定；资格过滤、全批/全拒和 100 条限制保持 |
| U06 | 部分失败被包装为整体成功 | 已修复结构化汇总与状态标题；真实部分失败场景尚未跑 |
| U07 | 外部写回状态失败静默 | 已修复为审批页可见错误；真实外部状态读取失败尚未连浏览器验证 |
| U08 | “审批已清空”过度承诺 | 已修复为“无待确认项”，同时保留已批准/失败/unknown 提示 |
| U09 | 导入回执未落实 | 已完成多文件持续收据、成功/部分/失败/处理中状态、details/estimate、软预算提示、关闭重开和重复导入幂等语义；CUA 已真实打开/关闭/重开抽屉，本地隔离 API 已返回模型未配置、类型错误、空文件错误；原生文件面板选中仍受 CUA 接口限制，真实模型链路未跑 |
| U10 | 草稿与焦点保护不完整 | 常规弹层、问答、审批、日志/产物及同步冲突详情已接入统一关闭保护、初始焦点、Tab 约束、Escape 和返回焦点；CUA 已观察冲突初始焦点、预检和 Tab 环，冲突选择按 workspace 保存；原生确认框后的稳定返回焦点仍不作为本轮全部通过 |
| U11 | 来源不能真正打开 | 已完成 vault 范围只读来源面板；真实审批候选来源点击尚未在有候选数据下验证 |
| U12 | 问答丢失结构化信息 | 已完成结构化回答、冲突、无法作答、实际引用/仅召回展示；未做真实模型场景 |
| U13 | 项目搜索与显示名不一致 | 已修复并有纯渲染测试；详情改为项目页内渲染，返回会恢复查询/筛选/滚动上下文；CUA 已验证中文显示名搜索值恢复，以及今日 → 详情 → 返回今日的焦点恢复；项目页路径返回焦点仍需单独稳定复测 |
| U14 | 项目状态语义混杂 | 已拆分类型、工作台状态、同步提示、活动日期和实质更新日期；完整状态组合仍需真实资料矩阵 |
| U15 | 产物保存直接覆盖当前状态 | 已修复为保存产物 → 预览摘要 → 用户确认 → 状态写入，并有契约测试；状态写入失败重试尚未真实执行 |
| U16 | 窄屏与键盘支持不足 | 已完成基础 tab/focus、窄屏问答选择器和通用弹层；CUA 复测 1280/960/768/390/320 五档无整体横向溢出，并验证六页签 Home/End/方向键；Chrome 原生 200% 缩放、浅色主题、reduced-motion 和原生 App 仍未验收 |
| U17 | 视觉重复与 CSS 串扰 | 已完成主要 CSS/消息类名/列表平面化收口；还需系统化视觉矩阵检查，不做无依据的重设计 |
| U18 | 部分文字对比不足 | 主要颜色和状态徽标已收口；尚未做深浅主题/200% 缩放的对比度与可读性实测 |
| U19 | 文档承诺与代码不一致 | 产品说明、使用指南、内置 `web/src/guide.md` 已对齐；后续改动必须同步产品说明和构建指南 |

## 4. 已完成的代码与验证证据

### 已完成的可靠性与 UX/UI 改造

- 捕捉失败保留原文，请求期间新输入不会被旧响应清除。
- 读取失败保留旧数据并显式提示；同步横幅可重新读取。
- 审批决定和实际写回分离；“检查并写回”显示零写入预演；apply 结果按完成/部分完成/需处理区分。
- 审批页支持全部/待确认/已批准/已拒绝筛选、待确认复选框和当前选择摘要；按选择批量决定仍只调用 `/api/review/batch`，批准继续排除缺依据/缺落点候选，并保留 100 条限制。
- 批量批准只纳入有依据和落点的候选；全局 inbox 与个人日程不被错误禁用；单批 100 条上限保留。
- external action 的失败和 unknown 可见，unknown 不自动重试。
- 导入抽屉有持续结果容器，显示文件、大小、状态、详情和 estimate。
- 导入抽屉保留多条收据，显示成功/部分完成/失败/处理中，按顺序处理多文件；关闭后重开保留当前收据，重复已完成资料返回幂等跳过说明且不重复调用模型。
- workspace-scoped 草稿、workspace generation、请求序号、弹层焦点初始化和返回焦点已接入主要路径。
- 证据来源通过 vault 范围 API 只读打开并做路径安全校验。
- 问答结构化回答、冲突、建议、无法作答、实际引用和仅召回材料分开展示。
- 项目显示名搜索和“未发现同步提醒”语义已修复；日志活动与实质状态更新时间分离。
- 项目详情已从通用弹层收口到项目页内，返回按钮区分返回今日/项目列表，并保留查询、筛选和滚动上下文；本轮 CUA 已验证项目页中文搜索恢复和今日入口返回焦点。
- 产物状态同步增加最终摘要预览；指南本地目录/搜索和设置连接状态语义已完成。
- 最近修复设置页 `minmax(0, 1fr)`、自动化控件换行、checkbox/radio 宽度和横向溢出；本轮补充 900px/380px 顶栏收缩规则，避免 768/320 页面整体溢出。

### 实际验证

- 当前 HEAD：`cb1bd34`（`main` = `origin/main`）；本轮验证未执行真实外部写回。
- 本轮覆盖率门：`uv run --no-sync pytest --cov=summit_workbench --cov-report=term-missing --cov-fail-under=80 -q` 通过，`840 passed, 1 skipped, 5 warnings`，总覆盖率 `81.12%`。
- 本轮 `cd web && ./node_modules/.bin/tsc --noEmit`：通过；307 个源码文件无错误；`uv lock --check`、`uv run --no-sync python scripts/secret_scan.py`：均通过。
- 本轮 `bash scripts/test-native-updates.sh`、`bash scripts/test-native-automation.sh`：均通过；更新协调器测试夹具补充合成 workspace compatibility marker，未改变生产 Swift 代码或安全 fail-closed 语义。
- 本轮 `uv run --no-sync pytest -q tests/integration/test_packaged_app.py -m integration`：`1 skipped`；因未设置 `WB_PACKAGED_APP`，packaged App smoke 未执行，不能替代真实 App/WKWebView 验收。
- 本轮静态产物重建与 `node web/scripts/verify-build.mjs src/summit_workbench/webapp/static`：通过；身份为 `v2026.09.10-cb1bd34-ebdc777c`。
- 本轮 CUA 浏览器通道连续两次超时并自动重置，未取得新的真实页面状态；只保留此前已取得的隔离 Chrome 证据，不将本轮 CUA 记为通过。

- 本次最终 `uv run --no-sync pytest -q`：840 passed，1 skipped，5 warnings。
- `uv run --no-sync pytest -q tests/contract/test_web_route_contract.py tests/unit/test_web_security.py`：12 passed，2 warnings。
- `uv run --no-sync pytest tests/contract/test_web_route_contract.py`：1 passed。
- `uv run --no-sync ruff check .`：通过。
- `uv run --no-sync ruff format --check .`：394 个文件已格式化。
- `uv run --no-sync mypy`：312 个源码文件无错误。
- `npm --prefix web run test:frontend`：build identity、feature contract、项目/审批纯渲染、浏览器交互契约全部通过。
- `npm --prefix web run build`：通过；本次静态产物身份为 `v2026.09.10-cb1bd34-ebdc777c`。
- `node web/scripts/verify-build.mjs src/summit_workbench/webapp/static`：通过。
- `git diff --check`：通过。
- CUA 既有真实本地 Chrome：今日、审批、第二大脑、项目、指南、设置主流程可打开；导入抽屉、项目线视图、指南搜索、问答范围切换、设置高级区可开关；审批预演显示 `DRY-RUN（零写入）`，设置页及高级区 `scrollWidth=clientWidth`。
- 本轮隔离真实 Chrome：合成审批资料完成状态筛选、待确认复选框、选择摘要、按选择批量批准以及切换筛选清空选择；合成 Git 分叉显示 `diverged-protected` 横幅，冲突详情初始焦点落在人工选择、临时预检显示通过，项目详情为页内区域；今日入口返回焦点已观察。
- 本轮冲突弹层真实观察：选择“保留本机”后按 Escape，浏览器弹出未保存草稿关闭确认；Tab 从末按钮回到人工选择，取消确认后弹层保持打开，确认后弹层关闭。未点击恢复写回；冲突包下载与原生确认框后的稳定返回焦点不作为通过。
- 本轮隔离真实 Chrome 响应式观察：`1280×820`、`960×640`、`768×640`、`390×700`、`320×700` 五档 `body/document scrollWidth` 均无整体溢出；当前 CUA 窗口实际为深色主题，未切换浅色/系统 reduced-motion，Chrome 原生 200% 快捷键在扩展通道无效，未宣称通过。
- 本轮隔离真实导入观察：导入抽屉关闭后可重开；本地 API 接收合成 Markdown/TXT/PDF/空文件并分别返回模型未配置、类型不支持、空文件等明确回执。CUA `filechooser.setFiles` 返回 `Not allowed`，因此没有把浏览器原生选中文件或真实页面导入回执写成通过。

### 本轮四项增量的完成记录

- U05：`web/src/features/review/render.ts`、`web/src/features/review/types.ts`、`web/src/legacy-main.ts` 和前端测试增加状态筛选、待确认选择、范围摘要及按选择批量决定；用户可见变化是选择范围清楚，切换筛选自动清空，资格/100 条限制/预演写回边界不变。
- U10：`web/src/legacy-main.ts` 让同步冲突详情、加载失败和预检重绘统一经过 dialog 激活；人工选择按 workspace 保存，稍后处理走关闭保护，成功恢复后清理；合成冲突 workflow/API 回归已通过。
- U13/U14：`web/src/features/projects/render.ts` 与 `web/src/legacy-main.ts` 将详情放入项目页，增加状态筛选和返回上下文，恢复查询/筛选/滚动；未改 `activity_at`/`updated` 语义。
- U09：`web/src/features/today/types.ts`、`render.ts`、`index.ts`、`legacy-main.ts` 和 `src/summit_workbench/webapp/legacy_app.py` 支持多条导入收据、部分失败状态、软预算提示和幂等重复跳过；新增纯渲染/API 测试。
- 本轮测试：前端契约/纯渲染/构建产物通过；最终 `uv run --no-sync pytest -q` 为 840 passed、1 skipped、5 warnings；route/security 为 12 passed、2 warnings；最新构建身份为 `v2026.09.10-cb1bd34-ebdc777c`。

### 明确未执行

- 没有点击“确认应用（写回）”，没有执行真实审批写回。
- 本次审批筛选增量已在隔离真实 CUA 浏览器验证筛选切换、复选框、选择摘要和按选中批量批准；仍未完成网络层“一次点击一次请求”证据及 0/1/100/101 条矩阵。
- 本轮隔离 CUA 的合成 Git 分叉已显示保护横幅并打开冲突详情；人工选择、只读临时预检、Tab 约束、Escape 未保存保护、取消保持弹层和确认关闭均已观察；未点击恢复提交，冲突包下载与原生确认框后的稳定返回焦点不作为通过。
- 没有执行真实模型调用、真实 DeepSeek API、真实 Feishu OAuth、任务/日历写回或真实远端 Git 凭据验证；浏览器原生文件选择器因 CUA `Not allowed` 未完成，实际 API 的合成错误回执已验证。
- 没有替换已安装 App、执行独立 WKWebView 或 packaged App 黑盒 smoke。
- 320/390/768/960/1280 已在隔离 Chrome 验证无整体溢出；尚未完成 Chrome 原生 200% 缩放、浅色主题、系统减少动态效果的全矩阵验收。
- CUA 测试留下 1 个空问答会话，仅在浏览器本地状态中，不在 vault/飞书中；删除动作因需要 GUI 确认而没有执行。

### 当前续测记录（2026-09-10，最新事实）

- 当前仍为 `main`；本阶段运行时代码基线为 `4abe7fb`，最新静态 frontend build 为 `v2026.09.10-4abe7fb-350853f1`，其后仅有交接记录/构建记录提交，没有改变运行时代码。
- 在隔离 `HOME`、隔离 workspace/vault 和 `127.0.0.1:8798` 上，CUA 已真实完成：onboarding 新建工作台并跳过模型/飞书后重启进入工作台；设置高级维护默认折叠和展开；六页签 Home/End/方向键巡航；审批状态筛选、复选框、切换筛选清空选择和单选批量批准；中文显示名与 `·` 特殊字符搜索；项目详情页内打开、返回查询与入口焦点、归档/恢复；导入抽屉关闭重开以及两个合成 `.md/.txt` 文件的原生多文件选择。
- 本轮 CUA 发现两个实际问题并已小步修复：320px 设置页自动更新标签造成 4px 页面溢出（`web/src/style.css`）；项目详情返回时命中隐藏祖先中的重复入口，焦点落到 `body`（`web/src/legacy-main.ts`）。两处均先补 `web/scripts/test-browser-contract.mjs` 断言，旧代码先失败，修改后契约通过。
- 响应式结果：`1280×820`、`960×640`、`768×640`、`390×700`、`320×700` 页面级 `body/document scrollWidth` 均等于 client width；320px tablist 内部横向滚动仍是预期行为。页签键盘循环实际结果为 `End→设置`、`ArrowRight→今日`、`ArrowLeft→设置`、`Home→今日`。
- 导入结果：IAB 的原生 file chooser 可用，`multiple=true`，两个合成文件均得到“模型未配置”失败回执；关闭重开保留两条回执。这证明文件选择和失败回执闭环，但不证明模型成功、部分失败、软预算或完成导入幂等。
- 项目结果：修复后项目页返回稳定聚焦到中文项目入口并保留查询值；本次 fixture 高度等于视口，滚动位置恢复没有形成可观察位移，继续记为未验证。审批按钮结果已通过 CUA 观察，但通道没有可靠的 POST 计数证据，不能将“一次点击一次请求”记为通过。
- 导入抽屉焦点续测：在同一隔离 IAB 中打开抽屉并点击关闭，焦点稳定回到 `#btn-import-meeting`；再次通过触发按钮切换关闭也保持该结果。该修复只涉及关闭后的可用性与键盘连续性，不旁路导入 API 或改变回执语义。
- 提交后隔离 CUA 复核：在 `127.0.0.1:8798` 重新加载已推送代码，设置页高级与维护保持默认折叠，展开后四个高级分区可见；项目页内详情返回后焦点回到中文项目入口；导入抽屉关闭后焦点回到触发按钮。未执行在线健康检查、令牌提交、模型调用或外部写回。
- 自动门禁（本阶段代码/产物）：`npm --prefix web run test:frontend`、`cd web && ./node_modules/.bin/tsc --noEmit`、`npm --prefix web run build`、`node web/scripts/verify-build.mjs src/summit_workbench/webapp/static`、`git diff --check` 均通过；构建身份 `v2026.09.10-cb1bd34-60122c81`。文档修改完成后已复跑全量 Python/route/security/coverage、ruff、format、mypy、native tests：`840 passed, 1 skipped, 5 warnings`，coverage `81.12%`；packaged App 条件仍为 skip。
- 本阶段代码/产物门禁：前端契约、TypeScript、生产构建与产物校验均通过；构建身份 `v2026.09.10-a07f1bc-350853f1`。全量 Python/原生门禁已通过，覆盖率为 `81.12%`；packaged App smoke 明确为 skip。
- 提交后合成定向门禁：冲突/导入/API/安全 `80 passed, 2 warnings`；审批/项目/工作区 `58 passed, 1 warning`；会议/onboarding `26 passed, 1 warning`；前端契约、纯渲染和浏览器交互契约全部通过。新的 CUA 会话未提供 viewport 能力，未新增宽度矩阵数字；既有五档页面级无溢出证据仍有效。

### 2026-09-11 继续复核

- 全量门禁再次通过：`840 passed, 1 skipped, 5 warnings`，覆盖率 `81.12%`；route/security `12 passed, 2 warnings`；前端、TypeScript、ruff、format、mypy、锁文件、密钥扫描、原生更新/自动化测试全部通过。
- 最新静态产物 `v2026.09.10-4abe7fb-350853f1` 已重建并通过 `verify-build.mjs`；它对应最近运行时代码提交 `4abe7fb`，之后的变更仅为交接文档记录。
- 隔离 CUA 真实结果：设置页显示高级与维护默认折叠；从设置重新打开 onboarding，跳过模型/飞书后进入“设置完成”，再回到工作台；六页签 `End → 设置`、`ArrowRight → 今日`；导入抽屉关闭后焦点回到 `#btn-import-meeting`。全程未连接外部服务、未提交凭据、未执行模型或写回。
- 本次只读/本地测试仍使用临时 workspace/vault；CUA 未提供 viewport 控制能力，因此没有把本次新会话写成新的 200%/宽度证据。

### 2026-09-11 文档资产整理

- 按保守方案归档 9 份历史/非权威资料到 `docs/archive/`，包括早期背景、旧架构图、已完成计划、旧验收 runbook、静态设计预览和 ponytail 审计；没有删除内容。
- 已保留当前产品规格、操作说明、桌面 App/发布说明、ADR、当前验收记录和本轮实施/交接档案；README、PROJECTDESC、PRD、相关 ADR、产品说明、CHANGELOG 与预览脚本的路径引用已同步。
- `docs/archive/README.md` 是归档入口，明确历史文档不覆盖当前产品规则；`web/scripts/preview-brief.mjs` 的输出路径已固定在归档目录，防止后续生成重新污染当前设计目录。

### 本阶段明确仍未验证

- Chrome 原生 200% 缩放、浅色主题、系统 reduced-motion、packaged App/WKWebView。
- 审批 `0/1/100/101` 条完整真实矩阵、缺 route/global inbox/个人日程的浏览器网络证据、一次点击一次请求的可靠计数；没有点击“检查并写回”或任何真实外部写回。
- 冲突包导出下载事件的确定证据、原生确认框关闭后的稳定返回焦点；既有合成分叉的只读预检、人工选择校验、Tab 约束、Escape 草稿保护仍不扩展为恢复写回通过。
- 导入成功/部分失败/软预算/幂等完成导入；当前只完成原生选择和模型未配置失败回执。真实模型、飞书 OAuth、任务/日历写回、真实用户文件和真实远端 Git 均未执行。
- 问答冲突/无法作答/模型失败/来源 404/非 Markdown/超长/路径穿越/符号链接越界/workspace 隔离的完整真实浏览器矩阵；本阶段未引入 mock 模型来伪造成功链路。

## 5. 后续 agent 必须按此顺序工作

### A. 实现状态

本轮四项实现均已完成：审批筛选/按选择批量决定、同步冲突弹层统一保护、项目页内详情/返回上下文、导入多文件持续回执/幂等语义。后续只补未验证证据，不扩展产品范围。

### B. 再完成真实验证

1. 继续使用隔离测试工作区和合成资料，不连接真实飞书或真实工作 vault 做写操作。
2. 已完成 1280×820、960×640、768、390、320 的无溢出复测；剩余仅补 Chrome 原生 200%、浅色主题、reduced-motion 和未稳定的返回焦点/文件选择器证据。
3. 对审批使用 0/1/100/101 条、缺依据、缺 route、global inbox、个人日程、部分失败和 unknown fixtures；确认一次点击只发一次请求，旧预演失效后不能直接应用。
4. 对项目验证中文显示名、特殊字符、归档/恢复、日志不改变 `updated`、产物成功而状态失败不重复保存、从今日进入后返回位置。
5. 对问答验证冲突、无法作答、模型失败、来源 404/非 Markdown/超长/路径穿越/符号链接越界、workspace A 不能读 workspace B。
6. 对导入验证完整回执和页面重绘/关闭重开状态保持；当前抽屉重开已通过，原生文件选中受 CUA 限制。
7. 只有用户明确允许且测试环境隔离时，才考虑真实外部服务；任何真实写回仍需在动作前明确确认。

### C. 每一阶段完成后的固定门禁

- 运行与变更相关的单元、route/security、前端契约/纯渲染测试。
- 运行 `npm --prefix web run build`，再运行 `node web/scripts/verify-build.mjs src/summit_workbench/webapp/static`。
- 运行 `ruff check`、`ruff format --check`、`mypy`、`git diff --check`。
- 使用 CUA 做真实浏览器操作验证；源码契约测试不能替代点击、键盘和布局验收。
- 更新 `docs/implementation/V0-4-4-UX-UI-INCREMENTAL-IMPLEMENTATION.md` 和本档案的状态、证据、限制、下一步。
- 不要把历史 build 9、历史 unit 数字、源码正则或截图占位当成新一轮真实验证。
- 只在用户明确要求或已授权时提交/推送；不要自动替换 `/Applications` 中的 App。

## 6. 给下一个 agent 的最短判断标准

完成标准不是“页面看起来更高级”，而是：用户不会因失败丢掉输入，不会把批准误认为已经写回，不会因重复点击创建两次外部动作，不会看不懂部分失败/未知结果，不会失去草稿或焦点，不会无法核查来源；同时在窄屏、键盘、错误状态和真实浏览器中仍能完成主流程。任何没有实际执行的真机、WKWebView、模型、飞书或文件导入验证都必须明确写为“未验证”。

## 7. 2026-09-11 隔离 CUA 验收快照（覆盖前文同项的较新事实）

- 环境：临时 `HOME`、临时 workspace/vault、临时 bare Git remote、合成审批/冲突/导入资料和本地 In-app Browser；不含真实凭据、真实飞书、真实模型或真实业务数据。运行时代码基线为 `cb1bd34`，本次没有运行时代码改动。
- 已通过：五档 `1280×820`、`960×640`、`768×640`、`390×700`、`320×700` 页面级无整体横向溢出；六页签标签与 Home/End/方向键巡航；设置四组内容和高级维护默认折叠；项目页内详情、今日返回焦点、中文/特殊字符搜索、归档/恢复；审批筛选、选择摘要、筛选切换清空、按选中批量决定、资格禁用和零写入预演；同步分叉横幅、冲突详情、人工选择、只读预检和 Tab 环；导入抽屉重开、原生多文件选择、模型未配置失败回执和跨页签保留；指南无结果/清除；问答模型失败与失败问题不进下一轮上下文。
- 冲突关闭保护：有未保存选择时 Escape 先出现放弃草稿原生确认，没有直接丢弃；原生确认框处理后的稳定返回焦点因 CUA 通道超时，不宣称通过。冲突恢复确认从未点击。
- 冲突导出：已尝试但未取得 In-app Browser 的确定下载事件，记录为“失败/未验证”，不可写成导出通过。
- 仍未验证：Chrome 原生 200% 缩放、浅色主题、系统 reduced-motion、packaged App/WKWebView；审批 0/1/100/101 完整矩阵和一次点击一次请求的网络计数；项目可移动滚动位置；导入成功/部分失败/软预算/成功幂等重复；真实模型、Feishu OAuth、任务/日历或 Git 写回；来源和 workspace 隔离的完整真实浏览器异常矩阵。
- 既有自动门禁不变：全量 `840 passed, 1 skipped, 5 warnings`、覆盖率 `81.12%`、route/security `12 passed, 2 warnings`，前端/TypeScript/构建/产物校验/ruff/format/mypy/diff check 全部通过；packaged App skip 仍未执行。

这份快照优先于前文同项的“尚未完成 CUA”描述；它只更新证据状态，不改变产品边界、写回保护、workspace generation、锁、原子写、outbox、迁移和重试语义。

## 8. 2026-09-11 终审级审核与小步优化快照（覆盖前文同项的较新事实）

- 环境与身份：分支 `main`，最近运行时代码基线 `cb1bd34`。逐轮提交：R01–R08 → `ee561f5`（`a9bbc4a..ee561f5`）；R09–R12 → `ecafdb0`；R13–R14 见下方第三轮。第三轮构建身份：`v2026.09.11-ecafdb0-a107073b`（`npm --prefix web run build` + `verify-build.mjs` 通过）。未执行真实外部写回、真实模型、飞书 OAuth、真实远端 Git 或冲突恢复提交。
- 三轮共记录 14 个问题（P1×2、P2×9、P3×3），全部做了小步修复。逐项证据、根因、修复、文件、测试与回归风险见实施记录 `V0-4-4-UX-UI-INCREMENTAL-IMPLEMENTATION.md` 的三节记录。

### 已修复（用户可见变化）

**第一轮 R01–R08（已推送 `ee561f5`）**

1. **P1 项目详情过期响应**：返回/切换详情后，在途读取结果不再把旧详情推回页面或抢焦点；先返回今日后切到项目页也不会直接看到旧详情。（`web/src/legacy-main.ts`）
2. **P1 写回重复提交**：审批弹层「确认应用（写回）」增加单次在途保护并禁用按钮；决定变化后旧预演失效，必须重新「检查并写回」。预演 → 确认 → apply 的两步语义与服务端写回边界不变。
3. **P2 撤销弹层焦点/语义**：顶栏「↩ 撤销」改为共享 dialog 激活——初始焦点进入弹层、`role=dialog`/`aria-modal`、有关闭按钮、关闭后焦点回到 `#btn-undo`，并清掉上一个弹层的草稿标记以免 Escape 弹出无关确认。
4. **P2 设置页乱序渲染**：保存模型后的刷新不会被保存前的旧读取覆盖。
5. **P2 后台轮询**：60 秒刷新只在可见页运行，隐藏页暂停读取，回到前台立即补一次（版本 + 同步横幅）。
6. **P2 同步横幅读取失败**：横幅已显示保护态（如 `diverged-protected` 与「查看冲突详情」入口）时，一次读取失败不再静默隐藏，而是保留上次成功内容并提示「同步状态读取失败」+「重新读取」。
7. **P3 问答历史**：`/api/version` 省略 `workspace_id` 时，本地问答历史也会载入一次。
8. **P2 审批批量范围**：「一键拒绝过期项」显示实际条数（`（N）`），为 0 时不可点，title 说明不受当前筛选影响；执行仍走 `batchDecide`（100 条上限、只改决定）。

**第二轮 R09–R12（已推送 `ecafdb0`）**

9. **P3 外部写回状态乱序**：`/api/external-actions` 读取加请求序号，旧响应不再覆盖审批页的外部写回列表。
10. **P2 长文本提交提示**：捕捉/日志/产物正文超过后端 100,000 字符上限时本地拦截并说明「超过 10 万字上限（当前 N 字），请拆分后重试」；`normalizeApiError` 追加 envelope `details[0].msg`，其余校验失败也可诊断。
11. **P2 重复提交**：日志、产物、任务/会议行内编辑增加在途保护与按钮禁用，双击不再重复保存/重复 PATCH 飞书本体。
12. **P3 文档漂移**：PRD L51/3.1.5 的 `updated` 表述按现行实现改为 `activity_at`/`updated` 语义拆分。

**第三轮 R13–R14（本次续修，来源只读边界与截断语义）**

13. **P2 `/api/review/source` 目录收紧**：历史只读入口与 `/api/sources/read` 共用同一份知识目录白名单（`projects/ meetings/ logs/ artifacts/ inboxes/ daily/ reviews/ insights/` 或 `inbox.md`）；vault 内的 `_signals/`、`notes/` 等非知识路径现在返回 400。路由路径/方法与契约快照不变，行为只收紧。
14. **P3 `truncated` 语义**：`/api/sources/read` 新增 100,000 字符正文展示预算；超过时返回前 100,000 字符并置 `truncated: true`，前端「正文已截断」提示由此可达；>256 KiB 文件仍直接 413（用新测试锁定不放宽）。

### 验证范围（通过 / 失败 / 跳过 / 未执行）

- 通过：全量覆盖率门 `842 passed, 1 skipped, 5 warnings`、覆盖率 `81.14%`；route/security `12 passed, 2 warnings`；`npm --prefix web run test:frontend`（8 个脚本，含真实并发测试 `test-settings-render.mjs` 与真实单元测试 `test-api-error.mjs`）；`tsc --noEmit`；`npm --prefix web run build`；`verify-build.mjs`；`ruff check`；`ruff format --check`；`mypy`；`git diff --check`。
- 失败：最终状态无失败项。三轮新增断言/测试的每一项在修复前都实际失败（`test-browser-contract.mjs`、`test-review-render.mjs`、`test-settings-render.mjs`、`test-api-error.mjs`、`tests/unit/test_webapi.py` 的来源用例），作为复现证据；修复后全部通过。
- 跳过：packaged App smoke（未设置 `WB_PACKAGED_APP`）。
- 未执行：真实浏览器（CUA）点击/键盘/布局复测；Chrome 原生 200% 缩放、浅色主题、系统 reduced-motion；packaged App/WKWebView 黑盒；真实模型、飞书 OAuth、任务/日历写回、真实远端 Git；冲突恢复提交与真实审批写回。
- 边界：`test-browser-contract.mjs` 是源码级交互契约，**不是**真实浏览器测试；三轮都没有新增 CUA/浏览器证据，也不把源码断言写成浏览器通过。

### 仍未验证 / 待真实浏览器验收（交给下一个 agent）

- 第 4–7 节列出的全部未验证项保持不变。第三轮之后新增的可验项：来源面板在正文 100,000–256 KiB 时显示「正文已截断，以下内容仅供核查」且不崩；`/api/review/source` 对 `_signals/` 等非知识路径返回 400 的浏览器/网络层证据；以及所有 R01–R14 的交互断言在真实页面上的复验。
- 本节不改变产品边界、写回保护、workspace generation、锁、原子写、outbox、迁移与重试语义。

### 分支与提交状态

- 分支 `main`；`ee561f5`（R01–R08）与 `ecafdb0`（R09–R12）均已推送。
- 第三轮 R13–R14 改动与重建的静态产物（构建身份 `v2026.09.11-ecafdb0-a107073b`）按产品所有者指示随后提交并推送。

## 9. 2026-09-11 R08 修正、构建重建与人工验收终结快照（最新）

本节覆盖并 supersede 第 8 节中关于 R08、R02、构建身份和真实浏览器证据的旧状态；前文仍保留为历史记录。

- 当前身份：`main` 与 `origin/main` 均为 `046d940`（`fix(webapp): show expired review batch scope`），工作区干净。
- R08 修正：审批工具栏始终显示实际范围，包括无项时的「一键拒绝过期项（0）」；无过期项时原生 `disabled`，title 仍说明「当前 0 条」且范围不受筛选影响。修改文件：`web/src/features/review/render.ts`、`web/scripts/test-review-render.mjs`。
- 构建：在 `046d940` 上重新执行 `npm --prefix web run build` 与 `node web/scripts/verify-build.mjs src/summit_workbench/webapp/static`，构建身份为 `v2026.09.11-a851f70-1d8d7004`；静态入口已指向新 JS bundle，不再引用 `ecafdb0`。
- R02 真实浏览器/CDP 验收：临时 HOME/workspace/vault、临时 bare remote、本地 `127.0.0.1` 服务和 Chrome 页面；通过 Fetch 拦截并延迟 `/api/review/apply`，快速双击确认按钮只观察到 1 个请求，按钮立即禁用，最终仅返回一次合成完成结果，未触碰真实外部写回。
- R08 人工验收：本地临时验收页先观察「一键拒绝过期项（1）」可用且切换筛选后范围不变；再将唯一过期项截止日期改为未来日期，确认「一键拒绝过期项（0）」呈灰色，点击无提示、不出现「已批量更新」、待确认项保留。
- R02 人工验收：临时页完成零写入预演后双击「确认应用（写回）」；按钮立即禁用、无可见异常。事后检查临时 vault 仅有 1 条审批审计记录和 1 条 inbox 写入，没有重复结果；没有连接真实飞书、OAuth、模型或远端。
- 自动门禁：`npm --prefix web run test:frontend`、定向来源测试 `4 passed`、全量 `uv run --no-sync pytest -q` 为 `842 passed, 1 skipped, 5 warnings`；`verify-build.mjs` 与 `git diff --check` 通过。唯一 skip 仍为未设置 `WB_PACKAGED_APP` 的 packaged App smoke。
- 临时服务已停止；临时验收目录移入用户回收站，可恢复；仓库没有残留临时文件。

### 9.1 当前结论与仍需单独验收的边界

- R01–R14 中本次覆盖的 R02、R08 已有源码/构建/真实浏览器/人工证据，不再列为“待真实浏览器验收”。
- 本次人工 R02 写回只发生在临时 vault；真实模型、Feishu OAuth、任务/日历写回、真实远端 Git、冲突恢复提交仍未执行。
- packaged App/WKWebView、Chrome 原生 200% 缩放、浅色主题、系统 `prefers-reduced-motion` 和真实外部服务仍未验证；这些不能由本次本地 Chrome 或自动化测试替代。

## 10. 远端 CI 启用与门禁补强快照（2026-09-11，最新）

本节覆盖第 9 节及更早关于“远端 CI 未启动”的状态。

- 仓库已迁移到组织 `SummitYifeng/SummitWorkbench`。根因：Actions 分钟数按**仓库所有者**计费，
  `yifeng93` 个人账户额度耗尽且没有有效支付方式，而 Team 计划买在组织上；迁移后 CI 恢复，
  secrets、`release` environment 与 releases 均保留，本地 remote 已更新。
- 远端 CI 首次真实运行即暴露并修复一个缺陷（详见 ADR 0045「后续修订」与 CHANGELOG Unreleased）：
  macOS framework 版 Python 的 re-exec 使 `_same_server_executable()` 把活着的 server 误判为复用 PID，
  删除活着的 runtime 记录并绕过 `server_entry.py` 的重复实例保护。
- `packaged App smoke` 已接入 CI 的 arm64 构建矩阵；两个 workflow 的 action 升级到 node24 大版本，
  项目 Node 工具链 20 → 24。
- 当前 CI 全绿：workflow lint、macOS arm64 contract、macOS x86_64 负向 contract、quality-gate
  （844 passed / 1 skipped，覆盖率 81.19%）。
- **第 9.1 节列出的真实验收边界全部保持不变**：真实模型、飞书 OAuth、任务/日历写回、真实远端 Git、
  冲突恢复提交、WKWebView/原生 UI 黑盒、Chrome 原生 200% 缩放、浅色主题、reduced-motion，以及审批
  0/1/100/101 矩阵与网络计数，仍未验证。CI 里的 packaged smoke 只覆盖打包后的 server 与构建身份，
  **不替代**原生 App/WKWebView 黑盒验收；CI 转绿也不替代上述真实验收。
