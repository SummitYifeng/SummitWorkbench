# `web/src/legacy-main.ts` 拆分蓝图

- 文档性质：**只做方案，不改代码**。本轮不修改 `legacy-main.ts` 或任何 `.ts` / `.py` / `.swift` / 脚本文件，不搬目录、不改包结构、不重命名模块。
- 依据：`docs/implementation/DELIVERY-CLEANUP-HANDOFF.md` §9.3「`legacy_app.py` 与 `legacy-main.ts` 的拆分蓝图——按现有边界（`webapp/routers/*`、`web/src/features/*`）给出目标模块、依赖方向、迁移顺序与风险点」。
- 基线事实：`web/src/legacy-main.ts` 共 **3346 行**（`wc -l`）；顶层 `function` / `async function` **103** 个，顶层 `let` / `const` **63** 个，`interface` / `type` **32** 个；唯一导出为 `mountLegacyWorkbench`（3315-3346）。
- 所有行号均为对当前工作树该文件的实测值（`sed -n` / `grep -n` 逐段核对），不是估计值。若文件后续变动，需重新测绘。

---

## 1. 现状测绘

### 1.1 头部与外部依赖

`legacy-main.ts` 第 1-33 行是全部 import，共 10 个相对模块 + 1 个 CSS + 1 个 `?raw` 文本：

| 行 | 导入 | 用途 |
| --- | --- | --- |
| 1 | `./style.css` | 全局样式（`main.ts:1` 也导入同一份，Vite 去重） |
| 3 | `./api/client` → `createApiClient` | HTTP 客户端工厂 |
| 4 | `./core/workspace-store` → `workspaceScopedKey`、`workspaceStore` | workspace 作用域键与代际 |
| 5 | `./lifecycle/connection` → `mutation`、`deferReloadUntilMutationsComplete`、`isMutationInFlight`、`setMutationIdleHandler` | 写回在途保护与更新前等待 |
| 6-16 | `./lifecycle/drafts` → `clearDraftSnapshot`、`clearEntityDraft`、`loadDraftSnapshot`、`loadEntityDraft`、`saveDraftSnapshot as persistDraftSnapshot`、`saveEntityDraft`、类型 `DraftSnapshot`、`ReviewDraftFields` | 草稿持久化 |
| 17-23 | `./lifecycle/version` → `canonicalPanelUrl`、`CLIENT_BUILD`、`shouldPreventReload`、`validateVersionPayload`、类型 `VersionPayload`、`VersionStatus` | 版本握手 |
| 24 | `./lifecycle/native-bridge` → `notifyClientReady`、`sendNativeMessage` | 原生 App 桥 |
| 25 | `./md` → `esc`、`mdToHtml` | HTML 转义与 Markdown 渲染 |
| 26 | `./brief-card` → 类型 `BriefData` | 结构化简报类型 |
| 27-28 | `./features/projects` → `projectDetailHtml`、`projectDisplayName`、`projectsListHtml` + 类型 `ProjectListFilter`、`ProjectState`、`ProjectView` | 项目 feature（**已抽出**） |
| 29-30 | `./features/review` → `reviewHtml` + 类型 `ExternalAction`、`ReviewEntry`、`ReviewFilter`、`ReviewPayload` | 审批 feature（**已抽出**） |
| 31 | `./features/settings` → `renderSettings as renderSettingsFeature` | 设置 feature（**已抽出**） |
| 32 | `./features/today` → `mountToday` + 类型 `ImportReceipt` | 今日 feature（**已抽出**） |
| 33 | `./guide.md?raw` → `guideMd` | 使用指南内置文本 |

`./guide.md` 是**构建生成物**（见 §2.4），不是源码。

### 1.2 逻辑簇清单（27 簇，覆盖 3321 行，逐簇行区间已核对）

| # | 簇名 | 行范围 | 行数 | 关键符号 | 职责 |
| --- | --- | --- | --- | --- | --- |
| 1 | 导入与共享类型契约 | 1-155 | 155 | `Tab`、`StatusUsage`、`StatusBudget`、`StatusBacklog`、`StatusFeishu`、`StatusState`、`StatePayload`、`SyncStatusPayload`、`DiagnosticsPreviewPayload`、`ConflictSelection`、`ConflictPathDetail`、`ConflictDetails`、`SyncConflictDetailsPayload`、`RecoveryPreparationSummary`、`SyncConflictRecoveryPayload` | 全部跨模块 payload/DTO 类型 |
| 2 | 模块级可变状态 | 157-222 | 66 | `state`、`review`、`externalActions`、`tab`、`importing`、`importOpen`、`capturing`、`importResults`、`stateLoadError`、`reviewLoadError`、`externalActionsError`、`reviewPlanReady`、`reviewApplyBusy`、`reviewFilter`、`reviewSelectedIds`、`projectDetail*`、`projectListQuery`、`projectListFilter`、`projectReturnContext`、`projectFocusAfterRenderName`、`modalReturnFocus`、`lastStateReadAt`、`lastReviewReadAt`、`reviewDrafts`、`apiRequestSequence`、`latestStateRequest`、`latestReviewRequest`、`latestExternalActionsRequest`、`latestProjectViewRequest`、`MAX_TEXT_CHARS`、`StaleWorkspaceResponseError`、`isStaleWorkspaceResponse`、`remoteVersion`、`lastServerInstance`、`versionCheckPromise`、`connectionHadFailure`、`restoredDraft`、`loadedAskWorkspace`、`conflict*` | 全局共享状态与在途计数器（**拆分的主要难点**） |
| 3 | 第二大脑：类型与状态 | 224-304 | 81 | `AskMsg`、`AskThread`、`AskHistoryTurn`、`AskResponse`、`AskFact`、`AskConflictSide`、`AskConflict`、`AskAnswer`、`SourceReadPayload`、`ASK_MAX_THREADS`、`ASK_MAX_HISTORY`、`askThreads`、`askActiveId`、`askBusy`、`askBusyThreadId`、`askDraft`、`askErrors`、`askScope`、`askStorageKey`、`askDraftEntity` | 问答域类型与状态 |
| 4 | 运行时基座 | 306-354 | 49 | `app`、`toasts`（顶层 DOM 根）、`apiClient`、`api<T>()`、`persistEntityDraft`、`toast`、`rejectOversizeText` | DOM 根、API 封装、提示与草稿落盘 |
| 5 | 版本握手 · 诊断 · 草稿快照 | 356-587 | 232 | `healthTone`、`versionStatusLabel`、`setVersionStatus`、`saveCurrentDraftSnapshot`、`applyRestoredDraft`、`reloadToBuild`、`copyDiagnostics`、`previewDiagnostics`、`exportDiagnostics`、`doCheckVersion`、`checkVersion` | 版本/连接生命周期与更新前草稿保护 |
| 6 | 渲染调度与 Shell | 589-753 | 165 | `render`、`renderShell`、`focusVisibleProjectLink` | tab 派发、外壳 HTML、顶部栏与返回焦点工具 |
| 7 | 今日页装配 | 755-856 | 102 | `renderToday`（内联 `capture`、`importFiles`、`toggleImport`、`refresh` 四个 action） | 今日页 action 装配（渲染已委托 `mountToday`） |
| 8 | 第二大脑：会话存储 | 858-934 | 77 | `loadAskStore`、`saveAskStore`、`activeAskThread`、`makeThreadTitle`、`newAskThread`、`deleteAskThread`、`askHistoryOf` | localStorage 会话读写（上限 10） |
| 9 | 第二大脑：渲染与交互 | 936-1240 | 305 | `askView`、`renderAsk`、`renderAskSide`、`askSourceButton`、`renderAskAnswer`、`sourceReadSequence`、`openSource`、`renderAskChat`、`bindAskInput`、`askSubmit`、`beginAskRename` | 问答全页渲染、提交流程、只读来源弹层 |
| 10 | 审批页装配 | 1241-1296 | 56 | `renderReview` | 读取失败提示、`reviewHtml` 组装、草稿回填、筛选与勾选绑定 |
| 11 | 项目页装配 | 1298-1366 | 69 | `renderProjects` | 列表/详情三态与搜索、状态筛选 |
| 12 | 指南页 | 1368-1473 | 106 | `guideSummaryHtml`、`guideCache`、`guideBodyHtml`、`renderGuide` | 指南渲染、目录、本地搜索 |
| 13 | 设置页动作 + workspace 生命周期 | 1475-1650 | 176 | `RemoteNormalizationPreviewPayload`、`AcceptancePreflightPayload`、`previewGitRemoteNormalization`、`applyGitRemoteNormalization`、`rollbackGitRemoteNormalization`、`runAcceptancePreflight`、`renderSettings`、`runAutomationJob`、`copyAutomationSummary`、`switchProfile`、`migrateWorkspace`、`runSettingsDoctor` | 设置页写操作与 profile/迁移（渲染已委托 feature） |
| 14 | 外部写回核对 + 审批批量选择 | 1652-1689 | 38 | `reconcileExternalAction`、`selectedReviewEntries`、`batchSelectedReview` | 外部写回状态核对与按选中批量 |
| 15 | 全局事件总控 | 1691-2078 | 388 | 顶层 `document.addEventListener('click')`（1693-2006，**59 个 `action === '...'` 分支**）、顶层 `document.addEventListener('submit')`（2008-2078，`thread-create-form` 与 `.edit-form`） | 全应用唯一 action 派发器 |
| 16 | 审批决定 API 动作 | 2080-2149 | 70 | `decide`、`batchDecide`（内含 `REVIEW_BATCH_LIMIT = 100`，2108）、`setProjectState` | 审批决定与项目激活/归档 |
| 17 | 日志弹层 | 2151-2237 | 87 | `LogDraft`、`openLogModal`、`logSubmitting`、`submitLog` | 追加推进日志（多选项目/线程） |
| 18 | 产物弹层 | 2239-2404 | 166 | `ArtifactDraft`、`openArtifactModal`、`artifactSubmitting`、`submitArtifact` | AI 产物入库 + `产物已保存` 二次确认同步 |
| 19 | 项目详情绑定与导航 | 2406-2527 | 122 | `bindProjectDetail`、`showProjectView`、`backFromProjectDetail` | 详情内改名/日志/产物入口、返回上下文与滚动恢复 |
| 20 | 撤销系统改动 | 2529-2639 | 111 | `WbCommitItem`、`UndoHistoryPayload`、`UndoDiffPayload`、`UNDO_FLYNOTE`、`openUndoModal`、`loadUndoDiff`、`doUndoRevert` | git 自动提交历史还原 |
| 21 | 简报 · 任务完成 · 行内编辑 | 2641-2777 | 137 | `runBrief`、`completeTask`、`tsToDatetimeLocal`、`plusMinutesInput`、`openRowEditModal`、`rowEditSubmitting`、`submitRowEdit` | 今日页写回动作与飞书行内编辑 |
| 22 | 审批预演/写回 + 弹层基座 | 2779-2894 | 116 | `planApply`、`activateModal`、`openModal`、`closeModal`、`requestModalClose` | `/api/review/plan` 与 `/api/review/apply`，以及全应用弹层基础设施 |
| 23 | 数据读取与刷新 | 2896-2966 | 71 | `refreshState`、`refreshReview`、`refreshExternalActions`、`refreshAll` | 读取编排 + 过期响应丢弃 |
| 24 | 同步冲突：标签与详情 | 2968-3115 | 148 | `conflictKindLabel`、`conflictSelectionLabel`、`conflictRevision`、`conflictEventSummary`、`conflictDigestSummary`、`conflictSelectionsPayload`、`missingConflictSelections`、`activateConflictModal`、`renderSyncConflictModal`、`showSyncConflictDetails` | 冲突详情弹层 |
| 25 | 同步冲突：预检与恢复 | 3117-3212 | 96 | `conflictRecoveryRequest`、`conflictSelectionRequest`、`previewSyncConflictRecovery`、`applySyncConflictRecovery` | 选择校验、只读预检、确认恢复 |
| 26 | 同步横幅 · 重试 · 导出 | 3214-3311 | 98 | `refreshSyncBanner`、`retrySync`、`exportSyncSnapshot`、`exportSyncConflictPackage` | 顶部保护态横幅与导出 |
| 27 | 启动挂载 | 3313-3346 | 34 | `mountLegacyWorkbench`（唯一 export） | 外壳渲染、mutation idle 钩子、focus/visibilitychange、60s 轮询 |

