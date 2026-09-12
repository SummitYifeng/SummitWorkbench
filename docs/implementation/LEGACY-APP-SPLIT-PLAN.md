# LEGACY-APP 拆分蓝图（`src/summit_workbench/webapp/legacy_app.py`）

- 状态：**计划（planning deliverable）**。本轮不改任何代码，不移动目录，不改包结构。
- 对象文件：`src/summit_workbench/webapp/legacy_app.py`，**3457 行**（`wc -l` 实测）。
- 上位决策：`docs/archive/decisions/0035-webapp-route-service-split.md`（ADR 0035，P1-03）。
  该 ADR 已经明确：「既有 handler 暂由 `legacy_app.py` compatibility bundle 注册……后续迁移必须逐领域、逐快照完成」。
  本蓝图是该约束下的**逐领域迁移排期**，不是推翻 ADR。
- 一切行号、符号名、路由数均来自 `ast` 解析 + `grep` 实测，未凭印象填写；口径见 §1.1 与 §8。

---

## 0. 结论摘要

| 指标 | 实测值 |
| --- | --- |
| `legacy_app.py` 总行数 | **3457** |
| 顶层符号 | 4 个模块级常量 + 13 个模块级函数/类 + **2 个 app 工厂**（`_create_restricted_app` / `create_app`） |
| `def`/`class` 总数（含嵌套闭包） | 135 |
| 路由装饰器 | **80** 个（79 个生效注册点：`/` 有 SPA/SSR 两条互斥分支） |
| 其中 `_create_restricted_app`（受限空安装 app） | **14** 条，行范围 683–1095（413 行） |
| 其中 `create_app`（完整 app） | **65** 条，行范围 1098–3457（2360 行） |
| 路由契约快照 | `docs/contracts/web-route-contract.json`，**82 条 route / 38 个请求体模型** |
| 已由 `routers/*` 提供 | **17 条**（契约 − 本文件 = 17，已用集合差集核对，见 §2.2） |
| 仍滞留在本文件 | **65 / 82 = 79.3%** 的完整 app 路由 + **100%** 的受限 app 路由 + 全部中间件/异常处理器/lifespan/SPA 挂载/共享 helper |
| 目标模块数 | **22**（8 个共享 seam 模块 + 14 个路由模块，其中 2 个为扩展既有模块） |
| 迁移步数 | **16 步**（Step 0 基线冻结 + Step 1–16 抽取），每步独立可发布 |

**核心判断**：真正的难点不是「把函数搬走」，而是四个**隐式契约**——(1) `route_contract.py` 是**源码级**契约（`inspect.getsource` + 正则提取 error code），(2) `legacy_app` 的模块命名空间被 4 处测试 `monkeypatch` 当作**注入点**，(3) `profile_switch_in_progress` 闭包变量被 settings 集群写、被 sync 集群读，(4) 中间件注册顺序决定 HTTP 行为。§4 与 §6 专门处理这四条。

---

## 1. 现状测绘

### 1.1 文件的真实形态

`legacy_app.py` 不是「一个模块」，而是**两个互斥的 FastAPI 应用工厂被打包进同一个文件**：

```
legacy_app.py
├── 1–213    模块前言：imports + 2 个模块级常量
├── 216–680  共享 helper 层（11 个符号，被两个工厂共用）
├── 683–1095 _create_restricted_app()  ← 空安装控制面 app（14 条路由，无 vault context）
└── 1098–3457 create_app()             ← 完整面板 app（65 条路由，含全部领域 handler）
```

`create_app(ctx=None)` 在 1109–1124 行直接 `return _create_restricted_app(...)`，两个工厂由此耦合。
**所有领域 handler 都是工厂函数体内的闭包**，通过捕获 `ctx`、`app`、`_operation_id`、`feishu_clients`、`_run_web_mutation` 等外层变量工作——这既是它 3457 行的原因，也是拆分必须先建「共享 seam」的原因。

### 1.2 集群表（逐行核对）

`行数` 为闭区间实测值，含装饰器行与紧邻注释；`A/B/C…` 编号在 §3、§5 中被反复引用。

