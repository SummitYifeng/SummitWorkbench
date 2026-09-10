# SummitWorkbench 冗余审计与执行方案

审计日期：2026-09-10。基线：`050ec077a1a24226d7adc62df30314a2f6aae171`（v0.4.4）。

审计开始及测试结束时工作区均干净。本报告是本轮唯一新增文件，未实施代码优化。

## 结论与范围

使用 ponytail-audit，范围限于死代码、重复实现和未使用的抽象；不将正确性、安全性或性能审查混入删除任务。

对全仓文件树、Python/TypeScript/Swift 声明与引用、依赖清单、构建脚本、测试及相关 ADR 做静态筛查，再重点阅读候选项与真实入口。仓库共 478 个已跟踪文件；Python 源码 188 个文件、30,123 行；`legacy-main.ts` 3,446 行，`legacy_app.py` 3,470 行。不是逐行形式化证明，未对每个 CSS 选择器、动态调用或外部脚本使用情况做完备验证。

主要冗余是新功能替换后的旧实现和没有消费者的占位边界。建议先做行为不变的小规模清理：候选删除量约 360–400 行，考虑测试替换等新增内容后，净减约 300 行是规划估计，不是已完成统计。构建器可能已经消除了部分未使用前端代码，因此不承诺包体或速度同比改善。

## 审计发现（按可删除规模排序）

- delete: A1，删除失去入口的旧设置页及专属类型、渲染和保存辅助函数，约 180 行；保留实际接入的 `features/settings`。位置：`web/src/legacy-main.ts:1458`、`:1508`、`:1627`、`:1729`。
- delete: A2，删除未被调用的六步 `_onboarding_wizard_html`，55 行；继续使用现有 `render_onboarding_wizard`。位置：`src/summit_workbench/webapp/legacy_app.py:646`。
- delete: A3，删除四个没有仓库调用者的 Swift 方法，约 46 行；运行记录由现有 Python 写入路径维护，服务探测继续使用 `probe`。位置：`native/SummitWorkbench/RuntimeRecord.swift:46`、`:120`，`ServiceSupervisor.swift:298`，`ServiceClient.swift:45`。
- yagni: A4，删除四个前端空 feature 文件、五个后端空 router 文件及无消费者的 feature/prefix 常量，约 36–38 行；保留实际入口、真实路由和有行为的 feature。位置：`web/src/features/`、`src/summit_workbench/webapp/routers/`。
- delete: A5，移除编译器证实的多余导入、只写不读状态和局部变量，约 20 行；保留真正使用的渲染器、版本展示和焦点恢复实现。位置：`web/src/legacy-main.ts:26`、`:185`、`:205`、`:352`、`:3169`。
- delete: A6，删除无仓库消费者的 `build_identity`，18 行；保留 `WebBuildInfo`、`discover_build_number` 及当前版本响应。位置：`src/summit_workbench/webapp/build_info.py:223`。
- yagni: A7，删除零订阅者的 workspace 订阅设施，约 10 行；保留 workspace ID、generation、切换和 dispose 的实际语义。位置：`web/src/core/workspace-store.ts:3`、`:8`、`:22`、`:25`、`:31`。
- yagni: A8，删除运行记录清理函数中未读取的 `now`、`max_age` 参数及由此多余的导入，约 2 行净收益；保留依据进程身份判断的清理行为。位置：`src/summit_workbench/webapp/runtime.py:56`。

以上全部落地后的保守净减少预估（非硬性配额）：

net: -300 lines, -0 deps possible.

## 证据与精确边界

### A1：旧设置页

`renderSettings`（1720 行）调用 `renderSettingsFeature`；`legacyRenderSettings` 只有定义，没有调用。额外启用 TypeScript 未使用检查也报告该函数。

一并删除仅属于此不可达子图的：

- `ProfileSummaryPayload`、`ProfileListPayload`、`AutomationJobPayload`、`AutomationSettingsPayload`。
- `AUTOMATION_LABELS`、`WEEKDAY_LABELS`、`automationJobHtml`、旧 `httpsCandidate`。
- `legacyRenderSettings`、`saveAutomationForm`。

它们分布在多个不连续区段，不能按一个大行号范围删除。保留其中穿插的 `RemoteNormalizationPreviewPayload`、`AcceptancePreflightPayload` 和远端转换、预检函数。

旧页面曾提供移除 profile、schema migration、acceptance preflight、复制自动化摘要等入口。虽然旧渲染器不可达，但相关 action dispatcher、服务端 API、CLI 或原生路径需要独立判断。本轮保留这些处理器与 API，不把“新 UI 没有按钮”视为删除业务能力的授权，也不顺带恢复/重做 UI。