合计 3321 行，其余 25 行是簇间空行分隔（156、223、305、355、588、754、857、935、1297、1367、1474、1651、1690、2079、2150、2238、2405、2528、2640、2778、2895、2967、3116、3213、3312）。

### 1.3 结构性观察（决定拆分难点）

1. **状态高度集中**：簇 2 的 66 行里同时住着 6 个域的状态（today/review/projects/ask/sync/version）。这是拆分的第一难点。
2. **动作与渲染分离但同文件**：`renderReview`/`renderProjects`/`renderToday` 只是"装配器"（拼参数 + 绑事件 + 调 feature），真正的 HTML 已在 `features/*/render.ts`；但**动作**（decide、planApply、submitLog…）全部还在单体里。
3. **唯一 action 派发器**：59 个 `data-action` 分支集中在一个 click 监听里（1693-2006），是天然的"路由表"，也是拆分时最容易漏项的地方。
4. **在途保护成对出现**：`latestStateRequest`/`latestReviewRequest`/`latestExternalActionsRequest`/`latestProjectViewRequest`/`sourceReadSequence` 各自 `++` 与 `!==` 必须同模块，否则静默回归。
5. **模块顶层副作用仅 2 处**：306-307 的 `document.getElementById('app'|'toasts')` 顶层求值，和 1693/2008 的顶层 `document.addEventListener`。其余监听器都在函数内。

---

## 2. 既有边界

### 2.1 `web/src/` 目录现状（实测）

```
web/src/
├── legacy-main.ts        3346 行   ← 本蓝图对象
├── main.ts                  6 行   composition root
├── brief-card.ts          254 行
├── md.ts                   85 行
├── build-globals.d.ts       2 行
├── style.css              42288 B
├── guide.md               （构建生成物，.gitignore 忽略）
├── api/client.ts           85 行
├── core/workspace-store.ts 31 行
├── lifecycle/{connection.ts 35, drafts.ts 129, native-bridge.ts 44, version.ts 55}
└── features/
    ├── projects/{index.ts 2, render.ts 216, types.ts 37}    有实现
    ├── review/{index.ts 10, render.ts 248, types.ts 50}     有实现
    ├── settings/{index.ts 183}                              有实现
    ├── today/{index.ts 76, render.ts 70, types.ts 43}       有实现
    └── onboarding/ sync/ threads/ workspace/                空目录
```

### 2.2 `features/*` 的既有约定（照抄即可，不要另立风格）

- **目录结构**：`index.ts`（公共边界 / barrel）+ `render.ts`（纯 HTML 字符串渲染）+ `types.ts`（域类型）。`features/settings` 只有单个 `index.ts`（渲染 + 数据读取同文件），是"单文件 feature"的既有先例。
- **barrel 必须显式导出类型**（`isolatedModules` 要求）：
  - `features/projects/index.ts`：`export type { ProjectListFilter, ProjectState, ProjectView } from './types';` + `export { projectDetailHtml, projectDisplayName, projectsHtml, projectsListHtml } from './render';`
  - `features/review/index.ts`：同样形态，且注释写明 `/** Review feature boundary, including review apply actions. */` —— **审批写回动作本来就规划在这个边界里**。
- **依赖注入而非反向 import**：`features/settings/index.ts` 定义 `SettingsActions { api, mutation, toast, refresh }`，由调用方注入；feature 绝不 import `legacy-main`。`features/today/index.ts` 的 `mountToday(view, state, options)` 同样把 state 与 actions 作为入参。
- **模块顶层不得触碰 DOM/window**：4 个渲染测试都在 Node 下 `import` feature 模块（`platform: 'node'`），顶层访问 `document` 会直接抛错。
- **测试方式**：`web/scripts/test-<feature>-render.mjs` 用 esbuild 把一段内联 TS 入口（`stdin` + `resolveDir: src`）打成 ESM bundle 落盘，再 `import()` 动态加载并断言返回的 HTML 字符串。例：`test-project-render.mjs`、`test-review-render.mjs`、`test-today-import-render.mjs`、`test-settings-render.mjs`（后者还测并发过期响应）、`test-api-error.mjs`。**纯渲染函数天然可测**——这正是拆分的收益点。
- **ADR 依据**：`docs/archive/decisions/0036-frontend-feature-lifecycle-boundaries.md` 明确"`features/onboarding`、`workspace`、`projects`、`threads`、`review`、`sync`、`settings` 均有独立入口边界……既有大型等价 UI 实现暂由 `legacy-main.ts` 作为兼容 feature bundle 承载，新基础层从该 bundle 接入；之后新增或迁移 feature 必须从对应目录导入，不得重新堆回 composition root"。同文档 2026-09-10 记录：`onboarding`/`sync`/`threads`/`workspace` 的空入口文件因无消费者被删，**目录保留**。

### 2.3 `legacy-main.ts` 与 `features/*` 的实际关系

**已经抽出（4 个域，只有渲染与纯逻辑）**

| 已抽出 | 位置 | 单体里剩下的对应物 |
| --- | --- | --- |
| 今日页 HTML | `features/today/{render,index,types}.ts` | `renderToday`（755-856）——action 装配仍在单体 |
| 审批页 HTML | `features/review/{render,index,types}.ts` | `renderReview`（1241-1296）+ 全部审批动作（1669-1689、1874-1917、1948-1973、2080-2133、2779-2836） |
| 设置页 HTML + 读取 | `features/settings/index.ts` | `renderSettings` 适配器（1573-1580）+ 全部设置写动作（1491-1650、1776-1838） |
| 项目页 HTML | `features/projects/{render,index,types}.ts` | `renderProjects`（1298-1366）+ 详情导航（2406-2527）+ 项目动作（2135-2148、1840-1863） |

**仍滞留在单体里（按簇）**：第二大脑（簇 3、8、9 共 463 行）、指南页（簇 12，106 行）、同步横幅与冲突恢复（簇 24-26，342 行）、撤销（簇 20，111 行）、日志/产物弹层（簇 17-18，253 行）、行内编辑（簇 21，137 行）、版本/诊断/草稿快照（簇 5，232 行）、弹层基座（2838-2894，57 行）、全局事件总控（簇 15，388 行）、数据刷新（簇 23，71 行）、启动（簇 27，34 行）。

**结论**：`features/*` 已经把"渲染"这条线抽干净了，**剩下的是"状态 + 动作 + 基础设施 + 路由"**。因此蓝图的重点是这三类，而不是再拆 HTML。

### 2.4 入口链与构建链（精确）

```
web/index.html  <script type="module" src="/src/main.ts">
      ↓
web/src/main.ts (6 行)  import './style.css'; import { mountLegacyWorkbench } from './legacy-main'; mountLegacyWorkbench();
      ↓
web/src/legacy-main.ts  export function mountLegacyWorkbench()  ← 全应用唯一入口，3346 行
```

- **入口文件只有两个**：`web/index.html`（Vite 的 HTML 入口，指向 `/src/main.ts`）与 `web/src/main.ts`。`legacy-main.ts` 不是 HTML 入口，是被 `main.ts` 静态 import 的模块。
- **构建链**：`web/scripts/build.mjs` 的 `build()` 依次执行
  1. `npm run sync-guide` —— 把 `docs/product/WEB_USAGE_GUIDE.md` 拷成 `web/src/guide.md`（`web/scripts/sync-guide.mjs`）；
  2. `computeSourceHash(sourceEntries())` —— 源清单 = **`web/src/**` 递归全部文件** + `web/package.json` + `web/package-lock.json` + `web/vite.config.ts` + `web/tsconfig.json` + `docs/product/WEB_USAGE_GUIDE.md`；
  3. `node_modules/.bin/tsc --noEmit`（注入 `WB_FRONTEND_BUILD`、`WB_BUILD_TIME`）；
  4. `node_modules/.bin/vite build`；
  5. `writeBuildMeta()` 写 `src/summit_workbench/webapp/static/build-meta.json`。
- **`vite.config.ts`**：`base: '/static/'`（build 时）、`outDir: '../src/summit_workbench/webapp/static'`、`emptyOutDir: true`、`assetsDir: 'assets'`、`define.__WB_BUILD__ = process.env.WB_FRONTEND_BUILD ?? 'dev-local'`。
- **版本串 `v2026.09.11-e8ed6f7e` 的生成**：`build.mjs:makeBuildIdentity()` → `frontendBuild = \`v${builtAt 前 10 位把 - 换成 .}-${git rev-parse --short HEAD}-${sourceHash 前 8 位}\``。`CLIENT_BUILD` 由 `src/lifecycle/version.ts` 读取 `__WB_BUILD__` 得到（`build-globals.d.ts` 声明）。因此**当前工作树里的 `-e8ed6f7e` 是 sourceHash 前缀，会随 `web/src` 任意字节变化而变化**。
- **静态产物已入库**（`git ls-files` 实测 4 个）：
  - `src/summit_workbench/webapp/static/index.html`
  - `src/summit_workbench/webapp/static/build-meta.json`
  - `src/summit_workbench/webapp/static/assets/index-Bv4PjZAN.js`（内容哈希文件名，随源码变化）
  - `src/summit_workbench/webapp/static/assets/index-Dzf63s49.css`
  `.gitignore` 只忽略 `web/node_modules/` 与 `web/src/guide.md`。