| 集群 | 行范围 | 行数 | 关键符号（行号） | 职责 |
| --- | --- | --- | --- | --- |
| **A** 模块前言与常量 | 1–213 | 213 | 模块 docstring(1–11)、`# ruff: noqa: E501`(12)、全部 imports(14–196)、`_STATIC_DIR`(198)、`_SCHEMA_UPGRADE_WRITE_EXEMPTIONS`(206–213) | 依赖与全局常量；`_SCHEMA_UPGRADE_WRITE_EXEMPTIONS` 是只读升级态的写豁免白名单 |
| **B1** 模型配置加载 | 216–228 | 13 | `_load_model_config_for_context`(216) | 兼容既有 monkeypatch 语义的模型配置入口（`workspace_id is None` 时回退 `load_model_config`） |
| **B2** 飞书客户端池 | 231–312 | 82 | `_FeishuClientPool`(231)、`__init__`(238)、`_get`(251)、`user_client`(291)、`tenant_client`(294)、`close`(297)、`invalidate`(306) | 按身份复用飞书客户端，由 lifespan 统一释放；`_get` 内含 `inspect.signature(FeishuClient)` 的**测试兼容分支**(276) |
| **B3** 审批读取与文本渲染 | 315–336 | 22 | `_load`(315)、`_plan_text`(323) | 解析 `review.md` → `ReviewEntry`；`ApplyReport` → 纯文本 |
| **B4** Git 留痕 | 339–366 | 28 | `_commit_suffix`(339) | 写回后自动 `commit_paths` + `push_after_commit`，返回可追加进响应 `message` 的说明 |
| **B5** 线程活动迁移 seam | 369–377 | 9 | `_thread_activity_migration`(369) | 仅对冻结的 production context 构造 P2-01B migration |
| **B6** 撤销错误 envelope | 380–391 | 12 | `_undo_error_response`(380) | undo 错误码 → HTTP 状态映射（422/409/423） |
| **B7** 飞书写回器工厂 | 394–469 | 76 | `_build_task_creator`(394)、`assignee_open_id`(403)、`create`(409)、`_build_meeting_creator`(425)、`create`(438) | 构造 `TaskCreator`/`MeetingCreator`；身份只解析一次；会议缺省结束时间 = 开始 + 60min |
| **B8** 问答引用抽取 | 472–491 | 20 | `_cited_source_ids`(472) | 从 answer 的 `facts`/`conflicts` 抽 `source_id` |
| **B9** 问答 HTML 桥 | 494–542 | 49 | `_ask_html`(494) | 跑一次 `wb ask` 并渲染 HTML；返回 `(html, source_ids, answer)` |
| **B10** 会议导入链路 | 545–654 | 110 | `_run_web_import`(545) | 逐字稿归档 + 结构化 + 生成审批候选；幂等账本先行、软预算只报告不阻断 |
| **B11** 知识来源白名单 | 657–680 | 24 | `KNOWLEDGE_SOURCE_ROOTS`(659)、`SOURCE_BODY_DISPLAY_CHARS`(673)、`_is_knowledge_source`(676) | `/api/review/source` 与 `/api/sources/read` **共用**的只读白名单（注释明确「避免出现一个更宽的旁路」） |
| **C1** 受限 app 构造与边界 | 683–776 | 94 | `_create_restricted_app`(683)、`_restricted_validation_error`(706)、`_restricted_boundary`(724) | `FastAPI(title="SummitWorkbench onboarding")`；host/origin/session 边界；`app.state.active_workspace_context`(703) |
| **C2** 受限握手路由 | 778–825 | 48 | `restricted_home`(778, `GET /`)、`restricted_version`(784, `GET /api/version`)、`restricted_session_bootstrap`(808, `GET /api/session/bootstrap`) | 安装向导握手与一次性会话 cookie |
| **C3** 受限 onboarding 流程 | 827–1085 | 259 | `_rejected`(831)、`restricted_onboarding_status`(842)、`restricted_draft`(852)、`restricted_save_draft`(859)、`restricted_clear_draft`(882)、`restricted_remote_stage`(889)、`restricted_remote_confirm`(942)、`restricted_remote_cancel`(997)、`restricted_preflight`(1016)、`restricted_create`(1031)、`restricted_upgrade`(1051)、`restricted_connect`(1069) | 未安装状态下的 3 步向导 API；`remote_stages` 闭包 dict 暂存 staging 结果 |
| **C4** 受限连接路由接线 | 1087–1095 | 9 | `register_restricted_connection_routes`(1089 调用) | **已有的 router seam**，证明「受限 app 也能挂 router」 |
| **D1** 主 app 签名与运行时状态 | 1098–1154 | 57 | `create_app`(1098)、`ctx is None` 分支(1109–1124)、`feishu_clients`(1126)、`lifespan`(1140)、`app.state.feishu_clients`(1148)、`switch_plans`(1152)、`remote_normalization_plans`(1153)、`profile_switch_in_progress`(1154) | 工厂入口 + 全部闭包可变状态 |
| **D2** operation_id 与异常处理器 | 1156–1216 | 61 | `_operation_id`(1156)、`_validation_error`(1160)、`_http_error`(1176)、`_mutation_blocked_error`(1196)、`_unexpected_error`(1207) | 统一 error envelope（`validation_error`/`http_error`/`sync_diverged`/`internal_error`） |
| **D3** 安全边界中间件 | 1218–1301 | 84 | `_security_boundary`(1218) | host 白名单 → compatibility 写门 → origin → session token；**注册顺序敏感**（见 §6-R6） |
| **D4** build_info 与缓存策略 | 1303–1320 | 18 | `_build_info`(1303)、`_cache_policy`(1306) | `GET /api/version`/`/`/`build-meta.json` no-store；`/static/assets/` immutable |
| **D5** 首页与 SSR 看板 | 1322–1352 | 31 | `_dashboard`(1322)、`spa_index`(1340)、`app.mount("/static")`(1342)、`spa_home`(1344)、`home`(1350) | SPA 已构建则挂载 + `FileResponse`；否则 SSR 回退 |
| **E** 系统路由接线 | 1354–1369 | 16 | `register_system_routes`(1359 调用) | 已有 router seam；此处注入 `build_info=_build_info` |
| **F** Settings/Profile/Automation | 1371–1748 | **378** | `_settings_home`(1371)、`settings_profiles`(1374)、`settings_acceptance_preflight`(1388)、`settings_git_remote_preview`(1437)、`settings_git_remote_apply`(1484)、`settings_git_remote_rollback`(1535)、`settings_profile_prepare`(1570)、`settings_profile_commit`(1585)、`settings_profile_remove`(1603)、`settings_provider`(1629)、`_automation_settings_payload`(1649)、`settings_automation`(1672)、`update_settings_automation`(1676)、`run_settings_automation`(1708)、`settings_doctor`(1729) | **13 条路由**；写 `switch_plans`/`remote_normalization_plans`/`profile_switch_in_progress` |
| **G** 看板状态与 projects 接线 | 1750–1813 | 64 | `api_state`(1750)、`register_project_write_routes`(1810 调用) | 看板聚合（status + brief + inbox + projects + runtime）；已有 router seam，且**注入 `run_mutation`** |
| **H** 审批读取与决策 | 1815–1977 | 163 | `api_review`(1815)、`api_review_source`(1820)、`api_sources_read`(1846)、`api_decide`(1896)、`api_batch_decide`(1918)、`api_edit`(1942)、`api_plan`(1971) | 7 条路由；只读来源白名单在此使用 |
| **I** 外部动作与 apply | 1979–2073 | 95 | `api_external_actions`(1979)、`api_reconcile_external_action`(1985)、`api_apply`(2038) | 3 条路由；`api_apply` 注入 `_build_task_creator`/`_build_meeting_creator`(2048–2049) |
| **J** 线程 | 2075–2273 | 199 | `api_set_project_state`(2075)、`register_project_read_routes`(2110 调用)、`api_thread_activity_consistency`(2116)、`api_append_log`(2129)、`api_save_artifact`(2204) | 4 条路由 + 1 个 router seam |
| **K** 捕获与信号写回 | 2275–2492 | 218 | `api_capture`(2275)、`api_task_complete`(2344)、`api_task_update`(2378)、`api_meeting_update`(2433) | 4 条路由；后三者直接调飞书客户端池(2358/2402/2455) |
| **L** 简报/复盘/问答（JSON） | 2494–2591 | 98 | `api_run_brief`(2494)、`api_run_weekly`(2529)、`api_ask`(2550) | 3 条路由；均先过 `_sync_blocked` + `_mutation_blocked` |
| **M** 导入/撤销/退出 | 2593–2715 | 123 | `api_meetings_import`(2593)、`api_undo_history`(2636)、`api_undo_diff`(2650)、`api_undo_revert`(2661)、`api_shutdown`(2697) | 5 条路由；`api_meetings_import` 用 `inspect.signature(_run_web_import)` 决定是否传 `local_mutation`(2627–2630) |
| **N** SSR 兼容路由 | 2717–2862 | 146 | `run_brief_endpoint`(2719)、`run_weekly_endpoint`(2743)、`ask_endpoint`(2765)、`review`(2778)、`decide`(2783)、`edit`(2803)、`plan`(2833)、`apply`(2841) | 8 条路由；`# ---- SSR 兼容路由（旧入口与既有测试继续可用） ----` 块 |
| **O** 主 app onboarding 与 workspace 接线 | 2864–2969 | 106 | `_onboarding_rejected`(2864)、`api_onboarding_status`(2877)、`api_onboarding_preflight`(2890)、`api_onboarding_create`(2906)、`api_onboarding_upgrade`(2927)、`api_onboarding_connect`(2946)、`register_workspace_routes`(2967 调用) | 5 条路由 + 1 个 router seam |
| **P** 变更/同步核心（**共享入口**） | 2971–3086 | 116 | `_current_sync_snapshot`(2977)、`_run_web_mutation`(2986)、`_sync_blocked`(3014)、`_mutation_blocked`(3051)、`_sync_payload`(3068) | 全文件最重要的 seam：所有写路径的统一事务边界 |
| **Q** 同步 API | 3088–3455 | **368** | `api_sync_status`(3088)、`api_sync_conflict_explain`(3093)、`…/plan`(3100)、`…/details`(3107)、`…/validate`(3142)、`…/export`(3188)、`…/selection/validate`(3222)、`…/recover`(3267)、`api_sync_export`(3391)、`api_claim_primary`(3396)、`api_sync_run`(3440) | **11 条路由**，单块最大 |
| — 尾部 | 3456–3457 | 2 | `return app`(3457) | — |

**行数配平核对**：213 + 2 + 465 + 2 + 413 + 2 + 255 + 1 + 16 + 1 + 378 + 1 + 64 + 1 + 163 + 1 + 95 + 1 + 199 + 1 + 218 + 1 + 98 + 1 + 123 + 1 + 146 + 1 + 106 + 1 + 116 + 1 + 368 + 2 = **3457** ✅

### 1.3 共享入口 `_run_web_mutation` 的真实调用面

定义在 2986–3012，是**唯一**的本地事务边界封装（`run_local_mutation` + sync snapshot + compatibility + author + push-after-commit）。实测 17 处调用：

| 调用行 | 所属集群 | 调用行 | 所属集群 |
| --- | --- | --- | --- |
| 1812（作为 `run_mutation=` 注入 `routers/projects.py`） | G | 2327 `capture` | K |
| 1906 / 1921 / 1959 `decide`/`batch`/`edit` | H | 2361 / 2411 / 2469 `tasks`/`meetings` | K |
| 2001 / 2010 / 2019 `reconcile_external_action` | I | 2794 / 2824 SSR `decide`/`edit` | N |
| 2099 `threads/state` | J | 3413 `sync/primary/claim` | Q |
| 2189 `threads/logs` | J | | |
| 2259 `threads/artifacts` | J | | |

**结论**：`_run_web_mutation` 被 H/I/J/K/N/Q 六个集群 + `routers/projects.py` 共用，**必须是先抽出的共享 seam，不能跟着任何一个路由模块走**。

同理，两个守卫被 11 处调用：

- `_mutation_blocked`：2040(apply)、2501、2536、2666、2726、2750、2843
- `_sync_blocked`：2498、2533、2723、2747（均与 `_mutation_blocked` 成对出现，`_sync_blocked` 在前）

### 1.4 闭包可变状态清单（拆分的隐藏耦合）

| 状态 | 定义行 | 写入方 | 读取方 | 是否跨集群 |
| --- | --- | --- | --- | --- |
| `remote_stages` | 704 | 933(C3) | 951、991、1003(C3) | 否，自我封闭 |
| `switch_plans` | 1152 | 1581(F) | 1581、1588(F) | 否 |
| `remote_normalization_plans` | 1153 | 1470(F) | 1498、1526(F) | 否 |
| **`profile_switch_in_progress`** | **1154** | **1582、1588–1598(F，`nonlocal`)** | **2989(P，`_run_web_mutation`)** | **是 ⚠️** |
| `feishu_clients` | 1126 | — | 2048、2049、2358、2402、2455、2851、2852 + `app.state` | 是（K/I/N） |
| `spa_dir` / `server_instance` / `started_at` / `panel_mode` / `host_allowlist` | 1149–1151、1131–1138 | — | D4/D5/E/F/G | 是 |

