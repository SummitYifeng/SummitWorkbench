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
- 本轮目标版本：`v0.4.5` build 19
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

本地 `scripts/pre-push-gate.sh`（完整档，含前端）与远端 CI 均全绿：

| 项 | 结果 |
|---|---|
| `ruff check .` | 通过（`All checks passed!`） |
| `ruff format --check` | 通过（400 files already formatted） |
| `mypy`（strict） | 通过（`Success: no issues found in 308 source files`） |
| `pytest` | **890 passed / 1 skipped**，覆盖率 **82.33%**（与基线一致，未下降） |
| 前端 `tsc --noEmit` + `test:frontend` | 通过（7 个脚本全绿：build identity / feature contract / project render / review render / today import / settings race / api error / browser contract） |
| 前端生产构建 + `verify-build.mjs` | 通过，`Build verified: v2026.09.12-ec27776-0bc00d2c` |
| 远端 CI | 全绿：[run 34664463181](https://github.com/SummitYifeng/SummitWorkbench/actions/runs/34664463181)（quality-gate + macOS arm64 contract + macOS x86_64 contract + workflow lint 四个 job 全 success） |
| 门禁**未放宽** | 覆盖率门槛、mypy strict、契约测试一律未改动；**未修改任何测试以使其通过** |

### 4.1 本轮唯一一次测试改动（按 §8.2 说明理由）

`tests/unit/test_workspace_migration.py` 断言迁移后的 `min_writer_version` 等于字面量 `"0.4.4"`。
版本 bump 到 0.4.5 后该断言失败。**这不是"改测试让门禁变绿"**：

- 被测语义：`workspace_migration.py:396` 有意把写门提升为**执行迁移的那个 App 版本**
  （`current["min_writer_version"] = version`，`version` 缺省取 `__version__`）。
- 该字面量在写下时是正确的，只是**被版本 bump 变成过期常量**——属于发版必踩的维护性失败。
- 改法：断言改为对 `__version__`（真源）取值，而不是改成新的字面量，从而不再每次发版都要手改。
- **变异检查**（§8.2 要求）：把 `workspace_migration.py` 的写入值改成 `"0.0.0-sentinel"`，
  断言**确实失败**；恢复后 `git diff` 为空（逐字节还原）。故该断言不是"怎么都通过"的假测试。

---

## 五、发布结果（完整链路）

- **tag**：`v0.4.5`（指向 `749eeef`；`pyproject.toml` 版本 = `0.4.5`，release.yml 的 tag ↔ version 校验通过）
- **release run**：<https://github.com/SummitYifeng/SummitWorkbench/actions/runs/34664646655>（success）
- **产物 release**：<https://github.com/yifeng93/SummitWorkbench-Updates/releases/tag/v0.4.5>
  —— **`latest` 已正确指向 v0.4.5**（`prerelease=false`、`draft=false`）。此前 latest 停在 `v0.4.2`，
  历史 rc 均为 prerelease，**未污染 stable 通道**，符合 §7.3 要求。
- **DMG SHA256**：`79a64f36871cd0d8a2ac187d7028d21c653970d10e77702b049172f126852d80`
  （本地下载后 `shasum -a 256` 实测，与 `update-feed.json`、`SHA256SUMS`、`release-metadata.json`
  四处一致；大小 49413832 字节）
- **update-feed.json 的 `latest` 指向**：`artifacts[0].version = 0.4.5`、`build = 19`、
  `architecture = arm64`、`download_url` 指向 v0.4.5 的 DMG；`workspace_schema` 为
  `schema_version 2 / min_reader 0.4.5 / min_writer 0.4.5`；带 Ed25519 `signature` 与 `public_key`，
  与 App 内 `build-manifest.json` 的 `update_public_key` 一致。
- **本机安装与启动证据**：从 DMG 安装到 `/Applications/SummitWorkbench.app`，实测
  - `CFBundleShortVersionString = 0.4.5`、`CFBundleVersion = 19`；
  - 服务进程存活并监听动态端口，`/api/version` 返回
    `server_version 0.4.5 / build 19 / git_revision 749eeef / frontend_build v2026.09.12-749eeef-0bc00d2c`；
  - 六页签（today / review / ask / projects / guide / settings）全部存在于**已安装 App 实际服务出的**
    bundle 中；重写后的指南正文（「我想记一件事」「我想撤销一次改动」等）也在其中；
  - `/static/` 下 JS/CSS 均 HTTP 200；
  - **无 crash loop**：本次启动只有 1 条生命周期事件（`service_spawned`），当前运行段
    **0 条 error/warning**（日志里历史上那些 error 行属于此前会话，不是本次）。

### 5.1 发布过程中修正的一处配置（非代码问题）

首次 tag run **失败**在 `Prepare protected update configuration`：该步骤要求
`vars.UPDATE_DOWNLOAD_URL` 与
`https://github.com/<更新仓>/releases/download/<本次 tag>/<本次 DMG 名>` **逐字相等**，
而 `release` environment 里的该变量仍停留在上一次正式版 `v0.4.2` 的值
（`.../download/v0.4.2/SummitWorkbench-0.4.2-arm64-INTERNAL-DEV.dmg`）。

这**不是"为让检查变绿而放宽门槛"**，而是发布流程要求的版本化配置刷新：该变量的语义就是
"当前 stable 版 DMG 的精确下载地址"，每次正式发版都必须随之更新（rc 通道由 tag 派生、不读它，
所以历史上最后一次成功的是 rc 时，它就一直没被更新）。把 `UPDATE_DOWNLOAD_URL` 更新为 v0.4.5 的
地址后 `gh run rerun --failed`，全链路通过。**未修改任何工作流、脚本或门禁。**

### 5.2 一处诚实的遗留瑕疵（不影响已发布产物）

`docs/product/WEB_USAGE_GUIDE.md` 顶部的适用版本标记在**已发布的 DMG 内**显示为
`v0.4.5 build 13`，正确值应为 `build 19`。

原因：我在发起发布前先写了这个标记，当时假设 build 号是 13（承接 `v0.4.4` build 12 顺延）；
但按仓库现有规则，**build 号由 CI 的 `github.run_number` 决定**
（`release.yml` 传 `BUILD_NUMBER: ${{ github.run_number }}`，本次 release run 号为 19）。
真正的 build 是 **19**。

处理：仓库内**所有文档已更正为 build 19**；但为修正这一行而重建前端会改变 `source_hash`
与产物身份，并使已发布的 DMG 与仓库静态产物不一致——那正是 §3 与产物清单都明确要避免的漂移。
两害相权，选择**保留已发布产物不动、把仓库文档改对**，并在此明确记录。
该差异纯属版本字符串显示，**不涉及任何行为**；下次任何发版重建会自然消除它。

**→ 需求方随后选择"发个补丁版修掉它"，已在 `v0.4.6` 完成，见下节。**

---

## 六、v0.4.6 补丁版（修掉 §5.2）

需求方裁决后追加的一轮。**产品行为同样未改动**：只改指南开头一句文案并重建前端。

- **tag**：`v0.4.6`（→ `8eeff60`）· **build 20**（`github.run_number` = 20）
- **release run**：<https://github.com/SummitYifeng/SummitWorkbench/actions/runs/34665831750>（success，**一次通过**）
- **产物**：<https://github.com/yifeng93/SummitWorkbench-Updates/releases/tag/v0.4.6>，
  `latest` 正确指向 v0.4.6
- **DMG SHA256**：`a47f1a068fc64617e025c440e8ffe29aad5f2e1cb41745426474cdb7ee737034`
  （49381183 字节；feed / SHA256SUMS / release-metadata 三处一致，本地实测一致）

### 修法：不是把 13 换成 20，而是让它不再可能漂移

§5.2 那行字的本質問題不是"数字写错了"，而是**指南正文是构建时打进产物的静态 Markdown**，
里面写任何版本号都只能描述"构建它的那次发布"，无法描述"读者正在运行的那个 App"。
只把 13 改成 20，下一个版本会立刻再过期一次。

所以新写法**不再出现任何具体版本号**，改为指路：

> 想看当前装的是哪个版本：看**窗口顶栏右上角的状态文字**，它会实时显示
> （形如「界面 v… · 服务 x.y.z · 已同步」）——那里读的是真实运行值，永远准。

这句话指的是 `legacy-main.ts:372` 渲染的实时状态（客户端串用自己的 `CLIENT_BUILD`、
服务端串用 `/api/version` 的 `server_version`），**构造上就不可能漂移**。

### 验证（逐项实测，不只看 workflow 绿）

| 项 | 证据 |
|---|---|
| 产物内源码确已修好 | DMG 内 `web/static/assets/index-B2HwK92i.js` 里 `适用版本` / `build 13` / `build 19` **全部消失**，新文案 `窗口顶栏右上角的状态文字` 存在 |
| 装机 | `/Applications/SummitWorkbench.app` → `CFBundleShortVersionString 0.4.6`、`CFBundleVersion 20` |
| 实际服务出的是修好的 bundle | App 服务的 `index.html` 引用 `index-B2HwK92i.js`；拉下来核对：新文案存在、旧字符串不存在、六页签齐全 |
| API | `/api/version` → `server_version 0.4.6 / build 20 / git_revision 8eeff60 / frontend_build v2026.09.12-8eeff60-2bc31a83` |
| 资源 | `/static/` JS/CSS 均 HTTP 200 |
| 无 crash loop | 本次启动 **0 条 error/warning**、0 条异常生命周期事件 |
| 升级通道 | App 轮询的 `releases/latest/download/update-feed.json` 可达（HTTP 200）且内容为 `version 0.4.6 / build 20`，即 App 不会提示"降级"到 .5 |
| 门禁 | 本地完整 gate 全绿：890 passed / 1 skipped、覆盖率 82.33%、ruff、mypy strict、`tsc`、前端契约测试；CI [run 34665703015](https://github.com/SummitYifeng/SummitWorkbench/actions/runs/34665703015) 四 job 全 success |

顺带修掉的另一处同类过期描述：`OPEN-VERIFICATION-ITEMS.md` §J 结尾原写"已安装的 build 9 App
仍带旧前端"——该状态早在 v0.4.5 就已消除，已更正。

---

## 七、需要需求方裁决的事项（**均已裁决，本节存档**）

1. **§2.1 `list_events`** → 需求方裁决：**保留，本轮不动作**（零行为风险，且它仍是契约测试的覆盖对象）。
2. **§2.2 两个归档 HTML** → 需求方裁决：**按报告判断保留**。理由已在上文列明：
   `ARCHITECTURE.html` 被 `README.md:38` 链接、并被 PRD/PROJECTDESC 点名；
   `brief-v2-preview.html` 是活跃脚本 `web/scripts/preview-brief.mjs:14` 的输出路径。
   若将来仍要删，需先改这三处文档链接与该脚本的输出路径。
3. **§2.3 四个空的 `web/src/features/` 子目录** → 需求方裁决：**保留**。
   ADR 0036 明确"目录保留"作为 feature 入口边界，且它们正是
   [`LEGACY-MAIN-SPLIT-PLAN.md`](LEGACY-MAIN-SPLIT-PLAN.md) 的迁移落点
   （`features/sync/`、`features/threads/`）。

### 附：需求方同时裁决的其它三项

- **§5.2 指南版本显示** → **发补丁版修掉**，已完成于 `v0.4.6`（见 §六）。
- **两份拆分方案** → **先不动，作为后续独立任务**。方案已落盘，随时可开工；
  两个方案的第一步都是"让源码级契约断言变得可搬迁"（步骤 0），建议开工时从它开始。
- **A6 / F1** → **本轮不动**。A6 需第二台机器现场复跑；F1 是超出 `INTERNAL-DEV` 范围的非缺陷。