- **产物校验三重**：
  - `web/scripts/verify-build.mjs`：`index.html` 的 sha256 必须等于 `meta.index_sha256`；`index.html` 里所有 `/static/...` 引用必须存在；`meta.assets` 每个文件必须存在且 sha256 匹配；**`assets/*.js` 必须包含 `meta.frontend_build` 字符串**；全树只能有一个 `build-meta.json`。
  - `src/summit_workbench/webapp/build_info.py:WebBuildInfo.from_static_dir()`：运行时同一套校验，失败抛 `BuildInfoError`；`version_payload()` 把 `frontend_build` 交给 `/api/version`。
  - `tests/unit/test_webapi.py:80-88` 直接读 `build-meta.json` 的 `frontend_build` 与接口返回值比对。
- **`web/src/guide.md` 是生成物**：`.gitignore` 已忽略；唯一事实源是 `docs/product/WEB_USAGE_GUIDE.md`（258 行）。**禁止手改、禁止提交、禁止把它当源码**。`legacy-main.ts:33` 的 `import guideMd from './guide.md?raw'` 是它唯一的消费者。

### 2.5 测试链（真实命令）

`web/package.json` scripts（原文）：

| 命令 | 实际执行 |
| --- | --- |
| `sync-guide` | `node scripts/sync-guide.mjs` |
| `dev` | `npm run sync-guide && vite` |
| `build` | `node scripts/build.mjs` |
| `test:build` | `node scripts/test-build.mjs` |
| `test:frontend` | `node scripts/test-build.mjs && node scripts/test-project-render.mjs && node scripts/test-review-render.mjs && node scripts/test-today-import-render.mjs && node scripts/test-settings-render.mjs && node scripts/test-api-error.mjs && node scripts/test-browser-contract.mjs` |

- `test-build.mjs` 的关键断言：`src/main.ts` **必须 ≤ 40 行**（"composition root"）；`api/client.ts` 含 `normalizeApiError` 与 `AbortController`；`core/workspace-store.ts` 含 `workspaceScopedKey`；`features/{projects,review,settings,today}/index.ts` **必须存在**；各自含 `projectDetailHtml` / `reviewHtml` / `profile` / `mountToday`。→ **新增 feature 目录必须带 `index.ts`，否则 `test:frontend` 直接失败**（注意：现有断言是白名单式的 4 个，新增目录不会自动被检查，但按约定仍应提供 `index.ts`）。
- `test-browser-contract.mjs` 是**源码级契约测试**（读文件 + 正则），不是真实浏览器 E2E。详见 §6 风险 1 与附录 A。
- 本地工具链已就绪，无需安装：`web/node_modules/.bin/` 下有 `tsc`、`vite`、`esbuild`（devDependencies：`esbuild ^0.28.2`、`typescript ^7.0.2`、`vite ^8.3.0`）。
- 独立类型检查命令：`cd web && ./node_modules/.bin/tsc --noEmit`。

---

## 3. 目标模块划分

命名与目录约定**完全沿用** `features/<domain>/{index,render,types}.ts` 与"features 通过参数接收 api/mutation/toast/refresh"的既有形态。不新增顶层目录：基础设施改动只落在既有 `web/src/api/`、`web/src/core/`、`web/src/lifecycle/`。

### 3.1 总览

| 目标模块 | 类型 | 承接的簇 | 迁入行数（约） | 测试 |
| --- | --- | --- | --- | --- |
| `features/shell/` | 新增目录 | 6（部分）、15（保留）、22、4（部分） | 290 | `test-shell-render.mjs`（新增） |
| `features/today/actions.ts` | 扩展既有 | 7、21 | 240 | 扩展 `test-today-import-render.mjs` |
| `features/review/` | 扩展既有 | 10、14、16、22（planApply） | 250 | 扩展 `test-review-render.mjs` |
| `features/projects/` | 扩展既有 | 11、19 | 190 | 扩展 `test-project-render.mjs` |
| `features/settings/` | 扩展既有 | 13 | 176 | 扩展 `test-settings-render.mjs` |
| `features/sync/` | 填充空目录 | 24、25、26 | 342 | `test-sync-render.mjs`（新增） |
| `features/threads/` | 填充空目录 | 17、18 | 253 | `test-threads-render.mjs`（新增） |
| `features/ask/` | 新增目录 | 3、8、9 | 463 | `test-ask-render.mjs`（新增） |
| `features/guide/` | 新增目录 | 12 | 106 | `test-guide-render.mjs`（新增） |
| `features/undo/` | 新增目录 | 20 | 111 | `test-undo-render.mjs`（新增） |
| `src/api/request.ts` | 扩展既有目录 | 4（`apiClient`、`api`、`StaleWorkspaceResponseError`） | 40 | `test-api-error.mjs` 扩展 |
| `src/lifecycle/version.ts` / `diagnostics.ts` | 扩展既有目录 | 5（版本）与 5（诊断） | 232 | `test-browser-contract.mjs` 现有断言 |
| `src/lifecycle/drafts.ts` | 扩展既有文件 | 5（快照编排 `saveCurrentDraftSnapshot`/`applyRestoredDraft`/`persistEntityDraft`） | 80 | 现有断言 |
| `src/core/text.ts` | 扩展既有目录 | 2（`MAX_TEXT_CHARS`/`rejectOversizeText`） | 10 | 现有断言 |
| `legacy-main.ts` | 收敛为组合根 | 1、2、6（`render`）、15（派发）、23、27 | ≈ 400-500 | `test:frontend` 全量 |

拆分后 `legacy-main.ts` 的预期规模：**约 400-500 行**（类型契约 + 跨域状态 + `render()` + 全局 action 派发 + 数据刷新编排 + `mountLegacyWorkbench`）。文件名**不变**（改名/删除需另行决策，见 §7）。

### 3.2 每个模块的职责、接收符号与测试

#### `features/shell/`（新增）

- **职责**：应用外壳、tab 路由、弹层基础设施、toast、DOM 根访问、焦点工具。**不得 import 任何其他 `features/<domain>`**。
- **文件与符号**
  - `dom.ts`：`appRoot()`、`toastRoot()`、`viewElement(tab)`、`modalBackdrop()`、`modalRoot()` —— 惰性访问器，替代 306-307 的顶层求值。
  - `toast.ts`：`toast(msg, kind)`（338-348 原样搬迁，内部用 `toastRoot()`）。
  - `modal.ts`：`activateModal`（2838）、`openModal`（2869）、`closeModal`（2882）、`requestModalClose`（2889）、`modalReturnFocus`、`registerModalCloseHook(fn)`（**新增**，用于解开 §4.4 的 `sourceReadSequence` 环）。
  - `shell.ts`：`renderShell(options)`（629-744）——tab 点击/键盘导航改为回调 `options.onSelectTab(tab)`；顶部栏按钮（刷新/检查更新/撤销/退出）与 `Escape`/`Tab` 焦点陷阱原样保留。
  - `tabs.ts`：`applyTabChrome(tab)`（591-628 的 tab 按钮 aria/active 与六视图显隐部分）。
  - `focus.ts`：`focusVisibleProjectLink(name)`（746-753）。
- **接收**：`{ onSelectTab, onRefresh, onCheckUpdates, onUndo, onQuit }` 回调。
- **测试**：`test-shell-render.mjs` —— 用假的 `document`（同 `test-settings-render.mjs` 的 stub 风格）验证 `applyTabChrome` 的 aria/`hidden` 行为，并断言 `renderShell` 产出的 HTML 含 6 个 `id="view-*"`、`#modal-backdrop`、`#toasts` 之外的 6 个 tab 按钮与 `data-action` 集合。

#### `features/today/actions.ts`（扩展既有 feature）

- **职责**：今日页写回动作。
- **接收符号**：`capture`/`importFiles`（757-847 的 action 对象）、`runBrief`（2641）、`completeTask`（2653）、`tsToDatetimeLocal`/`plusMinutesInput`（2681/2691，纯函数）、`openRowEditModal`/`submitRowEdit`（2701/2733）。
- **形态**：`export function createTodayActions(deps: { api, mutation, toast, refreshState, renderToday, limit }): TodayActions`，返回对象直接喂给 `mountToday`。`ImportReceipt` 类型保持从 `features/today` 导出不变。
- **测试**：扩展 `test-today-import-render.mjs`（已覆盖 partial/多文件/抽屉重开）；新增对 `tsToDatetimeLocal`、`plusMinutesInput` 的纯函数断言（含 `null`/`0`/非法值返回空串）。

#### `features/review/`（扩展既有 feature）

- **新增文件**：`state.ts`（`review`、`reviewFilter`、`reviewSelectedIds`、`reviewDrafts`、`reviewLoadError`、`reviewPlanReady`、`reviewApplyBusy`、`lastReviewReadAt`）、`actions.ts`（`decide` 2080、`batchDecide` 2103 + `REVIEW_BATCH_LIMIT` 2108、`selectedReviewEntries` 1669、`batchSelectedReview` 1676、`reconcileExternalAction` 1652、`planApply` 2779）、`assemble.ts`（`renderReview` 1241-1296）。
- **公共边界**（`index.ts` 增补）：`assembleReview(view, deps)`、`createReviewActions(deps)`、`applyReviewPayload(payload)`。`reviewHtml` 导出保持不变。
- **注意**：`index.ts` 的既有注释已经写明本边界"including review apply actions"，落地即兑现该注释。
- **测试**：扩展 `test-review-render.mjs`（已覆盖筛选/勾选/落点未定/批量门槛）；新增对 `batchSelectedReview` 过滤逻辑（`entry.actionable && !!entry.route`）与 `REVIEW_BATCH_LIMIT=100` 的纯逻辑断言——把现在**只靠正则锁定**的行为变成真断言（`test-browser-contract.mjs:44-46` 目前只是 grep）。

#### `features/projects/`（扩展既有 feature）

- **新增文件**：`state.ts`（`projectDetail*`、`projectListQuery`、`projectListFilter`、`projectReturnContext`、`projectFocusAfterRenderName`、`latestProjectViewRequest`）、`detail.ts`（`renderProjects` 1298-1366、`bindProjectDetail` 2406、`showProjectView` 2466、`backFromProjectDetail` 2506）、`actions.ts`（`setProjectState` 2135、项目改名提交 2425-2460）。
- **测试**：扩展 `test-project-render.mjs`（已覆盖显示名、转义、搜索、归档过滤、详情返回按钮）。