`nonlocal profile_switch_in_progress` 出现在 1572 与 1587 两处（`settings_profile_prepare` / `settings_profile_commit`）。

---

## 2. 既有边界

### 2.1 `routers/` 已经建立的东西

```
src/summit_workbench/webapp/
├── routers/
│   ├── __init__.py      (1 行)  """按领域注册 Web 路由；路由模块只负责协议编解码和调用服务。"""
│   ├── diagnostics.py   (83 行)  register_diagnostics_routes  → 2 条路由
│   ├── projects.py     (200 行)  register_project_read_routes / register_project_write_routes → 5 条路由
│   ├── settings.py     (645 行)  register_settings_connection_routes / register_restricted_connection_routes → 14 条路由
│   ├── system.py        (83 行)  register_system_routes → 2 条路由
│   └── workspace.py     (61 行)  register_workspace_routes → 1 条路由
├── services/
│   ├── __init__.py
│   └── workspace.py     (52 行)  migrate_workspace / migration_result_payload  ← 唯一的 service 模块
├── dependencies.py      (31 行)  RouteDependencies(frozen dataclass: app/context/operation_id) + get_app_context
├── errors.py             (5 行)  error_payload 的公开边界（从 security.py 再导出）
├── mutation_response.py (30 行)  _commit_note / _mutation_fields
└── app_factory.py       (69 行)  唯一公开应用创建入口
```

**已抽取 = 契约快照的 17 条 route**（用集合差集核对，`create_app` 注册的 65 条全部在快照内，`legacy − contract = ∅`）：

```
来自 routers/ 的 17 条：
  GET  /api/version                       POST /api/settings/feishu/authorize-url
  GET  /api/session/bootstrap             POST /api/settings/feishu/complete
  GET  /onboarding                        GET  /api/settings/feishu/status
  GET  /callback                          POST /api/settings/provider/verify
  GET  /callback/feishu                   POST /api/workspace/migration
  GET  /api/diagnostics/preview           GET  /api/projects/view
  GET  /api/diagnostics/export            POST /api/projects/rename|activate|archive|create
```

**仍滞留 = 65 条完整 app 路由 + 14 条受限 app 路由 = 79 个生效注册点**，以及**全部**共享 helper、中间件、异常处理器、`lifespan`、`app.state` 注入、SPA 挂载、闭包状态。

### 2.2 装配链（真实调用序）

```
webapp/__init__.py:create_app  →  webapp/app.py:create_app（兼容层）
                                     │  app.py:31–32 把 app._ask_html / app._run_web_import
                                     │  **回写**进 legacy_app 模块命名空间（monkeypatch 传播垫片）
                                     ▼
                               webapp/app_factory.py:create_app
                                     │  _create_legacy_app(...)  ← import legacy_app.create_app
                                     ▼
                               legacy_app.create_app(ctx, ...)
                                     ├─ 1126  构造 _FeishuClientPool
                                     ├─ 1140  lifespan（关闭飞书客户端）
                                     ├─ 1160–1216  4 个 exception_handler
                                     ├─ 1218  _security_boundary 中间件   ← 先注册 = 内层
                                     ├─ 1306  _cache_policy 中间件        ← 后注册 = 外层
                                     ├─ 1322–1352  SPA 挂载 / SSR 首页
                                     ├─ 1359  register_system_routes(...)      [routers/system.py]
                                     ├─ 1810  register_project_write_routes(...) [routers/projects.py]
                                     ├─ 2110  register_project_read_routes(...)  [routers/projects.py]
                                     ├─ 2969  register_workspace_routes(...)     [routers/workspace.py]
                                     └─ 其余 65 条 handler 原地定义
                                     ▼
                               app_factory.py:41–65（**在 legacy 返回之后**）
                                     ├─ app.state.app_context = context
                                     ├─ app.state.structured_logger = StructuredLogger(...)
                                     ├─ 50  register_diagnostics_routes(...)
                                     └─ 59  register_settings_connection_routes(...)
```

`_create_restricted_app` 同理，在 1089 调用 `routers/settings.py:register_restricted_connection_routes`。

### 2.3 既有抽取约定（从真实代码归纳，共 7 条）

1. **模块名 = 领域名**，放在 `webapp/routers/<domain>.py`；模块 docstring 一句话说明「协议适配 + 调用哪个 service/workflow」（见 `routers/workspace.py:1`、`routers/diagnostics.py:1`）。
2. **注册函数签名**：`def register_<domain>_routes(dependencies: RouteDependencies, *, <注入依赖>) -> None`。
   函数体内第一件事固定是 `app = dependencies.app` / `context = dependencies.context`。
3. **路由用闭包 + 装饰器注册**：`@app.get/post(...)` 直接写在 register 函数体内，**不使用 `APIRouter`**。全仓库 `routers/` 下没有任何 `APIRouter` 用法。
4. **返回联合类型的 handler 一律标 `response_model=None`**（`routers/workspace.py:22`、`routers/projects.py:71` 等），避免 FastAPI 从 `dict | JSONResponse` 推断响应模型。
5. **额外依赖用关键字参数注入**，而不是自己去读全局/环境：
   - `register_system_routes(..., static_dir, server_instance, started_at, panel_mode, session_token, workspace_id, device_id, build_info)`（`routers/system.py:20–31`）
   - `register_project_write_routes(dependencies, *, run_mutation: ProjectMutationRunner)`（`routers/projects.py:62–66`），调用侧 `legacy_app.py:1812` 注入 `_run_web_mutation`
   - `register_diagnostics_routes(dependencies, *, static_dir, log_path)`（`routers/diagnostics.py:18–23`）
   - `register_restricted_connection_routes(app, *, active_workspace, operation_id)`（`routers/settings.py:412–417`）← **唯一一个直接收 `FastAPI` 而非 `RouteDependencies` 的模块**，是既有不一致点，新模块不要模仿
6. **模块末尾写 `__all__`**（`routers/system.py:83`、`routers/projects.py:196–200`、`routers/settings.py:645`、`routers/workspace.py:61`）。注意 `legacy_app.py` **没有** `__all__`（实测：AST 顶层只有 4 个赋值）。
7. **长行模块自带 `# ruff: noqa: E501`**（`routers/settings.py:5`；`legacy_app.py:12` 同）。`pyproject.toml [tool.ruff.lint.per-file-ignores]` **没有**为 `webapp/` 配任何忽略，所以新模块必须自带或被 `ruff format` 折行。

### 2.4 测试约定

- 路由**没有**「一个 router 一个测试文件」的对应关系。全部通过 `TestClient(create_app(ctx, ...))` 端到端测（`tests/unit/test_webapi.py` 的 `_client(tmp_path, seed_review=...)`、`tests/unit/test_webapi_sync.py:25` 的 `client` fixture、`tests/unit/test_webapi_onboarding.py:19` 的 `client` fixture）。
- 唯一与路由表面直接绑定的测试是 `tests/contract/test_web_route_contract.py`：把 `create_app(AppContext(tmp_path/"vault", tmp_path/"work", "UTC"), static_dir=tmp_path)` 产出的 route contract 与 `docs/contracts/web-route-contract.json` **逐字段全等比较**。
- `tests/conftest.py` 只有一个 autouse fixture `isolate_home`（把 `HOME` 指向临时目录）。

---

## 3. 目标模块划分

命名全部沿用既有约定（`webapp/<helper>.py` 或 `webapp/routers/<domain>.py`），**不新建顶层包**，不重命名既有模块。

### 3.1 共享 seam 模块（8 个，无路由 / 或承载受限 app 工厂）

