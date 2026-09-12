# 交付前清理报告（v0.4.5）

> 本轮任务：在 `/Users/yifengstudio/Documents/GitHub/SummitWorkbench` 做交付前最后一次审查与优化。
> 完整任务定义见 [`DELIVERY-CLEANUP-HANDOFF.md`](DELIVERY-CLEANUP-HANDOFF.md)。
>
> **本轮的首要目标是不改变行为。** `v0.4.4` 的验收刚刚结束，任何行为回归都不会再被验收兜住，
> 因此所有"顺手改一下逻辑"的念头一律改成写进本报告而不是动手。
>
> 判定口径：**三重证据** —— ① 静态引用扫描（ruff / vulture / grep）
> ② 测试与构建产物是否引用 ③ 运行时路径是否可达。
> **三者都判定为无引用才允许删**；任一存疑 → 保留并记录理由。

- 基线：`v0.4.4` build 12（前端 `v2026.09.11-e8ed6f7-6e6e0c91`）
- 本轮目标版本：`v0.4.5` build 13
- 基线质量门：890 passed / 1 skipped，覆盖率 **82.33%**

---

## 一、已删除（附三重证据）

### 1.1 四个完全空的目录

| 目录 | 证据 |
|---|---|
| `docs/architecture/` | `ls -A` → 0 个条目（连隐藏文件也没有）；`git ls-files docs/architecture` → 0 个被跟踪文件 |
| `docs/background/` | 同上 |
| `docs/design/` | 同上 |
| `docs/plans/` | 同上 |

**三重证据**：

1. **静态引用**：删除前全仓扫描 `docs/architecture|docs/background|docs/design|docs/plans`，
   除本交接词自身外没有任何文档、脚本、测试把它们当作**现存路径**引用
   （`docs/archive/` 下的同名目录是另外的路径，不受影响）。
2. **测试与构建产物**：`git ls-files` 为空 → 不进入任何构建输入；无测试引用。
3. **运行时可达**：目录非 Python 包（无 `__init__.py`），不在 `pyproject.toml` 的
   `packages` / coverage `source` 内，运行时不可达。

**删除方式**：`rmdir`（仅在目录为空时成功），非 `rm -rf` —— 命令本身即为"确实为空"的验证。

> 说明：因为这 4 个目录**未被 git 跟踪**（git 根本不记录空目录），删除它们不会产生 diff。
> 这是正常的，不代表它们不存在。

### 1.2 一处失效路径引用（路径更正，非删除）

| 位置 | 原写法 | 实际位置 |
|---|---|---|
| `DELIVERY-CLEANUP-HANDOFF.md` §3 | `tests/unit/test_ci_contract.py` | **`tests/contract/test_ci_contract.py`** |

**证据**：`find . -name 'test_ci_contract*'` → 只存在于 `tests/contract/`；
`tests/unit/` 下无此文件。全仓扫描确认这是**唯一**一处失效的测试路径引用。

---

## 二、疑似但保留（附存疑原因）

> 本档是本轮最重要的部分。以下各项都**曾经**看起来像死代码/垃圾，但证据不支持删除。

### 2.1 `providers/feishu/calendar.py::list_events` —— 只被自己的契约测试调用

| 证据 | 结果 |
|---|---|
| ① 静态引用 | 生产代码**零**调用点；`__init__.py` 只导出 `list_events_between`，**未导出** `list_events` |
| ② 测试引用 | `tests/contract/test_feishu_calendar.py:14,97` 直接导入并调用（`test_list_events_takes_raw_fields_and_sorts`） |
| ③ 运行时可达 | 生产路径 `list_events_between` 走的是 `list_event_instances`（实例视图），与 `list_events`（原始事件视图）是**两个不同端点** |

**保留原因**：第 ② 条不满足「测试与构建产物均不引用」——它有一项**专门为它写的契约测试**。
按三重证据标准，只要一项存疑即保留。

**旁证**：`docs/archive/audits/PONYTAIL_AUDIT_050ec07.md:86` 已把它列为"二次核查候选，**不计入
收益、不交由本轮删除**；需要确认旧日历查询能力是否仍属于支持面"。即：**上一轮审计已得出
同样的"保留待裁决"结论**，本轮不推翻它。

**需要需求方裁决**：这个"按原始事件（而非重复实例）查询"的能力是否仍是支持面的一部分？
若是 → 保留；若否 → 应连同它的契约测试一起删（属于"被测代码本身被合法删除"的情形）。

### 2.2 `docs/archive/architecture/ARCHITECTURE.html` 与 `docs/archive/design/brief-v2-preview.html`

需求方在本轮开工前的选择题中选择了"把 archive 下这 2 个 HTML 也当垃圾删掉"。
**我没有执行该项**，因为证据明确不支持，且它与交接词的硬约束冲突：