#### `features/settings/`（扩展既有 feature）

- **新增文件**：`types.ts`（`RemoteNormalizationPreviewPayload` 1475、`AcceptancePreflightPayload` 1485，以及现有内联的 `ProfileSummary` 等一并归位）、`actions.ts`（1491-1650 全部写动作 + 1776-1838 的派发分支）。
- **形态**：`createSettingsActions(deps: SettingsActions): SettingsActionMap`，其中 `SettingsActions` 沿用 `features/settings/index.ts` 里**已经定义好**的 `{ api, mutation, toast, refresh }`。`switchProfile` 需要额外注入 `disposeApiClient()` 与 `clearDraftSnapshot()`（它现在直接调 `apiClient.dispose()` 与 `workspaceStore.dispose()`）。
- **测试**：扩展 `test-settings-render.mjs`（已有并发过期响应用例）；新增断言：`/api/settings/git/remote/preview|apply|acceptance-preflight` 三个请求都带 `Content-Type: application/json`（把 `test-browser-contract.mjs:67-81` 的邻近窗口正则换成对请求构造函数的直接调用断言）。

#### `features/sync/`（填充既有空目录）

- **文件与符号**
  - `types.ts`：`SyncStatusPayload`、`ConflictSelection`、`ConflictPathDetail`、`ConflictDetails`、`SyncConflictDetailsPayload`、`RecoveryPreparationSummary`、`SyncConflictRecoveryPayload`。
  - `labels.ts`（**纯函数，零依赖**）：`conflictKindLabel`（2968）、`conflictSelectionLabel`（2979）、`conflictRevision`（2988）、`conflictEventSummary`（2992）、`conflictDigestSummary`（2998）。
  - `state.ts`：`conflictDetails`、`conflictSelections`、`conflictPreparation`、`conflictMessage`、`conflictBusy`。
  - `conflict.ts`：`conflictSelectionsPayload`（3008）、`missingConflictSelections`（3012）、`activateConflictModal`（3016）、`renderSyncConflictModal`（3023）、`showSyncConflictDetails`（3082）、`conflictRecoveryRequest`（3117）、`conflictSelectionRequest`（3128）、`previewSyncConflictRecovery`（3138）、`applySyncConflictRecovery`（3178）。
  - `banner.ts`：`refreshSyncBanner`（3214）、`retrySync`（3258）、`exportSyncSnapshot`（3268）、`exportSyncConflictPackage`（3296）。
  - `index.ts`：`mountSyncBanner(deps)`、`createSyncActions(deps)`、`applySyncStatusPayload(payload)`。
- **测试**：`test-sync-render.mjs` —— 对 `conflictKindLabel` 全部 5 个 kind（含 `unknown-generated-view`/`opaque-binary`）、`conflictSelectionLabel` 3 个选项 + 兜底、`conflictRevision` 的 12 字符截断边界做直接断言；这比现在的 `/unknown-generated-view/`、`/preserve-both/` 两条正则强得多。

#### `features/threads/`（填充既有空目录）

- **理由**：日志与产物都是"写入项目/知识线程档案"的动作（`openLogModal` 文案："AI 会整理摘要并归入各线程"；产物弹层同样是线程归档），与 ADR 0036 承诺的 `threads` 边界一致。
- **文件**：`types.ts`（`LogDraft` 2151、`ArtifactDraft` 2239）、`log-modal.ts`（`openLogModal` 2156、`submitLog` 2200、`logSubmitting` 2198）、`artifact-modal.ts`（`openArtifactModal` 2246、`submitArtifact` 2343、`artifactSubmitting` 2341）、`index.ts`。
- **注意**：这两个弹层是 `.edit-form` 之外的独立表单，`submit` 走各自的 `id`（`#log-form`、产物表单），不在 2008 的 submit 委托里，搬迁时不要漏掉它们自己的监听器。
- **测试**：`test-threads-render.mjs` —— 断言产物"二次确认"路径：`window.confirm` 文案含 `产物已保存` 且随后调用 `/api/threads/state`（把 `test-browser-contract.mjs:149` 的 1200 字符邻近窗口正则换成可执行断言）。

#### `features/ask/`（新增目录）

- **文件**：`types.ts`（簇 3 的类型）、`store.ts`（`ASK_MAX_THREADS`、`ASK_MAX_HISTORY`、`askThreads`、`askActiveId`、`askDraft`、`askErrors`、`askScope`、`askStorageKey`、`askDraftEntity`、`loadAskStore`、`saveAskStore`、`activeAskThread`、`makeThreadTitle`、`newAskThread`、`deleteAskThread`、`askHistoryOf`）、`render.ts`（`renderAskSide`、`askSourceButton`、`renderAskAnswer`、`renderAskChat` —— **纯字符串函数**）、`actions.ts`（`renderAsk`、`bindAskInput`、`askSubmit`、`beginAskRename`）、`source-reader.ts`（`sourceReadSequence`、`openSource` 1028-1055）、`index.ts`（`mountAsk(view, deps)`）。
- **跨域耦合**：`openSource` 依赖弹层基座；`closeModal` 里的 `sourceReadSequence += 1` 必须改为 `registerModalCloseHook(() => { sourceReadSequence += 1; })`，否则 shell ↔ ask 成环。
- **测试**：`test-ask-render.mjs` —— 对 `renderAskAnswer` 的 `unanswerable`、`facts`（实际引用）、仅召回未引用分组、`conflicts` 结构化冲突分别断言；`askSourceButton` 的转义断言；把现在 4 条正则（`renderAskAnswer`、`仅召回、未在回答中引用的材料`、`cited_source_ids`、`answer.conflicts`）升级为真断言。

#### `features/guide/`（新增目录）

- **文件**：`render.ts`（`guideSummaryHtml` 1370、`guideCache` 1376、`guideBodyHtml` 1378、`renderGuide` 1415）、`index.ts`（`mountGuide(view)`）。`import guideMd from '../../guide.md?raw'`（相对 `features/guide/render.ts`）。
- **测试**：`test-guide-render.mjs` —— `guideSummaryHtml` 只放行行内代码（`<script>` 必须被转义）的纯函数断言；`guideBodyHtml` 对 FAQ 段落（`**Q：**`）分组的断言（注意 `guideCache` 是模块级缓存，测试需按需重置，建议导出 `resetGuideCache()` 仅供测试）。

#### `features/undo/`（新增目录）

- **文件**：`types.ts`（`WbCommitItem`、`UndoHistoryPayload`、`UndoDiffPayload`）、`modal.ts`（`UNDO_FLYNOTE`、`openUndoModal`、`loadUndoDiff`、`doUndoRevert`）、`index.ts`。
- **测试**：`test-undo-render.mjs` —— 断言空历史/有历史两种弹层 HTML；`UNDO_FLYNOTE` 必须在两种情况下都出现（现在无覆盖）。

#### 基础设施（扩展既有目录，不新增顶层目录）

| 目标 | 迁入符号 | 说明 |
| --- | --- | --- |
| `src/api/request.ts` | `apiClient` 单例、`api<T>()`、`StaleWorkspaceResponseError`、`isStaleWorkspaceResponse`、`apiRequestSequence`、`disposeApiClient()` | `StaleWorkspaceResponseError` 必须与 `isStaleWorkspaceResponse` 同模块，各 feature 的 catch 才能复用而不互相 import |
| `src/lifecycle/version.ts` | `remoteVersion`、`lastServerInstance`、`versionCheckPromise`、`connectionHadFailure`、`versionStatusLabel`、`setVersionStatus`、`doCheckVersion`、`checkVersion`、`reloadToBuild` | 该文件已有 `CLIENT_BUILD`/`validateVersionPayload`/`canonicalPanelUrl`，是既有归属 |
| `src/lifecycle/diagnostics.ts` | `copyDiagnostics`、`previewDiagnostics`、`exportDiagnostics` | 诊断与版本同属生命周期 |
| `src/lifecycle/drafts.ts` | `saveCurrentDraftSnapshot`、`applyRestoredDraft`、`persistEntityDraft` | 该文件已导出 `saveDraftSnapshot`/`loadEntityDraft` 等底层能力，快照编排应与其同住 |
| `src/core/text.ts` | `MAX_TEXT_CHARS`、`rejectOversizeText` | 后端 100,000 字符上限的前端镜像 |

---

## 4. 依赖方向

### 4.1 分层与允许的 import

```
L0  src/api/*  src/core/*  src/lifecycle/*  src/md.ts  src/brief-card.ts      （基础设施，不得 import features）
L1  src/features/shell/*                                                      （只可 import L0）
L2  src/features/<domain>/*                                                   （可 import L0 + shell + 同域相对导入）
L3  src/legacy-main.ts                                                        （可 import 任意 feature 的 index.ts；是唯一组合点）
```

**硬规则**

1. `features/<domain>` 之间**只能经对方的 `index.ts` 交互**，不得深入内部文件。当前唯一违例：`features/review/render.ts:1` 直接 `import { projectDisplayName } from '../projects/render'`。修正方式是把 `projectDisplayName` 提升为 `features/projects/index.ts` 的公共导出后改为 `from '../projects'`（该 barrel 已被 `test-build.mjs` 的 `read('src/features/projects/index.ts')` 断言覆盖，改名会立刻报错）。
2. **任何 feature 不得 import `legacy-main.ts`**（否则成环）。
3. **`features/shell` 不得 import 任何 domain feature**。因此 `render()`（591-627，需要依次调用 6 个域的 render）**必须留在 `legacy-main.ts`**；shell 只提供 `applyTabChrome(tab)` 与 `viewElement(tab)`。
4. L0 不得 import features。实测当前 `src/api`、`src/core`、`src/lifecycle` 均满足。
5. 不允许新增顶层目录（保持 `src/{api,core,lifecycle,features}` 四个）。

### 4.2 共享状态的处理规则

- **每个域自己的状态住在 `features/<domain>/state.ts`**，只通过 `index.ts` 暴露 `apply<Domain>Payload(payload)` 与只读 getter。
- **跨域读取一律走函数入参**，沿用既有 `mountToday(view, state, options)` 与 `renderSettings(view, actions)` 的形态；禁止"feature A import feature B 的 state 模块"。
- **`state` / `review` 两个大快照**：仍由 `legacy-main.ts` 持有并扇出（`renderReview(reviewView)` 需要 `state.status.pending_review`、`state.day`、`state.projects`，跨了三个域，强行下沉只会制造环）。这是有意保留的 L3 职责。
- **在途计数器与其守卫必须同模块**（不变量）：`latestStateRequest`/`latestReviewRequest`/`latestExternalActionsRequest` 与 `refresh*` 同处；`latestProjectViewRequest` 与 `showProjectView`/`backFromProjectDetail` 同处 `features/projects/detail.ts`；`sourceReadSequence` 与 `openSource` 同处 `features/ask/source-reader.ts`；`reviewApplyBusy`/`reviewPlanReady` 同处 `features/review/state.ts`。