| # | 目标路径 | 职责 | 接收的符号（来源行） | 现有测试 |
| --- | --- | --- | --- | --- |
| S1 | `webapp/mutation_runtime.py` | 本地事务与同步守卫的**单例运行时对象**；持有 `profile_switch_in_progress`，打破 F↔P 环 | `_current_sync_snapshot`(2977)、`_run_web_mutation`(2986)、`_sync_blocked`(3014)、`_mutation_blocked`(3051)、`_sync_payload`(3068)、`_commit_suffix`(339) | `tests/unit/test_webapi_sync.py`、`tests/unit/test_sync_conflict_recovery.py`、`tests/unit/test_web_security.py`、`tests/unit/test_active_profile_runtime.py` |
| S2 | `webapp/feishu_pool.py` | 飞书客户端生命周期 + 写回器工厂 | `_FeishuClientPool`(231–312，含 276 行 `inspect.signature` 兼容分支)、`_build_task_creator`(394)、`_build_meeting_creator`(425) | `tests/unit/test_feishu_lifecycle.py`、`tests/unit/test_lock_root_unified.py`、`tests/unit/test_webapi.py::_stub_feishu_writes` |
| S3 | `webapp/knowledge_sources.py` | 只读知识来源白名单（唯一真源） | `KNOWLEDGE_SOURCE_ROOTS`(659)、`SOURCE_BODY_DISPLAY_CHARS`(673)、`_is_knowledge_source`(676) | `tests/unit/test_webapi.py`（`:334` 直接 import 常量） |
| S4 | `webapp/ask_view.py` | 问答 workflow ↔ HTML 桥 | `_ask_html`(494)、`_cited_source_ids`(472) | `tests/unit/test_webapi.py:711`、`tests/unit/test_web_security.py:160` |
| S5 | `webapp/meeting_import.py` | 会议逐字稿导入链路 | `_run_web_import`(545)、`_load_model_config_for_context`(216) | `tests/unit/test_web_security.py:178`、`tests/unit/test_webapi.py` |
| S6 | `webapp/request_boundary.py` | 异常处理器 + 两个 HTTP 中间件（**顺序敏感**） | `_validation_error`(1160)、`_http_error`(1176)、`_mutation_blocked_error`(1196)、`_unexpected_error`(1207)、`_security_boundary`(1218)、`_cache_policy`(1306)、`_restricted_validation_error`(706)、`_restricted_boundary`(724) | `tests/unit/test_web_security.py`、`tests/unit/test_web_session.py`、`tests/unit/test_panel_lifecycle_baseline.py` |
| S7 | `webapp/app_shell.py` | 首页（SPA/SSR 二选一）+ `/static` 挂载 + `_dashboard` | `_dashboard`(1322)、`spa_index`/`app.mount`(1340–1342)、`spa_home`(1344)、`home`(1350)、`_build_info`(1303) | `tests/unit/test_webapp.py::test_spa_served_when_static_built`、`tests/unit/test_webapi_sync.py`（`/api/state` 的 runtime 字段） |
| S8 | `webapp/restricted_app.py` | 受限（空安装）应用工厂 | `_create_restricted_app`(683–1095) 整体，含 `remote_stages` | `tests/unit/test_webapi_onboarding.py`、`tests/unit/test_onboarding_wizard.py`、`tests/unit/test_remote_onboarding.py` |

### 3.2 路由模块（14 个，其中 2 个是扩展既有模块）

| # | 目标路径 | 职责 | 接收的路由（现行号） | 接收的符号 | 现有测试 |
| --- | --- | --- | --- | --- | --- |
| R1 | `routers/system.py` **（扩展）** | 握手/会话 + 面板退出 + 受限握手 | `POST /api/shutdown`(2697)；新增 `register_restricted_system_routes` 收 `GET /`(778)、`GET /api/version`(784)、`GET /api/session/bootstrap`(808) | 无新 helper | `tests/unit/test_webapp.py`（`:187` patch `webapp.app.os._exit`）、`tests/unit/test_web_session.py` |
| R2 | `routers/settings.py` **（扩展）** | 全部 settings/profile/automation | 13 条：1374/1388/1437/1484/1535/1570/1585/1603/1629/1672/1676/1708/1729 | `_settings_home`(1371)、`_automation_settings_payload`(1649)；**注入** `runtime: MutationRuntime`、`build_info: Callable[[], WebBuildInfo]` | `tests/unit/test_profile_settings.py`、`tests/unit/test_automation_settings.py`、`tests/unit/test_active_profile_runtime.py` |
| R3 | `routers/onboarding.py` **（新）** | 完整 app 与受限 app 的 onboarding | 完整 5 条：2877/2890/2906/2927/2946；受限 11 条：842/852/859/882/889/942/997/1016/1031/1051/1069 | `_onboarding_rejected`(2864)、`_rejected`(831)；**注入** `active_workspace`（受限侧） | `tests/unit/test_webapi_onboarding.py`、`tests/unit/test_onboarding_wizard.py`、`tests/unit/test_remote_onboarding.py` |
| R4 | `routers/state.py` **（新）** | 看板聚合只读端点 | `GET /api/state`(1750) | 无；**注入** `runtime`、`build_info`、`server_instance`/`started_at`/`panel_mode` | `tests/unit/test_project_state.py`、`tests/unit/test_webapi.py`、`tests/unit/test_web_security.py` |
| R5 | `routers/review.py` **（新）** | 审批读取、决策、只读来源 + SSR 审批页 | JSON 7 条：1815/1820/1846/1896/1918/1942/1971；SSR 4 条：2778/2783/2803/2833 | `_load`(315)、`_plan_text`(323)、`_is_knowledge_source`(S3)；**注入** `runtime` | `tests/unit/test_webapi.py`、`tests/unit/test_web_security.py`、`tests/unit/test_web_session.py`、`tests/unit/test_webapp.py` |
| R6 | `routers/review_apply.py` **（新）** | apply 与外部动作对账 + SSR apply | JSON 3 条：1979/1985/2038；SSR 1 条：2841 | `_plan_text`；**注入** `runtime`、`feishu_clients`（供 creator 工厂） | `tests/unit/test_webapi.py`、`tests/unit/test_review_apply_threads.py`、`tests/unit/test_webapp.py` |
| R7 | `routers/threads.py` **（新）** | 线程状态/日志/产物/活动一致性 | 4 条：2075/2116/2129/2204 | `_thread_activity_migration`(369)；**注入** `runtime` | `tests/unit/test_thread_notes.py`、`tests/unit/test_project_state.py`、`tests/unit/test_thread_activity.py` |
| R8 | `routers/capture.py` **（新）** | inbox 捕获 + 任务/会议信号写回 | 4 条：2275/2344/2378/2433 | 无；**注入** `runtime`、`feishu_clients` | `tests/unit/test_capture.py`、`tests/unit/test_webapi.py`、`tests/unit/test_active_profile_runtime.py` |
| R9 | `routers/brief.py` **（新）** | 简报/复盘生成 + SSR 重定向 | JSON 2 条：2494/2529；SSR 2 条：2719/2743 | `_commit_suffix`（经 `runtime` 暴露）；**注入** `runtime` | `tests/unit/test_webapi_sync.py`（`:215` patch `_commit_suffix`）、`tests/unit/test_webapp.py` |
| R10 | `routers/ask.py` **（新）** | 问答 JSON + SSR | JSON 1 条：2550；SSR 1 条：2765 | 无；**注入** `runtime`（守卫），`_ask_html` 从 S4 读取 | `tests/unit/test_webapi.py`、`tests/unit/test_web_security.py` |
| R11 | `routers/meetings.py` **（新）** | 逐字稿导入上传 | 1 条：2593 | `_run_web_import`(S5)、`_run_web_mutation`（2628） | `tests/unit/test_web_security.py`、`tests/unit/test_webapi.py` |
| R12 | `routers/undo.py` **（新）** | Git 撤销三端点 | 3 条：2636/2650/2661 | `_undo_error_response`(380)；**注入** `runtime` | `tests/unit/test_webapi_undo.py` |
| R13 | `routers/sync.py` **（新）** | 同步状态/冲突/导出/主设备 | 11 条：3088/3093/3100/3107/3142/3188/3222/3267/3391/3396/3440 | `_sync_payload`(3068)；**注入** `runtime` | `tests/unit/test_webapi_sync.py`、`tests/unit/test_sync_conflict_recovery.py`、`tests/unit/test_sync_hardening.py` |
| — | `routers/workspace.py` / `routers/diagnostics.py` / `routers/projects.py` | — | **不动** | — | — |

**路由配平**：1(R1 shutdown) + 13(R2) + 16(R3) + 1(R4) + 11(R5) + 4(R6) + 4(R7) + 4(R8) + 4(R9) + 2(R10) + 1(R11) + 3(R12) + 11(R13) = **75**；加 S7 保留的 `/` = 76；加受限侧 3 条(R1) = **79** ✅ 与 §1.2 的 79 个生效注册点一致。

**关于 SSR 路由归属的取舍**：`legacy_app.py:2717` 的注释把 8 条 SSR 路由视为一个块。本蓝图**按领域拆分**（R5/R6/R9/R10），而不是建一个 `routers/ssr.py`「god module」——理由是 SSR handler 与对应 JSON handler 共享同一个 workflow、同一个守卫、同一个渲染函数（`render_review`/`render_plan`/`render_dashboard`），拆开反而制造横切依赖。若迁移中发现某条 SSR 路由的注入清单超过 4 项，再退回单一 `routers/ssr.py` 方案。

---

## 4. 依赖方向

### 4.1 允许的 import 方向（只允许向下）