### A2：旧引导页

`_onboarding_wizard_html` 在仓库仅出现定义。restricted 首页实际导入 `webapp/onboarding_view.py` 的 `render_onboarding_wizard`。仅删除这个旧函数；保留 restricted app、onboarding API 和新版引导页。

### A3：Swift 无调用方法

具体为 `RuntimeRecord.writeAtomically`、`RuntimeRecord.processStartedAt`、`ServiceSupervisor.processStartDate`、`ServiceClient.isReady`。跨 native、tests、scripts、packaging 搜索未发现调用。两个日期方法为 private；另外两个方法不是框架委托回调。

必须保留 `RuntimeRecord` 解码、定位、读取、所有权判断、清理与终止服务逻辑，以及 `ServiceClient.probe`。`commandOutput` 仍被 `executablePath` 使用，不得级联误删。AppKit/WebKit 委托方法由框架调用，不能按文本引用次数删除。

### A4：占位边界

前端空文件：`features/{onboarding,sync,threads,workspace}/index.ts`，每个只有说明和字符串常量，无应用导入。另可删除 `projectsFeature`、`reviewFeature`、`settingsFeature`，保留这三个模块实际使用的导出和实现。

后端空文件：`webapp/routers/{feishu,threads,review,onboarding,sync}.py`，每个只有说明、`ROUTE_PREFIXES` 和 `__all__`。没有路由注册调用者。`routers/projects.py` 中未使用的 `ROUTE_PREFIXES` 及对应 `__all__` 条目也可清理，但不能删除项目路由实现。

`web/scripts/test-build.mjs` 与 `test-browser-contract.mjs` 存在要求占位文件存在或包含特定字符串的断言。同步修改这些断言：真实 API 用现有 route contract/onboarding 测试验证；真实渲染保持现有 render 测试。不要为了通过断言重新建立空文件。ADR 0035/0036 是历史决策记录，可补充本次收敛说明，不覆盖历史事实。

### A5：8 项 TypeScript 诊断

审计命令：`cd web && ./node_modules/.bin/tsc --noEmit --noUnusedLocals --noUnusedParameters`，返回 8 项诊断：

`briefCardHtml`、`projectsHtml`、`ReviewGroup`、`projectReturnFocus`、`versionStatus`、`fmtCost`、`legacyRenderSettings`、`activePath`。

只删除多余导入，不能删除导出的 `briefCardHtml` 或 `projectsHtml` 实现；今日页仍使用它们。`legacyRenderSettings` 已算入 A1，不重复计数。

`projectReturnFocus` 只有赋值；实际返回焦点使用 `projectFocusAfterRenderName` 和 `focusVisibleProjectLink`。删除旧变量及写入后，替换 `test-browser-contract.mjs:86` 要求出现旧变量名的断言，并复查与旧赋值表达式绑定的文本断言。保留返回项目列表时的查询、过滤、滚动与可见目标焦点恢复；不要仅删测试后声称行为通过。

`versionStatus` 只写不读，但 `setVersionStatus` 和 `versionStatusLabel` 用于展示，必须保留。`activePath` 的计算结果未使用，不应连带改动冲突弹窗。

### A6–A8：未使用辅助层

`build_identity` 未发现应用、脚本或测试调用；函数名相近的测试名称不是调用证据。删除前复查当前版本响应的实际调用链，保持输出字段不变。

`WorkspaceStore.subscribe` 没有订阅调用，只有测试对其存在作正则断言。可移除 `WorkspaceListener`、listeners 集合、通知循环、subscribe 及 dispose 中清空 listeners 的语句；保留 dispose 重置 ID 和递增 generation，保持请求失效与存储隔离行为。

`cleanup_stale_runtime_record` 的 `now`/`max_age` 不参与逻辑。现有测试通过 `max_age=timedelta(seconds=1)` 表达存活进程不能按年龄清理。去掉参数时应保留该场景：构造很旧但仍存活的记录，确认不删除。不要删掉测试的旧时间设置。只读引用检索不能保证仓库外的 Python 调用者不存在；若维护文档声明这些辅助函数为外部公共 API，则保留并记录，不强制完成行数目标。

## 暂不执行的候选与明确保留项