### 4.3 数据刷新（`refreshState`/`refreshReview`/`refreshExternalActions`/`refreshAll`）的归属

两个可选方案，**推荐方案 A**：

- **方案 A（推荐，无环）**：`features/shell/refresh.ts` 提供 `registerLoader({ key, load })` 与 `refreshAll()`/`refreshKey(key)`。各 feature 在 `mount*` 时注册自己的 loader，计数器私有于该模块。`legacy-main.ts` 只调 `refreshAll()`。依赖方向：feature → `shell/refresh`（L1），`legacy-main` → `shell/refresh`（L3），无环。
- **方案 B（更保守）**：`refresh*` 四个函数整段留在 `legacy-main.ts`（L3）。这仍是合法分层（L3 可以横向扇出），只是组合根会多约 70 行。若某一步想降低风险，可以先走 B 再择机转 A。

### 4.4 必须避免的具体环

| 环 | 现状证据 | 处理 |
| --- | --- | --- |
| `shell/modal` ↔ `ask` | `closeModal()` 内 `sourceReadSequence += 1`（2883） | `registerModalCloseHook()`；由 `features/ask` 在 mount 时注册 |
| `shell` ↔ 6 个域 | `render()`（591-627）按 tab 调 6 个 render | `render()` 留在 `legacy-main.ts`；shell 不 import 域 |
| `shell` ↔ `sync` | `activateConflictModal`（3016）复用 `activateModal`（2838） | 单向：sync → shell/modal。允许 |
| `sync` ↔ `undo` | 二者都用 `openModal`；`requestModalClose` 被两者共用 | 均单向依赖 shell/modal，无相互依赖 |
| `review` ↔ `projects` | `review/render.ts` 直接 import `projects/render` | 改走 `features/projects/index.ts` barrel |
| `settings` ↔ `lifecycle/version` | `switchProfile`（1608）调 `apiClient.dispose()` + `workspaceStore.dispose()` | `src/api/request.ts` 导出 `disposeApiClient()`；`workspaceStore` 直接 import 既有 `src/core/workspace-store` |
| `legacy-main` ↔ 任意 feature | 全局 click 派发器需要调各域动作 | **保留派发器在 `legacy-main`**（L3 只向下调用，不反向） |

### 4.5 DOM 根、API client、启动顺序的处理

- **DOM 根**：`const app = document.getElementById('app')`（306）与 `toasts`（307）是**模块顶层求值**。目标：`features/shell/dom.ts` 的惰性访问器 `appRoot()`/`toastRoot()`；**禁止任何 feature 在模块顶层访问 `document`/`window`**——4 个渲染测试在 Node（`platform: 'node'`）下 import feature 模块，顶层访问会直接抛错。
- **API client**：`apiClient` 单例（309-317）带 `onFailure`/`onSuccess` 回调维护 `connectionHadFailure`，`onSuccess` 会在连接恢复时触发 `checkVersion('connection-restored')`。下沉到 `src/api/request.ts` 时，这两个回调必须改成**可注册的观察者**（`onConnectionRestored(fn)`），否则 `api/request` 会反向 import 版本模块。
- **启动顺序（不可改动语义）**：
  1. `main.ts` → `mountLegacyWorkbench()`
  2. `renderShell()` —— **先建 DOM 外壳**（所有 `#view-*`、`#modal-backdrop` 都在这一步产生）
  3. `setMutationIdleHandler(...)`（`saveCurrentDraftSnapshot()` + `reloadToBuild()`）
  4. 注册 `window focus`（3321）与 `document visibilitychange`（3322）
  5. `startApp()`：`checkVersion('startup')` → `loadDraftSnapshot(...)` → `refreshAll()` → 若有恢复草稿再 `render()`
  6. `refreshSyncBanner()`；两个 60s `setInterval`（仅在 `visibilityState === 'visible'` 时工作）
  - 规则：**feature 的注册副作用只能发生在 `mount*()` 被调用时**，且 `mount*()` 只能在 `renderShell()` 之后调用；`features/*/index.ts` 顶层只允许 import 与函数/类型声明。

### 4.6 实测的 global/window 耦合清单（迁移时逐项确认）

| 类别 | 位置 | 处理 |
| --- | --- | --- |
| `window.sessionStorage` 键 `wb.update.last-target` / `wb.update.last-attempt-at` | 455-456、1706-1707 | 随 `reloadToBuild`/`retry-update` 一并进 `src/lifecycle/version.ts`；键名常量集中定义 |
| `window.localStorage`（问答会话） | 862、875 | 留在 `features/ask/store.ts`（经 `workspaceScopedKey()`） |
| `window.location.href = '/onboarding'` | 1831 | 进 settings 动作；`test-browser-contract.mjs:13` 有断言 |
| `window.location.assign(canonicalPanelUrl(...))` | 461 | 进 `src/lifecycle/version.ts` |
| `window.location.reload()` | 1619、1632 | 进 settings 动作 |
| `window.confirm` / `window.prompt` | 12 处（704、914、1520、1542、1623、1805、1826、1846、1932、1937、1943、2376、2623、3180） | 留在各域；其中 3 条被契约测试用邻近窗口锁定 |
| `navigator.clipboard` | 1601 | 进 settings 动作 |
| `URL.createObjectURL` | 3287、3300、3306 | 进 `features/sync/banner.ts` |
| `sendNativeMessage`（quit / checkForUpdates / openLogDirectory / saveTextFile） | 698、1747、3292 等 | 经 `src/lifecycle/native-bridge` 既有 API |
| `notifyClientReady(CLIENT_BUILD, server_instance)` | 563 | 留在版本模块 |
| 顶层 `document.addEventListener('click'/'submit')` | 1693、2008 | **全应用只允许各一处**，留在 `legacy-main.ts` |
| `document.addEventListener('keydown')`（弹层焦点陷阱） | 722（`renderShell` 内） | 随 shell；`renderShell` 只调用一次，不会重复注册 |
| `window.addEventListener('focus')`、`document.addEventListener('visibilitychange')`、2× `setInterval` | 3321、3322、3338、3342 | 留在 `mountLegacyWorkbench` |
| 跨模块 DOM id 字符串（`#app`、`#toasts`、`#modal-backdrop`、`#modal`、`#version-status`、`#version-error-banner`、`#day-pill`、`#tab-badge-review`、`.tab`、`#view-{today,review,ask,projects,guide,settings}`） | `renderShell` 629-744 与各 feature render | 登记为跨模块契约；建议集中到 `features/shell/dom.ts` 常量 |

---

## 5. 迁移顺序

每一步**独立可发布、行为保持**。所有步骤都遵守：不改文案、不改 DOM 结构、不改请求路径与请求头、不改键盘/焦点行为。

**通用验证命令**（每步都跑）

```bash
# 1. 类型门（最快的失败信号）
cd web && ./node_modules/.bin/tsc --noEmit

# 2. 前端全量测试
npm --prefix web run test:frontend

# 3. 生产构建 + 产物校验（会改写已入库的 static/，必须与源码同批提交）
npm --prefix web run build
node web/scripts/verify-build.mjs src/summit_workbench/webapp/static

# 4. Python 侧消费方（构建身份变了仍必须通过）
uv run pytest tests/unit/test_webapi.py tests/unit/test_acceptance_preflight.py -q
```

### 步骤 0（前置，必须单独一笔提交）：让契约测试对文件布局免疫  ✅ **已完成 2026-09-12**

- **改动**：`web/scripts/test-browser-contract.mjs` 把 `const source = fs.readFileSync('src/legacy-main.ts','utf8')` 换成一个只读的聚合读取器（例如 `const source = ['src/legacy-main.ts', ...].map(read).join('\n')`），并**同时**消除 12 条带 `[\s\S]{0,N}` 邻近窗口的脆弱断言中的 4 条最脆的（见 §6 风险 1 的清单），改为两条独立断言。**不改任何断言的语义**。
- **为什么必须最先做**：107 条断言里有 **84 条**锚定 `legacy-main.ts`（见附录 A）。任何搬迁都会误伤，导致无法判断"是真的回归还是测试过时"。
- **注意**：3 条 `assert.doesNotMatch(source, ...)`（54、99、132-136）在内容搬走后会**静默通过**，属于"守卫丢失"而非"测试失败"。步骤 0 必须把它们逐条重新指向新模块文件。
- **验证**：`npm --prefix web run test:frontend`（预期与步骤 0 之前完全相同，全绿）。

### 步骤 1：纯函数与类型外迁（零行为风险）

- **产出**：`features/sync/labels.ts`（5 个纯函数）、`features/today/` 的 `tsToDatetimeLocal`/`plusMinutesInput`、`src/core/text.ts`（`MAX_TEXT_CHARS`/`rejectOversizeText`）、`features/undo/types.ts`、`features/sync/types.ts`、`features/ask/types.ts`。
- **手法**：`legacy-main.ts` 改为从新模块 import（删除原定义），不改任何调用点。
- **验证**：通用命令 + 新增 `test-sync-render.mjs` 的纯函数断言。
- **收益**：先建立"新模块 + 新测试"的样板，风险几乎为零。

### 步骤 2：弹层基座与 DOM 根（`features/shell/`）

- **产出**：`features/shell/{dom,modal,toast}.ts`；`activateModal`/`openModal`/`closeModal`/`requestModalClose`/`modalReturnFocus` 迁入 `modal.ts`；`registerModalCloseHook()` 建立，`features/ask`（此步仍只是 legacy-main 内的一个注册调用）注册 `sourceReadSequence` 失效钩子。
- **注意**：`closeModal()` 现在直接改 `sourceReadSequence`（2883），必须**同步**改为钩子，否则要么成环要么丢失"关闭弹层时作废在途来源读取"的语义。
- **验证**：通用命令；契约测试的 `function activateModal`、`requestModalClose`、`if \(backdrop\.hidden\)[\s\S]{0,180}modalReturnFocus` 三处断言（步骤 0 已改指向 `features/shell/modal.ts`）必须仍然通过。

### 步骤 3：请求基座与应用外壳