```
                      app_factory.py  （唯一公开装配点，只调用 register_*，不定义路由）
                              │
        ┌─────────────────────┴─────────────────────┐
        ▼                                           ▼
  legacy_app.py（过渡 facade）              routers/*（领域路由）
        │                                           │
        └─────────────────┬─────────────────────────┘
                          ▼
   webapp 共享 seam：mutation_runtime / feishu_pool / knowledge_sources /
   ask_view / meeting_import / request_boundary / app_shell / restricted_app
                          │
                          ▼
   webapp 基础层（既有，不动）：context / dependencies / api / errors / security /
   mutation_response / presenters / build_info / runtime / views / services
                          │
                          ▼
   repositories/ · workflows/ · providers/ · domain/ · observability/ · config/
```

**五条硬规则**：

1. `routers/*` **禁止** `import summit_workbench.webapp.legacy_app`（本轮最大的环风险）。
2. 共享 seam **禁止** `import routers/*`，也禁止 import `legacy_app`。
3. 基础层（`api.py` / `security.py` / `dependencies.py` / `context.py` …）保持叶子，**禁止**向上 import。
4. `legacy_app.py` 只做「向外 import + 再导出兼容别名」，任何模块都不得 import 它（除过渡期的 `app.py` / `app_factory.py`）。
5. 路由之间**不得互相 import**。若两个路由模块需要同一个 helper，helper 下沉到共享 seam 或 `webapp` 基础层。

### 4.2 必须避免的三个环

| 环 | 成因 | 打破方式 |
| --- | --- | --- |
| `mutation_runtime` ↔ `routers/settings` | `_run_web_mutation`(2989) **读** `profile_switch_in_progress`，而该变量被 settings handler(1572/1587) **写**。朴素拆分会变成「runtime 要 import settings 拿状态，settings 要 import runtime 跑事务」 | **把标志位搬进 `MutationRuntime` 实例**：`runtime.begin_profile_switch()` / `runtime.end_profile_switch()` / `runtime.profile_switch_in_progress`。settings 单向依赖 runtime，环消失 |
| `mutation_runtime` ↔ `routers/sync` | `_sync_payload` 只被 `routers/sync` 用，但 `_current_sync_snapshot` 被 `api_state`(1755) 也用 | `snapshot()` 留在 `MutationRuntime`（唯一状态源）；`sync_payload()` 作为纯编码函数放 `routers/sync.py`。两条边都指向 runtime，单向 |
| `feishu_pool` ↔ `routers/review_apply` / `routers/capture` | K/I/N 三个集群都要 `_build_task_creator` / `user_client()` | creator 工厂放 S2；**由 factory 构造好 `FeishuClientPool` 后作为关键字参数注入**给 R6/R8（与 `routers/projects.py` 注入 `run_mutation` 完全同构）。S2 不认识任何路由 |

### 4.3 `_run_web_mutation` 的具体处理方案

现状是 `create_app` 内的闭包：

```python
def _run_web_mutation[T](action: str, mutation: Callable[[str], LocalMutationOutcome[T]]
) -> LocalMutationResult[T]:
    if profile_switch_in_progress: ...      # ← 来自 settings 集群
    profile = ctx.active_workspace.profile if ctx.active_workspace else None
    return run_local_mutation(ctx.vault_dir, action, mutation,
        sync_snapshot=..., sync_snapshot_provider=..., compatibility=ctx.compatibility, ...)
```

目标形态（`webapp/mutation_runtime.py`）：

```python
class MutationRuntime:
    """本地事务 + 同步守卫的唯一运行时。所有路由通过注入获得，不自行构造。"""

    def __init__(self, context: WebContext) -> None: ...
    @property
    def profile_switch_in_progress(self) -> bool: ...
    def begin_profile_switch(self) -> None: ...  # 供 routers/settings.py 调用
    def end_profile_switch(self) -> None: ...
    def snapshot(self) -> SyncSnapshot: ...  # 原 _current_sync_snapshot
    def run[T](self, action, mutation) -> LocalMutationResult[T]: ...  # 原 _run_web_mutation
    def sync_blocked(self, request) -> JSONResponse | None: ...  # 原 _sync_blocked
    def mutation_blocked(self, request) -> JSONResponse | None: ...  # 原 _mutation_blocked
    def commit_suffix(self, paths, summary) -> str: ...  # 原 _commit_suffix
```

- **PEP 695 泛型**：`def _run_web_mutation[T](...)` → `def run[T](self, ...)`，Python 3.12 语法不变，`target-version = "py312"` 支持；但 `mypy strict` 必须复跑。
- **`_sync_payload` 不入 runtime**：它只被 R13 用（3088/3391 两处），且是纯编码 → 随 R13 走。
- **`_commit_suffix` 入 runtime**：它同时被 R9（brief/weekly）用；且 `tests/unit/test_webapi_sync.py:215` 对它有 monkeypatch 契约（见 §6-R3）。
- **`MutationRuntime` 的构造点**：`legacy_app.create_app` 中 `ctx is not None` 之后、任何 `register_*` 之前创建一次，然后作为关键字参数向下传；**不得做成模块级单例**（否则同进程多 app 共享状态，破坏现有 per-app 语义，见 §6-R8）。

---

## 5. 迁移顺序

**通用验证三连**（每一步都必须跑，下文各步只列额外命令）：

```bash
# ① 路由表面零变化（最重要，失败即回滚）
uv run pytest tests/contract/test_web_route_contract.py -q

# ② 领域回归
uv run pytest tests/unit/<该领域的测试> -q

# ③ 完整质量门（含 ruff / mypy(strict) / 覆盖率 ≥ 80%）
WB_GATE_FAST=1 scripts/pre-push-gate.sh      # 完整版去掉 WB_GATE_FAST=1
```

> ⚠️ **禁止**用 `scripts/update-web-route-contract.py` 重新生成快照来「修」①的失败。快照变化 = 行为变化 = 本步失败。

### Step 0 · 基线冻结（不改代码）

```bash
wc -l src/summit_workbench/webapp/legacy_app.py            # 期望 3457
shasum -a 256 docs/contracts/web-route-contract.json
uv run pytest --cov=summit_workbench --cov-report=term-missing --cov-fail-under=80 -q
```

**判据**：全绿并记录基线覆盖率数字（后续每步不得低于它）。

### Step 1 · 抽出 `webapp/knowledge_sources.py`（B11，24 行）

- 迁移 `KNOWLEDGE_SOURCE_ROOTS` / `SOURCE_BODY_DISPLAY_CHARS` / `_is_knowledge_source`。
- `legacy_app.py` 保留再导出：`from ...knowledge_sources import KNOWLEDGE_SOURCE_ROOTS, SOURCE_BODY_DISPLAY_CHARS, _is_knowledge_source`（`tests/unit/test_webapi.py:334` 直接从 `legacy_app` import）。
- **验证**：`uv run pytest tests/unit/test_webapi.py -q -k "sources_read or review_source"`

### Step 2 · 抽出 `webapp/feishu_pool.py`（B2 + B7，158 行）

- **必须原样保留** `_get` 中的 `if "token_provider" in inspect.signature(FeishuClient).parameters:` 分支（276 行）——`tests/unit/test_webapi.py:1062` 用 2 参数 lambda 替换 `FeishuClient` 正是走这条 fallback。
- **验证**：`uv run pytest tests/unit/test_feishu_lifecycle.py tests/unit/test_lock_root_unified.py tests/unit/test_webapi.py -q`

### Step 3 · 抽出 `webapp/mutation_runtime.py`（P + B4，144 行）

- 建立 `MutationRuntime`（§4.3），`legacy_app` 内改用它；`profile_switch_in_progress` 从闭包变量变为实例属性，1572/1587 的 `nonlocal` 改为 `runtime.begin_profile_switch()` / `runtime.end_profile_switch()`。
- ⚠️ **本步必须同时修改 `tests/unit/test_webapi_sync.py:215`** 的 patch 目标：`summit_workbench.webapp.legacy_app._commit_suffix` → `summit_workbench.webapp.mutation_runtime._commit_suffix`。仅靠 `legacy_app` 再导出别名**无效**：`api_run_brief` 迁移后读取的是自己模块的 global，patch `legacy_app` 的属性不会影响它。
- **验证**：`uv run pytest tests/unit/test_webapi_sync.py tests/unit/test_sync_conflict_recovery.py tests/unit/test_web_security.py tests/unit/test_active_profile_runtime.py -q`

### Step 4 · 抽出 `webapp/request_boundary.py`（D2 + D3 + D4 中间件部分，≈160 行）

- 导出 `install_exception_handlers(app, operation_id)`、`install_security_boundary(app, ...)`、`install_cache_policy(app)`、`install_restricted_boundary(app, ...)`。
- ⚠️ **调用顺序 = 行为**：必须仍是 security 先、cache 后（Starlette 1.6.0 `applications.py:107 insert(0)` + `:81 reversed` ⇒ **后注册者在外层**）。
- **验证**：`uv run pytest tests/unit/test_web_security.py tests/unit/test_web_session.py tests/unit/test_panel_lifecycle_baseline.py -q`
  附加：`python -c "from ...; print([m.cls.__name__ for m in app.user_middleware])"` 与 Step 0 记录值逐项比对。