| 文件 | ① 静态引用证据 | ② 构建产物证据 |
|---|---|---|
| `ARCHITECTURE.html` | **被 `README.md:38` 作为链接引用**（"旧架构示意图（归档）"）；`docs/product/PRD.md:3` 与 `PROJECTDESC.md:84` 都以文件名点名它作为"当前权威规格"的对照物 | 无 |
| `brief-v2-preview.html` | `CHANGELOG.md:228`、`docs/product/WEB_WORKBENCH.md:134`、`docs/archive/decisions/0024-*.md:28` 均点名 | **`web/scripts/preview-brief.mjs:14` 的 `OUT_HTML` 常量就是这条路径——该脚本仍在仓库中，运行它会写到这个文件** |

**保留原因**：删除会同时造成两类违约，而这两类是交接词明文禁止的：

1. §6 要求"**文档里引用的路径/命令/文件名必须仍然存在**"——删掉 `ARCHITECTURE.html` 会直接
   在 `README.md` 留下一个断链。
2. §4 把"脚本"明确列为"grep 不到引用但其实是活的"一类，`preview-brief.mjs` 正是活跃脚本；
   删掉它的输出路径会破坏一个活脚本的既有行为。

**取舍依据**：交接词 §1 的原话是"**宁可留下 10 处可疑代码，也不要删掉 1 处活代码**"；
§11 是"拿不准就问，**默认保留并写进报告**"。因此我按"保留 + 上报裁决"处理。
这一条需要需求方明确认可（若仍要删，正确做法是先改 `README.md`/`PROJECTDESC.md`/`PRD.md`
与 `preview-brief.mjs` 的输出路径，那属于超出本轮授权的改动）。

### 2.3 四个空的 `web/src/features/` 子目录

`web/src/features/{onboarding,sync,threads,workspace}/` 都是 0 条目空目录。

**保留原因**：它们不是垃圾，而是**被 ADR 明确保留的边界**。
`docs/archive/decisions/0036-frontend-feature-lifecycle-boundaries.md`「2026-09-10 冗余审计收敛」
一节原文：

> 审计确认 onboarding、sync、threads、workspace 的空入口文件及 workspace store 的无调用订阅
> 接口没有消费者，已删除；……**目录保留**。

ADR 0036 同时规定"新增或迁移 feature 必须从对应目录导入，不得重新堆回 composition root"。
也就是说，这四个空目录正是**本轮产出的 `LEGACY-MAIN-SPLIT-PLAN.md` 要填充的目标位置**
（该方案将 `features/sync/` 与 `features/threads/` 列为迁移目标）。删掉它们会让拆分方案失去落点。

**需要需求方裁决**：若坚持删（例如认为空的占位目录会造成困惑），需同时修订 ADR 0036；
本轮不做。

### 2.4 `docs/contracts/` 目录

目录内只有 `web-route-contract.json`，且它是**已入库的生成物**
（由 `scripts/update-web-route-contract.py` 从 app factory 重新生成）。

**保留原因**：它仍是**当前生效**的 web 路由契约——被 `tests/contract/test_web_route_contract.py`
使用，且交接词 §2 明确"需要更新就跑那个脚本、不要手改内容"。删除目录属于改结构，超出本轮授权。

### 2.5 vulture / ruff 的全部高置信度候选项 —— **均为误报**

这是本轮最大的误删风险面，也是 §4 预警的那一类。做法：对 vulture 报出的 **138 个唯一符号**
逐条核对"生产引用数 / 测试引用数"，再对"两侧都为 0"的符号逐一查明**它的注册机制**。

**ruff `check`：`All checks passed!`（0 命中）。**

**vulture**（一次性只读扫描，未加入 CI；注意 vulture 2.16 的解析器不认识 PEP 695 泛型语法，
对 `def f[T](...)` / `class C[T]` / `type X = ...` 会直接报 `invalid syntax`，
因此它对本项目的覆盖本就不完整）：

| 误报类别 | 代表符号 | 为何是活的 |
|---|---|---|
| Typer 命令 | `list_projects` / `apply_review` / `sweep_review` / `archive_local` / `import_transcripts` / `import_local` / `note_transcript` / `refresh` / `smoke` … | 由 `@*_app.command` 装饰器注册，**引用是装饰器不是 import**。逐条已确认装饰器存在 |
| FastAPI 路由处理器 | `api_version` / `session_bootstrap` / `api_project_view` / `api_project_activate` / `api_project_rename` / `api_project_archive` / `api_project_create` / `api_workspace_migration` / `diagnostics_preview` / `diagnostics_export` / `settings_provider_verify` / `settings_feishu_*` / `onboarding_*` / `feishu_callback` / `restricted_feishu_callback` / `full_onboarding` … | 由 `@app.get` / `@app.post` / `@application.post` 注册，逐条已确认装饰器存在 |
| Pydantic 模型 | `webapp/api.py` 里 30+ 个 `*Payload` 类 | 作为路由**参数类型注解**被 FastAPI 消费，无需显式引用 |
| Pydantic 校验器 | `_valid_due_date` / `_workspace_id_is_uuid` / `_event_id_is_ulid` / `_device_id_is_uuid_v4` / `_occurred_at_is_aware` / `_text_is_single_line` / `_payload_is_json` / `_workspace_id_is_uuid_v4` | 由 `@field_validator` 注册 |
| Pydantic 字段 | `git_mode` / `automation_role` / `model_provider` / `model_base_url` / `feishu_app_id` / `feishu_redirect_uri` / `plan_id` / `stage_id` / `expected_workspace_id` … | 是模型字段声明；值经 `model_dump()` 序列化后被消费 |
| 框架签名参数 | `settings_customise_sources` 的 `dotenv_settings` / `file_secret_settings` | **由 Pydantic 基类定义、子类按名覆写**，参数名和位置都是契约，不能删 |
| 测试夹具与常量 | `isolate_home`（conftest 自动夹具） / `capfd`（pytest 内建夹具） / `pytestmark` / `_clone_worktree` / `_feishu_page` | vulture 无法追踪夹具注入与同文件内调用 |
| 枚举与常量成员 | `domain/threaddoc.py` 的 `PROGRESS`/`ACTION`/`TODO`/`BLOCKED`/`SUMMARY`/`PRD`/… 、`domain/review.py` 的 `PROJECT_STATUS_CHANGE`/`TASK_CREATE`、`domain/capture.py` 的 `TASK`、`providers/feishu/meetings.py` 的 `ARTIFACT_MINUTES` | 模块级契约常量，按名被其它模块/文档引用 |