- **产出**：`src/api/request.ts`（`apiClient`、`api<T>()`、`StaleWorkspaceResponseError`、`isStaleWorkspaceResponse`、`apiRequestSequence`、`disposeApiClient()`、`onConnectionRestored(fn)`）；`features/shell/{shell,tabs,focus}.ts`（`renderShell` 改为 `mountShell({ onSelectTab, onRefresh, onCheckUpdates, onUndo, onQuit })`）。
- **注意**：`renderShell` 里的按钮回调当前直接引用 `refreshAll`/`refreshSyncBanner`/`openUndoModal`；改为回调注入。tab 点击改为 `onSelectTab(tab)`，`render()` 仍留在 `legacy-main.ts`。
- **验证**：通用命令；`test-api-error.mjs` 必须仍通过（它 import `./api/client`，路径未变）。

### 步骤 4：`features/guide/` 整页外迁（自包含，几乎无跨域依赖）

- **产出**：`features/guide/{render,index}.ts`；`legacy-main.ts` 的 `import guideMd from './guide.md?raw'` 迁到 `features/guide/render.ts`，路径变为 `'../../guide.md?raw'`。
- **注意**：`guide.md` 是生成物（§2.4）；这一步**只改 import 路径**，不得触碰 `docs/product/WEB_USAGE_GUIDE.md`，也不得把 `web/src/guide.md` 加进版本控制。
- **验证**：通用命令 + `test-guide-render.mjs`；契约测试的 4 条 guide 断言（`guide-search`、`guide-index-links`、`node.tagName === 'H2' || node.tagName === 'H3'`、`data-guide-section`、`link.hidden = ...`）改指向 `features/guide/render.ts` 后必须通过。

### 步骤 5：`features/ask/` 整页外迁（最大单块，463 行）

- **产出**：`features/ask/{types,store,render,actions,source-reader,index}.ts`。
- **建议**：先 `store.ts`（无 DOM）+ `render.ts`（纯字符串），再 `source-reader.ts`，最后 `actions.ts` 与 `index.ts`。每小步都跑通用命令。
- **注意**：`askSubmit`（1137-1209）依赖 `refreshState` 之外还依赖 `state?.projects`（检索范围下拉）与 `askErrors`；`renderAskChat` 里对 `askDraft` 的实体草稿读写要保持 `persistEntityDraft`/`loadEntityDraft` 的调用次序（契约测试锁定 `/saveEntityDraft|loadEntityDraft|clearEntityDraft/`）。
- **验证**：通用命令 + `test-ask-render.mjs`。

### 步骤 6：`features/sync/` + `features/undo/`

- **产出**：如 §3.2。`refreshSyncBanner` 与 `retrySync` 一并迁入 `banner.ts`。
- **注意**：`put` 契约测试的负向断言 `assert.doesNotMatch(source, /async function refreshSyncBanner[\s\S]{0,1800}\} catch \{\s*\n\s*el\.hidden = true;/)`（132-136）是"不要静默隐藏保护态横幅"的守卫；搬迁后必须重新指向 `features/sync/banner.ts`，并保留正向断言 `/同步状态读取失败/`。
- **验证**：通用命令 + `test-sync-render.mjs`、`test-undo-render.mjs`。

### 步骤 7：`features/threads/`（日志与产物弹层）

- **产出**：如 §3.2。`bindProjectDetail` 里对 `openLogModal`/`openArtifactModal` 的调用改为从 `features/threads`（或经 `features/projects` 注入）导入。
- **注意**：`submitArtifact` 的两步确认（`产物已保存` → `/api/threads/state`）与 `openArtifactModal` 内的 `persistEntityDraft('artifact:...')` 是关键不变量。
- **验证**：通用命令 + `test-threads-render.mjs`。

### 步骤 8：`features/projects/` 详情导航 + `features/review/` 动作 + `features/settings/` 动作 + `features/today/` 动作

- **产出**：如 §3.2。这是把"滞留动作"归位的一步，也是唯一会显著改动全局派发器的步骤：click 分支由内联实现改为一行调用（`features/review/actions.ts` 的 `handleReviewBatch(btn)` 等）。
- **注意**：
  - `planApply` 同时被 `plan`/`apply` 两个 data-action 分支使用，且耦合 `#plan-result`、`#modal [data-action="apply"]` 的 DOM 查询与 `reviewApplyBusy`/`reviewPlanReady`。整块搬迁，不拆分。
  - `showProjectView`/`backFromProjectDetail` 与 `projectReturnContext`/`projectFocusAfterRenderName`/`latestProjectViewRequest` 必须同模块（6 条契约断言锁定这套不变量）。
- **验证**：通用命令 + 扩展后的 `test-project-render.mjs`、`test-review-render.mjs`、`test-settings-render.mjs`、`test-today-import-render.mjs`。

### 步骤 9：收敛 `legacy-main.ts` 与刷新编排

- **产出**：`legacy-main.ts` 只剩簇 1（类型）、簇 2（跨域状态）、`render()`、全局 click/submit 派发、`refreshState`/`refreshReview`/`refreshExternalActions`/`refreshAll`（或用 §4.3 方案 A 换成 `shell/refresh.ts` 的注册表）、`mountLegacyWorkbench`。目标规模 **约 400-500 行**。
- **注意**：`main.ts` 必须保持 ≤ 40 行（`test-build.mjs` 断言），因此不要往 `main.ts` 里加东西。
- **验证**：通用命令 + 全量 `uv run pytest -q` + `npm --prefix web run test:build`。

---

## 6. 风险点

### 风险 1：`test-browser-contract.mjs` 有 84/107 条断言锚定 `legacy-main.ts`

**实测事实**（逐条解析确认）：文件共 **107** 条 `assert.match`/`assert.doesNotMatch`；锚定对象分布为 — `legacy-main.ts` **84** 条、`features/settings/index.ts` **7** 条、`features/review/render.ts` **4** 条、`style.css` **4** 条、其余 `read(...)` 文件 **8** 条（`lifecycle/native-bridge.ts` 1、`api/client.ts` 1、`core/workspace-store.ts` 1、`features/today/render.ts` 2、`features/today/index.ts` 3）。

其中 **12 条**使用 `[\s\S]{0,N}` 邻近窗口（布局极脆），逐条如下：

| 行 | 断言要点 | 窗口 | 脆弱点 |
| --- | --- | --- | --- |
| 19 | `/api/sync/conflict/selection/validate` 之后 350 字符内出现 `conflictSelectionRequest()` | 350 | 两个符号分到不同函数即失败，即使语义完全正确 |
| 69/74/79 | 三个 settings 请求路径之后 250 字符内出现 `headers: { 'Content-Type': 'application/json' }` | 250 | 中间插入一行注释就可能突破窗口 |
| 89 | `const action = btn.dataset.action ?? '';` 之后 120 字符内 `btn.focus()` | 120 | 派发器重排即失败 |
| 91 | `if (backdrop.hidden)` 之后 180 字符内 `modalReturnFocus` | 180 | 弹层基座搬迁时若拆函数即失败 |
| 116 | `async function openUndoModal` 之后 500 字符内 `openModal(` | 500 | 函数改名/签名调整即失败 |
| 122/127 | `document.visibilityState !== 'visible') return;` 之后 80 字符内 `checkVersion('interval')` / `refreshSyncBanner()` | 80 | 两个 60s 轮询的间距极窄 |
| 134 | `async function refreshSyncBanner` 之后 1800 字符内不得出现 `} catch {\n el.hidden = true;` | 1800 | **负向断言，搬走后静默通过** |
| 149 | `window.confirm` → 350 字内 `产物已保存` → 500 字内 `/api/threads/state` | 350/500 | 产物二次确认链路 |

**另有 2 条负向断言在内容搬走后会静默通过**（守卫丢失而非失败）：第 54 行 `assert.doesNotMatch(source, /selected[^\n]*\/api\/review\/apply/)`、第 99 行 `assert.doesNotMatch(source, /activateModal\(projectViewHtml\(view\)\)/)`。

**缓解**
1. 步骤 0 先引入多文件聚合读取器，把断言与"内容住在哪个文件"解耦。
2. 对 4 条最脆的邻近断言（19、69/74/79、134、149）改成"两条独立断言 + 一条对导出函数的行为断言"——语义不变，但不再依赖字符距离。这是本蓝图里**唯一**允许的测试改动，且必须与源码搬迁分成不同提交以便审阅。
3. 3 条 `doesNotMatch` 必须显式登记到新文件，并在提交说明里点明"守卫已重新锚定"，避免静默失效。

### 风险 2：构建身份变化 + 已入库的静态产物

**实测事实**：`build.mjs:sourceEntries()` 的哈希输入包含 **`web/src/**` 的全部文件**，所以任何搬迁都会改变 `source_hash` → `frontend_build`（`v<日期>-<gitsha>-<hash8>`）→ Vite 产物文件名 `index-<hash>.js` → `index.html`、`build-meta.json`、`assets/*` 四个已入库文件的内容全部变化。而 `verify-build.mjs` 要求 `assets/*.js` **必须包含** `meta.frontend_build` 字符串、`meta.assets` 的 sha256 必须逐一匹配；`build_info.py` 在服务启动时做同一套校验（失败抛 `BuildInfoError`）；`tests/unit/test_webapi.py:80-88` 读 `build-meta.json` 与 `/api/version` 比对。

**后果**：只提交源码、不重新构建提交 static/，会同时打破 `verify-build`、运行时 `WebBuildInfo`、`tests/unit/test_webapi.py`；反之，忘记 `emptyOutDir` 会残留旧 hash 文件导致"全树只能有一个 build-meta.json"之外的重复资源。

**缓解**
1. 每个步骤都执行 `npm --prefix web run build && node web/scripts/verify-build.mjs src/summit_workbench/webapp/static`。
2. 源码与 `src/summit_workbench/webapp/static/` 的 4 个文件放**同一笔提交**；提交信息里记录新的 `frontend_build`（这与 `docs/implementation/V0-4-4-UX-UI-INCREMENTAL-IMPLEMENTATION.md` 的既有写法一致）。
3. 纯文档提交（例如本文件）不触发构建，不产生 static/ 变更。

### 风险 3：`web/src/guide.md` 是生成物，抽取 `features/guide/` 会动它的 import 路径

**实测事实**：`.gitignore` 含 `web/src/guide.md`（注释："构建时从 `docs/product/WEB_USAGE_GUIDE.md` 生成的指南副本（勿提交，防漂移）"）；`sync-guide.mjs` 是唯一生产者，已并入 `dev` 与 `build`；`legacy-main.ts:33` 是唯一消费者。