### Step 5 · 抽出 `webapp/restricted_app.py`（C1–C4，413 行）

- `_create_restricted_app` → `create_restricted_app()`；`legacy_app` 保留 `_create_restricted_app = create_restricted_app` 别名（1109–1124 的调用点同步改）。
- 本步**只搬工厂，不拆 C3 的路由**（一次只动一件事）。
- **验证**：`uv run pytest tests/unit/test_webapi_onboarding.py tests/unit/test_onboarding_wizard.py tests/unit/test_remote_onboarding.py tests/unit/test_active_profile_runtime.py -q`

### Step 6 · 抽出 `routers/sync.py`（Q，368 行，11 条路由）—— 单笔收益最大

- `register_sync_routes(dependencies, *, runtime: MutationRuntime)`；`_sync_payload` 随迁为模块内私有函数。
- **验证**：`uv run pytest tests/unit/test_webapi_sync.py tests/unit/test_sync_conflict_recovery.py tests/unit/test_sync_hardening.py tests/unit/test_sync_conflict.py -q`

### Step 7 · 扩展 `routers/settings.py`（F，378 行，13 条路由）

- 新增 `register_settings_routes(dependencies, *, runtime, build_info)`。
- ⚠️ `switch_plans` / `remote_normalization_plans` **在 register 函数体内创建**（闭包捕获），**不要**提升为模块级 dict —— 后者会让同进程的多个 app 实例共享状态，改变现有语义并污染测试。
- **验证**：`uv run pytest tests/unit/test_profile_settings.py tests/unit/test_automation_settings.py tests/unit/test_active_profile_runtime.py -q`

### Step 8 · 抽出 `routers/state.py`（G 前半，57 行，1 条路由）

- 注入 `runtime`、`build_info`、`server_instance`/`started_at`/`panel_mode`（`build_info` 注入方式照抄 `routers/system.py:30`）。
- **验证**：`uv run pytest tests/unit/test_webapi.py -q -k "state"`

### Step 9 · 抽出 `routers/review.py`（H + SSR 2778/2783/2803/2833，≈250 行，11 条路由）

- **验证**：`uv run pytest tests/unit/test_webapi.py tests/unit/test_web_security.py tests/unit/test_web_session.py tests/unit/test_webapp.py -q`

### Step 10 · 抽出 `routers/review_apply.py`（I + SSR 2841，≈130 行，4 条路由）

- **注入 `feishu_clients`**（2048–2049 与 2851–2852 的 creator 构造需要）。
- **验证**：`uv run pytest tests/unit/test_webapi.py tests/unit/test_review_apply_threads.py tests/unit/test_webapp.py -q`

### Step 11 · 抽出 `routers/threads.py`（J，199 行，4 条路由）

- **验证**：`uv run pytest tests/unit/test_thread_notes.py tests/unit/test_project_state.py tests/unit/test_thread_activity.py -q`

### Step 12 · 抽出 `routers/capture.py`（K，218 行，4 条路由）

- **注入 `feishu_clients`**（2358/2402/2455）。
- **验证**：`uv run pytest tests/unit/test_capture.py tests/unit/test_webapi.py -q -k "capture or task or meeting_update"`

### Step 13 · 抽出 `webapp/ask_view.py`（S4）+ `routers/brief.py`（R9）+ `routers/ask.py`（R10）

- ⚠️ **三处 monkeypatch 契约必须同步更新**（见 §6-R3）：`tests/unit/test_webapi.py:711`、`tests/unit/test_web_security.py:160`、`tests/unit/test_web_security.py:178`；以及 `webapp/app.py:14` 的 import 来源与 31–32 行的传播垫片。
- 建议**单独一个 commit 只做这一步**，因为它是唯一同时触碰 `app.py` 公共兼容层的步骤。
- **验证**：`uv run pytest tests/unit/test_webapi.py tests/unit/test_web_security.py tests/unit/test_webapi_sync.py tests/unit/test_webapp.py -q`

### Step 14 · 抽出 `routers/meetings.py`（R11）+ `routers/undo.py`（R12）

- `api_meetings_import` 的 `inspect.signature(_run_web_import)` 分支（2627–2630）随迁；若 S5 改为**依赖注入 `run_mutation`** 而非 `inspect.signature` 探测，那是行为改进——**本蓝图不批准**，保持原样。
- **验证**：`uv run pytest tests/unit/test_web_security.py tests/unit/test_webapi_undo.py -q`

### Step 15 · 抽出 `routers/onboarding.py`（R3）+ 扩展 `routers/system.py`（R1）

- `register_onboarding_routes(dependencies)`（完整 app，5 条）+ `register_restricted_onboarding_routes(app, *, active_workspace, operation_id)`（受限 app，11 条）。
- `routers/system.py` 增加 `register_restricted_system_routes(app, *, static_dir, server_instance, started_at, panel_mode, session_token, workspace_id, device_id, build_info)`；`POST /api/shutdown` 也归入此模块。
- ⚠️ `/api/version` 在**两个 app 上各有一份实现**（784 受限、`routers/system.py:37` 完整）。不要合并成一个函数——受限版本没有 `RouteDependencies`、不加 `Cache-Control` 头。
- **验证**：`uv run pytest tests/unit/test_webapi_onboarding.py tests/unit/test_onboarding_wizard.py tests/unit/test_webapp.py tests/unit/test_web_session.py -q`

### Step 16 · 抽出 `webapp/app_shell.py`（S7）+ `legacy_app.py` 收尾

- 目标：`legacy_app.py` 只剩 `create_app(ctx, ...)` facade（构造 `FeishuClientPool` + `MutationRuntime` + `lifespan` → 按序调用各 `register_*`）+ 兼容再导出，**目标 ≤ 250 行**（相对 3457 行）。
- 收尾时**保留**这些再导出（不得删除）：`KNOWLEDGE_SOURCE_ROOTS`、`SOURCE_BODY_DISPLAY_CHARS`、`_ask_html`、`_run_web_import`、`_commit_suffix`、`WebContext`。
- **判据（本步唯一的最终验收）**：

```bash
uv run pytest -q                                     # 全量
uv run pytest tests/contract/test_web_route_contract.py -q
uv run pytest --cov=summit_workbench --cov-fail-under=80 -q
uv run ruff check . && uv run ruff format --check . && uv run mypy
scripts/pre-push-gate.sh                             # 完整门（含前端）
git diff --stat docs/contracts/web-route-contract.json   # 必须无输出
```

---

## 6. 风险点与对策

> 全部风险均已用 `grep`/`ast` 在仓库中验证，附**文件:行**证据。

### R1 · `route_contract.py` 是**源码级**契约（最高风险）

**证据**：`src/summit_workbench/webapp/route_contract.py:56` 对每个 endpoint 调 `inspect.getsource(route.endpoint)`，`:59` 用 `_ERROR_CODE_RE = re.compile(r"code\s*=\s*[\"']([^\"']+)[\"']")` 从**源码文本**里抽 error code；`tests/contract/test_web_route_contract.py:19` 把结果与 `docs/contracts/web-route-contract.json`（82 条）**全等比较**。

**具体触发条件**：

- 把 handler 内联的 `error_payload(code="...")` 提取成**被多个 handler 共用的 helper** → 该 code 从 endpoint 源码里消失。已确认当前**内联且被快照记录**的 code 有：`acceptance_preflight_failed` / `workspace_not_configured`（`/api/settings/acceptance-preflight`）、`invalid_build_manifest`（`/api/version`）、`authentication_required`（`/api/session/bootstrap`）、`workspace_not_configured`（`/api/sync/primary/claim`、`/api/workspace/migration`）、`ask_unavailable`（`/api/ask`），以及 `routers/settings.py` 里 feishu 相关的 6 个 code。
  反例（安全）：`GET /api/undo/diff` 与 `POST /api/undo/revert` 的快照 `error_codes` 就是 `[]`——因为 code 早已在 `_undo_error_response`(380) 里，`inspect.getsource` 看不到。**把内联 code 外移是行为变化，反之亦然。**
- 用装饰器/工厂**包裹** handler → `getsource` 返回包装器源码。
- 在 handler 上做 `functools.partial` / 动态注册 → `getsource` 抛 `TypeError`，`source = ""`，error code 全丢。

**对策**：① handler 函数体**逐字搬运**，不改字符串、不抽 code；② 不引入任何 handler 包装层；③ 每步先跑契约测试，失败即回滚；④ **禁止**用 `scripts/update-web-route-contract.py` 刷新快照掩盖差异。