- `providers/feishu/calendar.py:list_events` 只发现 contract 测试调用；生产 `list_events_between` 使用 `list_event_instances`。列为二次核查候选，不计入收益、不交由本轮删除；需要确认旧日历查询能力是否仍属于支持面。
- `legacy_app.py`、`legacy-main.ts` 是真实运行主体，不是备份。将其全部拆分只是移动代码，不计为精简成果，本轮不做。
- SSR fallback、`/review`、`/ask` 等旧 HTML 路径仍注册，并由测试/无 SPA 场景使用；保留 `views.py` 与 `python-multipart`（上传及 Form 正在使用）。
- 两套 Git backend 分别服务开发/CLI 和打包生产，有 conformance 测试；保留 `GitRepo`、`GitBackend`、system/dulwich 及依赖。
- `FactsSource`、`Completer` 支撑隔离网络的测试注入；不为节约几行删除协议。
- JSONL、原子写、锁、outbox、脱敏、workspace scope、thread activity 迁移模式、HTTP 重试策略均有实际语义，不按文件大小或“看似包装层”删除。
- `runtime_record_path`、`lock_file_path` 等测试辅助入口不因生产引用少就列为死代码；装饰器注册的 FastAPI/Typer/Pydantic 函数也不适用单一引用计数规则。
- CSS、静态发布资源、旧数据迁移和 launchd 兼容脚本未取得足够删除证据；不纳入自动删除。
- 当前没有证据充分、可直接删除的依赖。不要把 httpx 替换为 urllib，或为追求零依赖手写现有库能力。

## 执行顺序

| 批次 | 工作内容 | 验收与退出条件 |
| --- | --- | --- |
| 0 | 核对基线和工作区，记录现有测试结果；如 HEAD 更新，对候选逐项重新核实 | 不重置用户代码，不默认回退到旧 SHA |
| 1 | A1、A2、A5：删除旧 UI 子图和未使用本地声明；同步相关行为测试 | 未使用检查无报错；前端测试、新旧入口与 route contract 回归通过 |
| 2 | A4、A6、A7、A8：收敛占位文件、辅助 API 和测试假约束 | 不增加空包装或通用框架；workspace generation、版本载荷、运行记录行为不变 |
| 3 | A3：删除 Swift 无调用方法 | 原生源码 typecheck/编译通过；现有 native contract 与适用行为测试通过 |
| 4 | 将 noUnusedLocals/noUnusedParameters 写入 tsconfig；在 CI 明确执行现有 test:frontend；完成质量门及交付 | 所有适用检查通过，记录实际净行数与保留项，不要求凑够 300 行 |

按批次组织可独立审查的改动。若单项证据被新代码推翻，则保留该项、说明原因，继续其余范围，不扩展成产品重新设计。

## 已运行与后续验收

本轮已运行：

- `npm --prefix web run test:frontend`：通过。包括构建标识、渲染测试、源码交互契约；后者并非真实浏览器端到端测试。
- 上述 TypeScript 额外未使用检查：8 项已列出；这是审计发现，不能描述为质量门通过。
- Python 定向回归：92 passed，1 条 Starlette/httpx 弃用警告。覆盖下列 8 个文件。

```sh
.venv/bin/python -m pytest -q \
  tests/contract/test_web_route_contract.py \
  tests/unit/test_webapp.py \
  tests/unit/test_webapi.py \
  tests/unit/test_onboarding_wizard.py \
  tests/unit/test_webapi_onboarding.py \
  tests/unit/test_runtime_record.py \
  tests/unit/test_native_panel_contract.py \
  tests/contract/test_feishu_calendar.py
```

本轮未执行全量 pytest、Swift 编译、生产重建或真实浏览器行为测试。实施后要求：

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest --cov=summit_workbench --cov-report=term-missing --cov-fail-under=80 -q
npm --prefix web run test:frontend
npm --prefix web run build
node web/scripts/verify-build.mjs src/summit_workbench/webapp/static
uv lock --check
uv run python scripts/secret_scan.py
```

Swift 变更需对生产 Swift 源文件集合执行适用的 typecheck/编译，按仓库脚本的目标平台和 frameworks；只跑源码文本断言不足以验收。涉及构建脚本时检查脚本副作用，不安装或替换用户现用 App。

前端浏览器验收使用临时工作区和本地模拟数据，覆盖设置保存、自动化配置、项目详情返回焦点、工作区切换后的旧请求失效、冲突弹窗关闭焦点、新版引导页。优先复用现有工具；不为此次删除新建大型测试框架。若缺乏浏览器验收条件，明确列出未验证项，不能将源码正则断言当作交互结果。

前端 build 会更新已跟踪 static 产物和 build-meta。只由构建脚本生成并校验，不手改打包文件、不将压缩产物行数计入源码净收益。不盲目更新路由快照让测试通过；本轮预期 API 契约不变。

交付应包含：逐项处理状态、实际删除/新增源码行数、依赖变化（预期 0）、测试证据、保留项和未验证项。不发布、不推送、不连接真实飞书/模型执行写入，不迁移用户数据。