**后果**：新 clone 或 CI 未跑 `sync-guide` 时，`features/guide/render.ts` 的 `import guideMd from '../../guide.md?raw'` 会让 `tsc`/`vite` 直接失败（文件不存在）；若有人为"修好构建"而提交 `guide.md` 或手改它，就会与事实源漂移。

**缓解**：import 路径写对（`features/guide/render.ts` → `'../../guide.md?raw'`）；构建始终走 `npm --prefix web run build`（内部已含 `sync-guide`）；不把 `guide.md` 加入版本控制；指南内容只改 `docs/product/WEB_USAGE_GUIDE.md`。

### 风险 4：TypeScript 严格度会让"搬一半"直接编译失败

**实测 `web/tsconfig.json`**：`target: ES2022`、`module: ESNext`、`moduleResolution: bundler`、**`strict: true`**、`noEmit: true`、**`noUnusedLocals: true`**、**`noUnusedParameters: true`**、`skipLibCheck: true`、**`isolatedModules: true`**、`useDefineForClassFields: true`、`types: ["vite/client"]`、`include: ["src"]`。`build.mjs` 把 `tsc --noEmit` 作为硬门。

**后果**
- `noUnusedLocals`/`noUnusedParameters`：搬走函数后遗留的 import、只被搬走代码使用的私有 helper、只用于某域的参数，都会让构建失败。
- `isolatedModules`：类型再导出必须写 `export type { ... }`（既有 barrel 已是此风格，照抄即可）；把类型当值再导出会被 esbuild/Vite 拒绝。
- `moduleResolution: bundler`：相对导入**不带扩展名**（既有风格），不要写成 `./render.js`。

**缓解**：每步先跑 `./node_modules/.bin/tsc --noEmit`；搬迁时同步删除旧位置与本文件内已无用的 import；新 barrel 复制 `features/projects/index.ts` 的 `export type` 写法。

### 风险 5：模块顶层 DOM/window 访问会同时打破测试与启动顺序

**实测事实**：306-307 在模块顶层求值 `document.getElementById('app')`/`('toasts')`；4 个渲染测试在 Node（`platform: 'node'`）下 `import()` feature 模块。

**后果**：把顶层求值原样搬进 `features/shell/*` 后，Node 下的渲染测试会因 `document is not defined` 崩溃；同时若某个 feature 被早于 `renderShell()` 求值，会拿到 `null` 并静默失效。

**缓解**：`features/shell/dom.ts` 用惰性访问器；把"feature 顶层不得访问 DOM/window"写成评审清单项。

### 风险 6：全局监听器重复注册 → 双写回

**实测事实**：顶层 `document.addEventListener('click')` 与 `('submit')` 各只有一处（1693、2008）；`keydown`（722）在 `renderShell` 内，`renderShell` 仅被 `mountLegacyWorkbench` 调用一次。

**后果**：搬迁时若在 feature 内"顺手"再注册一个 click 委托，审批决定/日志/产物会执行两次（`mutation()` 只能防重复请求，不能防两次逻辑执行）。

**缓解**：规则写死——全应用只保留一处 click、一处 submit 派发器（留在 `legacy-main.ts`），feature 只导出 `handle*Action()` 纯函数式处理器；并在 `test-browser-contract.mjs` 增加一条"全树只出现一次 `document.addEventListener('click'`"的计数断言。

### 风险 7：焦点与弹层不变量

**实测事实**：契约测试显式锁定 `modalReturnFocus`（91）、`activateConflictModal`（143-146）、`requestModalClose`（88、148）、`openModal` 复用（116）、`projectFocusAfterRenderName`/`getComputedStyle(el).display !== 'none'`/`getClientRects().length > 0`（94-98）、`#pv-*` 详情返回焦点。

**后果**：弹层基座与撤销/同步冲突弹层若分成两步搬迁，中间态会出现"关闭后焦点丢失"或"嵌套弹层覆盖返回焦点"。

**缓解**：步骤 2 一次性把弹层基座 + `sourceReadSequence` 钩子做完；撤销（步骤 6）与同步冲突（步骤 6）同一步落地；每步用键盘走查 Escape/焦点归还（`docs/acceptance/UI-VERIFICATION-BATCHES.md` 已登记 C1 等真实浏览器验证项）。

### 风险 8：在途计数器被拆散 → 过期响应静默覆盖新数据

**实测事实**：`latestStateRequest`/`latestReviewRequest`/`latestExternalActionsRequest`/`latestProjectViewRequest`/`sourceReadSequence` 各自成对（`++` 与 `!==`）；另有 `features/settings/index.ts` 内的 `settingsRenderSequence`。契约测试有 6 条断言（86、101-108、153-154、61-66）专门盯这件事。

**后果**：把 `++counter` 与 `counter !==` 分到不同模块，或把 `backFromProjectDetail` 里的 `latestProjectViewRequest += 1`（2508）漏搬，都会让"用户已离开详情，过期响应把旧详情推回页面"复活。

**缓解**：把"计数器与守卫同模块"列为不变量（§4.2）；搬迁时以函数为最小单位整体移动，不按行剪裁。

### 风险 9：覆盖率与 Python 侧门禁

**实测事实**：`pyproject.toml` `[tool.coverage.run] source = ["src/summit_workbench"]`、`omit = ["*/webapp/views.py"]`、`[tool.coverage.report] fail_under = 80`；交接要求覆盖率不低于 82.33%。**前端 TS 不进入 Python 覆盖率统计**。

**后果**：纯前端拆分对覆盖率中性；但若同一批提交顺带改了 `src/summit_workbench/webapp/**`（Python 侧在统计范围内），会引入额外风险。

**缓解**：拆分提交只动 `web/` 与自带的 `static/` 产物，不动 Python；每步结束跑 `uv run pytest -q` 确认无连带失败。

### 风险 10：渲染测试脚手架的重复成本

**实测事实**：4 个 `test-*-render.mjs` 各自复制了约 30-90 行的 esbuild `stdin` 打包模板（`build({ stdin: { contents: entry, resolveDir: srcDir, ... }, bundle: true, write: false, format: 'esm', platform: 'node' })`），且各自 `mkdirSync`/`rmSync` 一个临时目录。

**后果**：新增 6 个功能测试会再复制 6 份模板，`test:frontend` 的串行时长和维护面同步上升；同时 `test:frontend` 的命令行会变长，容易漏挂新脚本。

**缓解**：本蓝图不引入共享测试工具（避免额外结构变更）；新增脚本严格沿用命名 `test-<feature>-render.mjs` 并**逐个追加进 `package.json` 的 `test:frontend` 链**；每步验证时确认新脚本确实被执行（`test:frontend` 是 `&&` 链，漏挂不会报错）。

---

## 7. 明确不做 / 需要裁决

**本轮不做**
1. 不修改任何代码文件（含 `legacy-main.ts`、`test-browser-contract.mjs`、`package.json`）。
2. 不搬目录、不改包结构、不重命名模块；`legacy-main.ts` 保持文件名与 `mountLegacyWorkbench` 导出名，`main.ts` 保持 ≤ 40 行。
3. 不运行打包器、不安装依赖、不新增工具链。
4. 不新增顶层目录（目标模块全部落在 `web/src/features/` 或既有 `web/src/{api,core,lifecycle}/`）。
5. 不改产品行为：路由、写回边界、锁语义、outbox、schema/迁移、文案、DOM 结构与键盘/焦点行为一律不变。

**需要需求方裁决的两点**
1. `legacy-main.ts` 最终是否删除并改名（例如 `composition-root.ts`）。本蓝图按"**保留文件名，收敛为组合根**"设计，因为约束禁止重命名，且删除会让 `test-browser-contract.mjs` 的 `readFileSync('src/legacy-main.ts')` 与 ADR 0036 的"兼容 feature bundle"表述同时失效。若将来要改名，需先完成本蓝图步骤 0 的聚合读取器改造。
2. 刷新编排走 §4.3 方案 A（`features/shell/refresh.ts` 注册表）还是方案 B（留在组合根）。方案 A 更干净但引入注册时序；方案 B 更保守但组合根多约 70 行。

---

## 附录 A · `test-browser-contract.mjs` 断言分类（渲染层 vs 单体内部耦合）

**判据**："渲染层"指断言锚定在 feature 渲染函数或样式表上，或只依赖某个字符串/符号仍存在于被读取的文件集合中（内容搬家不影响）；"单体内部耦合"指断言锚定 `legacy-main.ts`，其中带邻近窗口的还额外依赖字符距离。

| 类别 | 条数 | 是否随布局变化失效 | 代表断言 |
| --- | --- | --- | --- |
| 锚定 `legacy-main.ts` 的普通断言（其中 2 条为负向：第 54、99 行） | **72** | 仅在符号/字符串**整体搬走**时失效；步骤 0 的聚合读取器可免疫 | `source, /function openSource/`、`source, /MAX_TEXT_CHARS = 100_000/`、`source, /latestStateRequest|latestReviewRequest/` |
| 锚定 `legacy-main.ts` 的邻近窗口断言（其中 1 条为负向：第 132-136 行） | **12** | **会**因拆分/重排失效（哪怕语义不变） | 第 19、69、74、79、89、91、116、122、127、132、149 行（详见风险 1 表） |
| 锚定已抽出 feature 的断言（settings 7 + review 4） | **11** | 否（已经是模块化的） | `reviewSource, /data-review-filter=/`、`settingsSource, /settingsRenderSequence/` |
| 锚定 `style.css` 的断言 | **4** | 否（纯样式） | `@media (max-width: 900px) … .header-right .version-status` 等 |
| 锚定其余既有模块的 `read(...)` 断言（`native-bridge` 1、`api/client` 1、`core/workspace-store` 1、`today/render` 2、`today/index` 3） | **8** | 否 | `read('src/features/today/index.ts'), /let currentOpen = options\.importOpen/` |
| **合计** | **107** | — | 72 + 12 + 11 + 4 + 8 = 107 |

**三种负向断言单独看**（它们搬走后会"静默通过"，属于守卫丢失而非测试失败）：第 54 行 `selected…/api/review/apply`、第 99 行 `activateModal(projectViewHtml(view))`、第 132-136 行 `refreshSyncBanner` 不得静默隐藏横幅。

**结论**：拆分的安全性**取决于 15 条邻近窗口断言 + 3 条负向断言**，它们必须在步骤 0 被重新锚定；其余 92 条只需聚合读取器即可对布局免疫。