### R2 · `request_model` 依赖 `get_type_hints` 的模块 globals

**证据**：`route_contract.py:31` `hints = get_type_hints(route.endpoint, include_extras=True)`，异常被吞成 `hints = {}`；`_request_model` 随后回退到 `parameters.get(field.name)` 的**裸注解**，若该注解是字符串化/未解析形式则拿不到 `__name__` → `request_model` 变 `None`。快照里 **38 个 route 带请求体模型**，任何一个变 `None` 都会 break。

**具体触发条件**：新模块把 payload 模型写成**函数内局部 import** 或 `if TYPE_CHECKING:` import。`legacy_app.py` 现在把 30+ 个 payload 模型放在**模块顶层**（97–134），所以 `get_type_hints` 能解析。

**对策**：每个新路由模块**必须**在模块顶层 `from summit_workbench.webapp.api import <payload>`，写法照抄 `routers/workspace.py:10` 与 `routers/projects.py:16`。这是 `routers/` 现有的既有约定，也是硬性要求。代码库里大量「函数内 import 重依赖」的风格（如 `legacy_app.py:218`、`256`、`1364`）**不适用于 payload 模型**。

### R3 · 4 处 `monkeypatch` 把 `legacy_app` / `webapp.app` 当注入点

**证据（全部实测）**：

| # | 测试位置 | patch 目标 | 传播机制 |
| --- | --- | --- | --- |
| 1 | `tests/unit/test_webapi.py:711` | `summit_workbench.webapp.legacy_app._ask_html` | 直接 patch `legacy_app` 模块属性；`api_ask`(2565) 从自身 global 读取 → **搬走后失效** |
| 2 | `tests/unit/test_web_security.py:160` | `summit_workbench.webapp.app._ask_html` | `webapp/app.py:31` 在 `create_app` 内把 `app._ask_html` **回写**进 `legacy_app` → 间接生效 |
| 3 | `tests/unit/test_web_security.py:178` | `summit_workbench.webapp.app._run_web_import` | 同上，靠 `app.py:32` 回写 |
| 4 | `tests/unit/test_webapi_sync.py:215` | `summit_workbench.webapp.legacy_app._commit_suffix` | 直接 patch；`api_run_brief` 读取自身 global → **搬走后失效** |

**关键陷阱**：只在新模块里定义符号 + 在 `legacy_app` 里再导出别名，**不能让 patch #1 / #4 生效**——`monkeypatch.setattr("...legacy_app._ask_html", fake)` 改的是 `legacy_app.__dict__`，而迁移后的 handler 读的是 `routers.ask.__dict__`。

**对策**：把「搬迁符号」与「更新 patch 目标字符串」放在**同一个 commit**，并在该步的验收里明确跑对应测试文件。对 #2/#3，同步改写 `webapp/app.py:14/31/32` 的回写目标模块（`app.py` 是公共兼容层，`server_entry.py:19` 与原生壳通过 `webapp.app` 导入，不能删）。
**不得**把这三个 lambda 改成「通过依赖注入的假对象」——那是测试语义变化，超出「只移动、不改行为」的门。

### R4 · 常量 / 类型的直接 import 契约

**证据**：
- `tests/unit/test_webapi.py:334` `from summit_workbench.webapp.legacy_app import SOURCE_BODY_DISPLAY_CHARS`
- `tests/unit/test_webapp.py:58` `assert WebContext is legacy_app.WebContext`（`legacy_app.py:142` 是 `from ...context import WebContext as WebContext`）
- `tests/unit/test_webapp.py:187` `monkeypatch.setattr("summit_workbench.webapp.app.os._exit", ...)`（依赖 `app.py:7 import os` + `:45 __all__` 含 `"os"`；patch 的是 `os` 模块对象本身，所以 `/api/shutdown` 搬到哪都安全）

**对策**：`legacy_app.py` **永久保留**这些再导出（写进 Step 16 的验收清单）。`WebContext` **不得**在新模块里重新定义，只能从 `webapp/context.py` 转出。

### R5 · 覆盖率门 80%

**证据**：`pyproject.toml [tool.coverage.run] omit = ["*/webapp/views.py"]`（**只豁免 views.py**）；`[tool.coverage.report] fail_under = 80`；`.github/workflows/ci.yml:71` `--cov-fail-under=80`；`scripts/pre-push-gate.sh` 同一门。

**影响**：拆分本身不改变已覆盖行，但**新模块的模块级语句**（imports、常量、`if` 分支）都计入分母。所有 `register_*` 与 seam 模块都会被任何 `create_app()` 调用加载，所以导入行天然覆盖；风险在**条件式模块级逻辑**与**兼容再导出的 `try/except ImportError`**。

**对策**：新模块内**禁止**模块级 `if`/`try-except`/版本探测；兼容别名用无条件 `from … import … as …`。每步跑 `uv run pytest --cov=summit_workbench --cov-report=term-missing --cov-fail-under=80 -q` 并确保不低于 Step 0 基线。

### R6 · 中间件顺序 = HTTP 行为

**证据**：本机 starlette **1.6.0**，`.venv/.../starlette/applications.py:107` `self.user_middleware.insert(0, ...)`，`:81` `for cls, args, kwargs in reversed(middleware)`。⇒ **最后注册的中间件在最外层**。当前 `legacy_app.py:1218` 先注册 `_security_boundary`（内层）、`:1306` 后注册 `_cache_policy`（外层）。因此被安全边界拒绝的 `POST /` 之类请求，**仍会被 `_cache_policy` 补上 `Cache-Control` 头**；`_unexpected_error` 由 `ServerErrorMiddleware` 承载，在最外层。

**对策**：`install_security_boundary(app, ...)` 必须**先于** `install_cache_policy(app)` 调用（Step 4 明确写出）；重构后加一条断言 `[m.cls.__name__ for m in app.user_middleware]` 与基线逐项比对。

### R7 · `/` 与 `/static` 的注册时机

**证据**：`legacy_app.py:1340–1352` —— `app.mount("/static", StaticFiles(...))` 与 `GET /` 在 `if spa_index.is_file()` 分支内就地注册，**位置在所有 API 路由之前**；`tests/unit/test_webapi.py::test_spa_served_when_static_built` 覆盖 SPA 分支，`test_webapp.py::_client` 用不存在的 static 目录覆盖 SSR 分支。

**对策**：Step 16 抽出 `app_shell.py` 时，把 `install_app_shell(app, ctx, spa_dir)` 的调用点放在 factory 中**完全相同的位置**（在 settings/state/review 等 `register_*` 之前）。当前无路径冲突（`/static`、`/` 与任何 API 路径都不重叠），但注册顺序会影响 `app.routes` 列表与 OpenAPI 输出顺序。

### R8 · 闭包状态必须保持 per-app 语义

**证据**：`switch_plans`(1152)、`remote_normalization_plans`(1153)、`remote_stages`(704)、`profile_switch_in_progress`(1154) 全部定义在工厂函数体内 ⇒ 每次 `create_app()` 得到**全新实例**。测试大量在同一进程内创建多个 app（`tests/unit/test_webapi.py::_client`、`tests/unit/test_webapi_sync.py::client`、`tests/unit/test_webapi_onboarding.py::client`）。

**对策**：这些状态改为（a）`MutationRuntime` 实例属性，或（b）`register_*` 函数体内的闭包变量。**严禁**提升为模块级可变对象 —— 会造成跨测试污染与并发串扰。

### R9 · 迁移期 import 环

**证据**：`routers/settings.py:197 _invalidate_feishu_client(app)` 通过 `getattr(app.state, "feishu_clients", None)` 反向依赖主 app 的 state —— 这是**已存在的**隐式反向依赖，说明「router 读 app.state」在本仓库已被接受。但**不能**因此允许 `router → legacy_app` 的 import。

**对策**：§4.1 的五条硬规则；Step 4/5 之前不得开始 Step 6+；每次新增 `routers/*` 时用 `grep -rn "legacy_app" src/summit_workbench/webapp/routers/` 断言为空。

### R10 · `app.state.feishu_clients` 与 lifespan 时序

**证据**：`legacy_app.py:1126` 构造池、`:1140 lifespan` 关闭、`:1148 app.state.feishu_clients = feishu_clients`；`routers/settings.py:197` 读它；`tests/unit/test_feishu_lifecycle.py:39–40` 与 `tests/unit/test_lock_root_unified.py:113` **直接读 `app.state.feishu_clients`**。

**关键时序**：`app_factory.py:50/59` 在 `_create_legacy_app` **返回之后**才注册 diagnostics / settings_connection 路由，而 `_invalidate_feishu_client` 在请求期才 `getattr`，所以把池的构造留在 factory 内、赋值给 `app.state` 的位置**不变**即可。