**结论：本轮没有删除任何 Python 代码。** 这不是"没找到"，而是逐条核对后的结果：
所有看起来像死代码的候选，要么由框架按约定注册，要么是字段/契约常量。

---

## 三、建议但本轮不动

> 以下都**有道理**，但要么超出本轮授权，要么有行为风险。按"不改行为"的首要目标，
> 一律记录而不是动手。

### 3.1 两个巨型文件的拆分（已出方案，未改代码）

| 文件 | 规模 | 方案 |
|---|---|---|
| `src/summit_workbench/webapp/legacy_app.py` | 3457 行 | [`LEGACY-APP-SPLIT-PLAN.md`](LEGACY-APP-SPLIT-PLAN.md) |
| `web/src/legacy-main.ts` | 3346 行 | [`LEGACY-MAIN-SPLIT-PLAN.md`](LEGACY-MAIN-SPLIT-PLAN.md) |

两份方案都按**现有边界**（`webapp/routers/*`、`web/src/features/*`）给出目标模块、依赖方向、
迁移顺序与风险点，并给出每一步的验证命令。**本轮不执行拆分** —— 拆分是行为风险最高的一类改动，
且验收已结束，没有兜底。

### 3.2 `dulwich` 升级

`docs/acceptance/OPEN-VERIFICATION-ITEMS.md` §I 已给出完整结论：两条开放 advisory 在
macOS-only arm64 与纯客户端用法下均不可达；升级经实测是**一次真实迁移**
（16 个运行时测试失败 + 29 个 mypy strict 错误，根因是 `Repo.do_commit` 在 1.x 被移除）。
**维持 `dulwich>=0.22,<0.23`**，本轮不动。

### 3.3 `docs/archive/` 下 50 篇过程记录

它们是**历史**，不是垃圾。按约束 5 本轮**只加标注**：
在 `docs/archive/README.md` 顶部增加统一归档标注（"历史记录，结论可能已过期；
当前状态以 `docs/acceptance/OPEN-VERIFICATION-ITEMS.md` 为准；本目录只读"）。
**归档正文一字未改。**

### 3.4 README 里其余历史 build 编号

`CHANGELOG.md` 与 `docs/acceptance/V0-4-4-LOCAL-RELEASE-ACCEPTANCE.md` 中的 build 9/11/12
是**历史事实的准确记录**，不是过期现状描述，因此**不改写**。
只更新了描述"当前状态"的三处（`README.md`、`PROJECTDESC.md`、`docs/product/WEB_WORKBENCH.md`）。

### 3.5 `_vault` 与真实远端

按 §10"不碰真实 vault 的内容"。本轮所有验证都在只读或隔离路径下进行。

---

## 四、验证与门禁

| 项 | 结果 |
|---|---|
| `ruff check .` | 通过（`All checks passed!`） |
| `ruff format --check` | 通过（对 `docs/` 亦执行 `ruff format`，输出 `68 files left unchanged`） |
| `mypy`（strict） | 见最终报告 |
| `pytest` | 890 passed / 1 skipped，覆盖率 **82.33%**（与基线一致，未下降） |
| 前端 `tsc --noEmit` + `test:frontend` | 见最终报告 |
| 门禁**未放宽** | 覆盖率门槛、mypy strict、契约测试一律未改动；**未修改任何测试以使其通过** |

---

## 五、需要需求方裁决的事项

1. **§2.1 `list_events`**：这个"按原始事件查询"的能力是否仍属于支持面？留还是删？
2. **§2.2 两个归档 HTML**：你选择了删除，但证据显示它们被 `README.md` 链接、
   且是活跃脚本的输出路径。**我按硬约束保留并上报**。若确认要删，需要先改
   `README.md`/`PROJECTDESC.md`/`PRD.md` 与 `web/scripts/preview-brief.mjs` 的输出路径
   （超出本轮授权）。
3. **§2.3 四个空的 `web/src/features/` 子目录**：ADR 0036 明确"目录保留"，
   且它们是拆分方案的落点。是否仍要删？