> **计数更正（2026-09-12，执行步骤 0 时实测）**：上表把邻近窗口断言记为 **12** 条并漏掉了
> 4 条样式表断言。实测原文 `grep -c '\[\\s\\S\]{0,'` = **15**，行号为
> 19、69、74、79、89、91、116、122、127、**134**、149、**168、169、170、171**。
> 其中**真正会因为拆分而"静默通过"的只有 1 条负向断言（第 132–136 行的
> `refreshSyncBanner` 守卫）**；另外 2 条负向断言（54、99）不含窗口，聚合读取器已足够。
> 计划里"12 + 3 = 15 条"的说法基于一个错误的分类，实际是 15 条窗口断言（1 条负向）+ 2 条无窗口负向断言。
> 下表的分项数字同样以实测为准：锚定 `legacy-main.ts` 的断言共 **89** 条（74 条直接引用
> `source` + 15 条窗口断言），已抽出 feature 模块 **11** 条，其余模块 `read(...)` **8** 条，
> 样式表 **4** 条（已并入窗口断言），合计 107 条契约断言不变。

### 步骤 0 执行记录（2026-09-12，已完成）

已按本节要求落地，并修正了一处设计缺陷：

- `test-browser-contract.mjs` 改为**递归读取 `web/src` 下全部 `.ts`/`.css`**（排除 `guide.md`
  这类生成物与 `.d.ts`），聚合为 `source`；新增 `fileFor()`（定位契约要求的模块，缺文件即报错）
  与 `filesMatching()`（自动纳入新增样式表）。
- **15 条窗口断言全部改为"按文件求值"**（`assertNearby` / `doesNotMatchNearby`），而不是在拼接文本上求值。
  这一步是执行中发现的真问题：拼接文本上的有界窗口会**跨文件**匹配——探针函数在 A 文件、
  无关的 `catch` 块在 B 文件，窗口照样命中，于是负向守卫会**因无关原因误报**。
  按文件求值同时保住了两点：窗口跟随其锚点所在文件（搬迁后仍有效），且不跨文件。
  若锚点在任何文件里都找不到，测试**直接失败**，避免"什么都匹配不到所以通过"。
- 新增 **4 组 harness 自检**（写一个真实探针文件再删除），断言的是机制本身：
  守卫在**新建模块**里仍然触发；按文件求值不会跨文件匹配；锚点消失可被检测；新建文件会被扫描发现。
  自检**没有**断言"探针里不得出现坏模式"——那是错的：按文件求值下孤立探针本就不该匹配任何东西。

**验证**（全部实测，非推断）：

| 检查 | 结果 |
|---|---|
| `node web/scripts/test-browser-contract.mjs` | 通过（21 个源文件），107 条契约断言的描述逐条仍在 |
| 变异 A：把坏实现放进**新建模块** | **被抓住**，且报出 `violated in src/features/__mutant__.ts` |
| 变异 B：锚点与坏模式**分处两个文件** | **不误报**（这正是修复前会出错的场景） |
| 变异 C：从锚点所在文件删掉必需片段（3 条正向窗口断言各一次） | **全部被抓住** |
| 探针文件残留 | 无；`git status` 只有本测试文件一处改动 |

## 附录 B · 验证命令速查

```bash
# 类型门
cd web && ./node_modules/.bin/tsc --noEmit

# 前端全量（13 个脚本串行）
npm --prefix web run test:frontend

# 仅契约测试
node web/scripts/test-browser-contract.mjs

# 生产构建 + 产物校验（会改写已入库的 static/）
npm --prefix web run build
node web/scripts/verify-build.mjs src/summit_workbench/webapp/static

# Python 侧消费构建身份的测试
uv run pytest tests/unit/test_webapi.py tests/unit/test_acceptance_preflight.py -q

# 构建身份单元测试
npm --prefix web run test:build
```

## 附录 C · 步骤 1–9 执行记录（2026-09-12）

### C.1 结果

每一步都是"源码一笔 + 产物一笔"两笔提交（产物提交紧跟在源码提交之后，让
`build-meta.json` 的 `git_revision` 指向产出它的源码提交）。拆分期间所有提交都带
`[skip ci]`：CI 只在阶段边界手动触发一次，见 C.5。

| 步骤 | 源码提交 | `legacy-main.ts` |
| --- | --- | --- |
| 基线（后端拆分完成） | `be917d2` | 3395 |
| 0 · 契约测试布局免疫 | `455a8c1` | 3346 |
| 1 · 类型与纯函数外迁 | `631d118` | 3210 |
| 2 · 弹层基座、DOM 根与 toast | `94b96e1` | 3153 |
| 3 · 请求基座与应用外壳 | `c6c9d54` | 3014 |
| 4 · 使用指南整页 | `37d5141` | 2906 |
| 5 · 问答整页 | `c4a1b37` | 2494 |
| 6 · 同步 + 撤销 | `0f25c43` | 2093 |
| 7 · 线程日志/产物弹层 | `74128a1` | 1835 |
| 8a · 项目详情导航 | `54522d0` | 1612 |
| 8b · 审批动作 | `1a895dc` | 1395 |
| 8c · 设置页动作 | `380fd0d` | 1188 |
| 8d · 今日写回动作 | `858ecb7` | 997 |
| 9 · 版本状态展示 + 收敛 | 本记录同批 | 964 |

**3395 → 964 行（−71.6%）**，`main.ts` 仍是 6 行（上限 40 行，`test-build.mjs` 断言）。前端测试脚本从 7 个增至 13 个，
全部文件布局无关（`test-browser-contract.mjs` 读取 73 个源文件并逐文件求值窗口断言）。

### C.2 裁决 1（§7-2）：刷新编排走**方案 B**

`refreshState` / `refreshReview` / `refreshExternalActions` / `refreshAll` 整段留在
`legacy-main.ts`（L3）。理由：

1. 方案 A 要求每个 feature 在自己的 `mount*()` 里注册 loader，于是"注册是否已发生"成了新的
   时序不变量；而 `mount*()` 的调用顺序在组合根里已经很长（10 个）。
2. 三个在途计数器（`latestStateRequest`/`latestReviewRequest`/`latestExternalActionsRequest`）
   按 §4.2 必须与其守卫同模块，而守卫的**重置点**（workspace 切换）就在 `doCheckVersion` 里。
   下沉会把计数器与重置点分开。
3. 组合根为此多约 71 行，是 L3 合法的横向扇出。

### C.3 偏差：§3.1 的 `src/lifecycle/{version,diagnostics,drafts}.ts` 只搬了版本展示

§3.1 把簇 5 列在 `src/lifecycle/`，§5 从未给这一步排期。执行时逐函数核对依赖，结论是**该行的大
部分在 §4.1 硬规则 4（L0 不得 import features）下不成立**：

| 符号 | 阻挡依赖 |
| --- | --- |
| `applyRestoredDraft` | `setAskDraft()` —— 直接调用 `features/ask` 的写入口 |
| `persistEntityDraft` / `saveCurrentDraftSnapshot` / `copyDiagnostics` / `previewDiagnostics` / `exportDiagnostics` | `toast()`（`features/shell`，L1）；快照还读写 `tab`/`reviewDrafts`/`restoredDraft` |
| `doCheckVersion` / `checkVersion` | 要重置四个域的状态（ask/review/today/projects）并调用 `refreshAll()`，即 §4.2 明说属于 L3 的跨域编排 |

把它们参数化（注入 `toast`、注入四个 reset）不会减少组合根的职责，只会多出一层注入面，
因此保留在组合根。**可搬的部分已搬**：`versionStatusLabel`/`setVersionStatus`/`reloadToBuild`
只依赖 `CLIENT_BUILD`、`VersionPayload` 与 DOM，已迁入 `src/lifecycle/version.ts`
（`setVersionStatus`/`reloadToBuild` 增加 `remote` 入参以取代对组合根 `remoteVersion` 的闭包），
并新增 `test-version-status.mjs` 直接断言五个状态的文案。

### C.4 偏差：400–500 行目标未达成，实测下限约 750 行

964 行的实测构成：

| 区块 | 行数 |
| --- | --- |
| import 区 | 124 |
| 簇 1 类型契约（`StatePayload` 等） | 52 |
| 簇 2 跨域状态 | 22 |
| 组合根胶水（草稿快照、诊断、版本握手） | 189 |
| `render()` + `renderToday()` | 35 |
| 全局 click/submit 派发（簇 15） | 340 |
| `refresh*`（方案 B） | 71 |
| `mountLegacyWorkbench()` | 125 |

§4.4 明确要求派发器留在组合根，§5 步骤 9 也把簇 15 计入 400–500 的预算内；但派发器实测
**340 行**（57 个分支，绝大多数已是"一行调用 + return"），加上"必须留下"的类型/状态/刷新/启动
就已超过 700 行。即使把 C.3 的全部胶水（189 行）也搬走，下限仍在 **约 750 行**。
结论：**400–500 是估算，实测不支持**；除非把派发器改成 `data-action` → handler 表（可省约 260 行），
但那是一次覆盖 57 个分支、只有 grep 级契约测试兜底的行为重构，与本轮"行为保持"的纪律冲突，
故不做，登记为后续可选事项。

### C.5 验证

每一步都跑了完整门禁，最后一次（步骤 9）：

| 检查 | 结果 |
| --- | --- |
| `cd web && ./node_modules/.bin/tsc --noEmit` | 通过 |
| `npm --prefix web run test:frontend` | 13 个脚本全绿（73 个源文件） |
| `npm --prefix web run build` + `verify-build.mjs` | `Build verified` |
| `.venv/bin/python -m pytest --cov -q` | 927 passed, 1 skipped，覆盖率 83.16% |
| `ruff check` / `ruff format --check` / `mypy` / `secret_scan.py` | 全部通过 |
| `git push`（pre-push 钩子） | `✓ 本地门禁全部通过` |

CI 只在阶段边界手动触发：前端拆分全部落地后 `gh workflow run ci.yml` 一次，用于验证
macOS 打包链路；其余提交一律 `[skip ci]`。

### C.6 拆分期间修改的既有断言（3 处）

只有这 3 处，都是为了跟随**布局**变化，语义未放宽：

| 位置 | 改动 | 原因 |
| --- | --- | --- |
| `test-build.mjs` | 设置页内容锚点从 `features/settings/index.ts` 移到 `render.ts` | 设置页在 8c 拆成目录后，barrel 只剩 re-export |
| `test-browser-contract.mjs` | `settingsSource` 从单文件改为 `filesMatching(/^src\/features\/settings\/.*\.ts$/)` | 设置契约现在分布在目录内多个文件；放置保证由"单文件"改为"feature 内" |
| `python tests/contract/*` | 前端源码聚合读取（`5428267`），`test_native_panel_contract.py` 增加 `_web_sources()`/`_web_source_after()` 逐文件切片 | 同一符号搬进新模块后，原先"读单文件"的 Python 守卫会误报 |