**对策**：池仍由 `legacy_app.create_app` 构造并 `app.state.feishu_clients = pool`；仅把**类定义**搬到 `webapp/feishu_pool.py`（Step 2），把**注入给路由**做成显式关键字参数（Step 10/12）。

### R11 · `ruff` / `mypy` 质量门

**证据**：`pyproject.toml`：`[tool.ruff] line-length = 100`、`select = ["E","F","I","UP","B"]`、per-file-ignores **只覆盖 `views.py` 与 `scripts/guide_to_html.py`**；`[tool.mypy] strict = true, files = ["src","tests"]`，只有 `tests.*` 与 `repositories.dulwich_git` 有放宽。`legacy_app.py:12` 与 `routers/settings.py:5` 各自带 `# ruff: noqa: E501`。

**对策**：任何继承长行的新模块必须自带 `# ruff: noqa: E501`（并附一行理由注释，照抄 `routers/settings.py:3–5` 的写法）；新代码必须全注解，`def run[T](self, ...)` 这类 PEP 695 泛型方法要单独跑 `./.venv/bin/mypy` 确认。**不得**往 `pyproject.toml` 加新的 per-file-ignore。

### R12 · 打包（已核实：**无风险**，但需保持）

**证据**：`packaging/SummitWorkbenchServer.spec` 用 `collect_submodules("summit_workbench")`；`tests/unit/test_packaging_contract.py` 只断言该字符串存在。新模块在 `summit_workbench.webapp` 包内 ⇒ 自动被收集。

**对策**：不新增顶层包、不改 `packaging/*.spec`、不改 `server_entry.py`（它以 `from summit_workbench.webapp.app import WebContext, create_app` 导入，见 `server_entry.py:19`）。`tests/unit/test_packaging_contract.py:22/31` 对 `server_entry.py` 做源码文本断言，**动它就等于动契约**。

### R13 · `legacy_app.py` 的高改动率带来的合并冲突

**证据**：`git log --oneline -12 -- src/summit_workbench/webapp/legacy_app.py` 显示最近 12 个 commit 全部触碰该文件（`2a3719e`、`562c4fd`、`7e25cd3`、`7b20002`、`a851f70`、`cb1bd34`、`050ec07` …）。

**对策**：每个 Step 一个独立 commit、当次推送；长生命周期的分支会与主干持续冲突。Step 3（mutation runtime）与 Step 4（middleware）务必**串行**，不要并行开工。

### 已核实**不存在**的风险（明确排除）

- **没有任何测试把 `legacy_app.py` 当文本读取**。`grep -rn "legacy_app.py\|legacy_app\"" tests/` 返回空；`tests/unit/test_packaging_contract.py`、`tests/contract/test_ci_contract.py`、`tests/unit/test_native_panel_contract.py` 读的是 `packaging/*.spec`、`scripts/*`、`native/*.swift`、`web/src/*`、`.github/workflows/*`，**不含** `webapp/legacy_app.py`。
- **没有测试引用 `_create_restricted_app`**（全仓库仅 `legacy_app.py:683` 定义、`:1115` 调用）。
- **路由注册顺序不影响契约快照**：`route_contract.py:70` 按 `(path, method)` 排序输出。
- **`/api/version` 在两个 app 上的重复定义不冲突**：分属不同 `FastAPI` 实例。
- **`tests/unit/test_ci_contract.py` 位于 `tests/contract/`，不读 `webapp/`**（任务描述中提到的 `tests/unit/test_ci_contract.py` 实际路径是 `tests/contract/test_ci_contract.py`）。

---

## 7. 明确不做的事（非目标）

1. **不改任何公共 import 路径**：`summit_workbench.webapp.create_app`、`summit_workbench.webapp.app.create_app`、`summit_workbench.webapp.app_factory.create_app` 三者签名与行为不变（`server_entry.py:19`、CLI、原生壳依赖）。
2. **不移动目录、不新建顶层包、不重命名既有 `webapp/*.py` 与 `routers/*.py`**。
3. **不改 `docs/contracts/web-route-contract.json`**；不改 `route_contract.py` 的提取算法。
4. **不改会话/错误 envelope**、不改 `_SCHEMA_UPGRADE_WRITE_EXEMPTIONS`(206–213)、不改 `KNOWLEDGE_SOURCE_ROOTS`(659–670)。
5. **不引入 `APIRouter`**（与既有 `routers/` 约定不符，且会改变 `inspect.getsource` 与 `get_type_hints` 的解析上下文）。
6. **不改测试语义**：只允许更新 monkeypatch 的目标字符串与 import 来源；不允许把集成测试改成 mock 注入。
7. **不删除任何再导出别名**（`_ask_html`、`_run_web_import`、`_commit_suffix`、`SOURCE_BODY_DISPLAY_CHARS`、`KNOWLEDGE_SOURCE_ROOTS`、`WebContext`）。

---

## 8. 附录

### 8.1 验证命令清单（可直接复制）

```bash
# 契约（每步必跑，最高优先级）
uv run pytest tests/contract/test_web_route_contract.py -q

# 领域回归（按 §5 各步选择）
uv run pytest tests/unit/test_webapi.py tests/unit/test_webapi_sync.py tests/unit/test_webapp.py -q
uv run pytest tests/unit/test_web_security.py tests/unit/test_web_session.py -q
uv run pytest tests/unit/test_webapi_onboarding.py tests/unit/test_onboarding_wizard.py -q
uv run pytest tests/unit/test_webapi_undo.py tests/unit/test_capture.py -q
uv run pytest tests/unit/test_profile_settings.py tests/unit/test_automation_settings.py -q
uv run pytest tests/unit/test_sync_conflict_recovery.py tests/unit/test_sync_hardening.py -q
uv run pytest tests/unit/test_thread_notes.py tests/unit/test_thread_activity.py -q
uv run pytest tests/unit/test_feishu_lifecycle.py tests/unit/test_lock_root_unified.py -q

# 覆盖率门
uv run pytest --cov=summit_workbench --cov-report=term-missing --cov-fail-under=80 -q

# 静态检查
uv run ruff check . && uv run ruff format --check . && uv run mypy

# 完整本地门（= CI 门）
scripts/pre-push-gate.sh
WB_GATE_FAST=1 scripts/pre-push-gate.sh   # 跳过前端
```

### 8.2 关键文件索引

| 路径 | 为什么重要 |
| --- | --- |
| `docs/archive/decisions/0035-webapp-route-service-split.md` | 上位决策；「逐领域、逐快照迁移」的来源 |
| `docs/contracts/web-route-contract.json` | 82 条 route 的可执行快照；**冻结不动的产物** |
| `src/summit_workbench/webapp/route_contract.py` | 快照生成算法（源码级 error code + `get_type_hints` 模型名） |
| `scripts/update-web-route-contract.py` | 快照再生脚本；**禁止用它掩盖拆分引入的差异** |
| `src/summit_workbench/webapp/app_factory.py` | 唯一装配点；legacy 返回**之后**才挂 diagnostics/settings_connection |
| `src/summit_workbench/webapp/app.py` | 公共兼容层 + `_ask_html`/`_run_web_import` **monkeypatch 传播垫片**(31–32) |
| `src/summit_workbench/webapp/dependencies.py` | `RouteDependencies` 契约 |
| `src/summit_workbench/webapp/mutation_response.py` | `_commit_note` / `_mutation_fields` |
| `src/summit_workbench/webapp/services/workspace.py` | 唯一既有 service 模块，router→service 的样板 |
| `scripts/pre-push-gate.sh` | 本地质量门（ruff / format / mypy / pytest+覆盖率 / 前端契约） |
| `.github/workflows/ci.yml:71` | 远端覆盖率门 `--cov-fail-under=80` |
| `pyproject.toml` | ruff / mypy(strict) / coverage(omit 仅 views.py, fail_under 80) 配置 |
| `packaging/SummitWorkbenchServer.spec` | `collect_submodules` ⇒ 新模块免配置自动打包 |

### 8.3 拆分收益核算

| 阶段 | `legacy_app.py` 剩余行数（估算） | 移出的路由数 |
| --- | --- | --- |
| 现状 | 3457 | 0 |
| Step 1–5（seam + 受限 app） | ≈ 2400 | 0（但 14 条受限路由所在文件已独立） |
| Step 6–10（sync/settings/state/review/apply） | ≈ 1300 | 36 |
| Step 11–14（threads/capture/brief/ask/meetings/undo） | ≈ 800 | 26 |
| Step 15–16（onboarding/system/shell + 收尾） | **≤ 250（facade）** | 79（累计） |
