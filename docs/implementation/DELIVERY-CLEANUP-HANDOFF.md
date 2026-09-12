# 交付前最终审查与优化 —— 交接提示词

> 把本文件「复制区」整段发给一个新开的 agent 对话。它是自包含的：新 agent 看不到之前的对话。
> 需求方（账号所有者）已就下列六条做过选择题对齐，**不要再自行放宽**。

---

## 复制区（从这里开始）

你在 `/Users/yifengstudio/Documents/GitHub/SummitWorkbench` 做交付前的最后一次审查与优化：
清死代码、清文档、重写「指南」页、产出拆分方案、跑 CI，最后走完整发布链路。

### 0. 项目背景

- 本地个人工作系统：Python 3.12 + FastAPI 后端、Vite + 原生 TS 的 SPA、macOS Swift/AppKit +
  WKWebView 原生 App、`wb` Typer CLI；数据层是 Obsidian vault（Markdown + Git）。
- 当前基线：`v0.4.4` build 12，前端 `v2026.09.11-e8ed6f7e` 系列；**890 测试通过**、
  覆盖率 **82.33%**、远端 CI 全绿。仓库 `git@github.com:SummitYifeng/SummitWorkbench.git`。
- **验收已经全部做完**：`docs/acceptance/OPEN-VERIFICATION-ITEMS.md` 只剩 A6（需第二台机器现场
  复跑）与 F1（明确超出 `INTERNAL-DEV` 范围的非缺陷）。
- **这条最要紧**：验收阶段刚刚结束，**任何行为回归都不会再被验收兜住**。所以本轮的第一目标是
  **不改变行为**。凡是"顺手改一下逻辑"的念头，一律改成写进报告而不是动手。

### 1. 六条硬约束（已与需求方对齐，不要放宽）

1. **死代码判定用「三重证据」**：① 静态引用扫描（ruff/vulture/grep）② 测试与构建产物是否引用
   ③ 运行时路径是否可达。**三者都判定为无引用才允许删**；任一存疑 → **保留**并在报告里列出
   理由与证据。宁可留下 10 处可疑代码，也不要删掉 1 处活代码。
2. **目录结构只删空目录、不搬文件**。不跨包移动、不重命名模块、不改 import 路径。
3. **两个巨型文件本轮只出拆分方案，不动代码**：`src/summit_workbench/webapp/legacy_app.py`
   （3457 行）与 `web/src/legacy-main.ts`（3346 行）。
4. **「指南」页本轮直接重写为「怎么做」**（见 §5）。
5. **文档：删空目录 + 更新现状类文档 + `docs/archive/` 只加标注不改内容**。
6. **发布走完整链路**（见 §7）。

### 2. 已完成的扫描（不必重做，直接用）

| 区域 | 规模 |
|---|---|
| Python `src/` | 183 文件 / 30226 行 |
| 测试 `tests/` | 125 文件 / 19215 行 |
| Web TS `web/src/` | 21 文件 / 5007 行 |
| Swift `native/` | 15 文件 |
| 文档 `docs/` | 66 篇 / 11255 行（其中 **50 篇在 `docs/archive/`**） |

**已发现的明确问题**：

- **4 个完全空的目录**：`docs/architecture/`、`docs/background/`、`docs/design/`、`docs/plans/`
  （删除前用 `ls -A` 确认连隐藏文件也没有）。
- `docs/contracts/` 只剩一个 `web-route-contract.json`，它是**已入库的生成物**
  （由 `scripts/update-web-route-contract.py` 从 app factory 重新生成，`git ls-files` 可确认它
  被跟踪）。**不要手改它的内容**——需要更新就跑那个脚本。目录本身只有一个文件，是否保留由你
  按"它是否仍是当前契约"判断。
- 两个巨型文件（见约束 3）。
- `docs/archive/` 里 50 篇中有 49 篇是本轮（2026-09）产生的过程记录——它们是**历史**，
  不是垃圾；按约束 5 只加标注。

### 3. 动手前必读的仓库约定

- **质量门**：`scripts/pre-push-gate.sh`（已装 pre-push hook）＝ actionlint + action ref 预检 +
  ruff check/format + mypy strict + `pytest --cov-fail-under=80` + `tsc --noEmit` +
  `npm --prefix web run test:frontend` + `git diff --check`。**它必须保持全绿**，且**覆盖率不得下降**。
- **单一真源**：`docs/acceptance/OPEN-VERIFICATION-ITEMS.md` 是"还没验证什么"的唯一权威。
  本轮**不要**往里加计划或需求；确实关闭了某条才移动它。
- **提交纪律**：只在你被明确要求时提交/推送（本次任务已授权提交与推送）。源码改动与**静态产物**
  改动**分开提交**（仓库既有约定）。
- **契约测试**：仓库里有一类**源码级契约测试**，会断言源码/文档里的具体字符串或装配关系，例如
  `tests/unit/test_ci_contract.py`、`tests/unit/test_native_panel_contract.py`、
  `web/scripts/test-browser-contract.mjs`。**删除代码或改写文档很可能打断它们**——这是正常的，
  正确做法是**同步更新断言并说明理由**，不是绕过或删测试。

### 4. 死代码排查：这些地方「grep 不到引用但其实是活的」

这是本轮最大的误删风险。以下每一类都**不能**用"grep 不到引用"判定为死代码：

- **PyInstaller 入口**：`src/summit_workbench/webapp/server_entry.py`、`src/summit_workbench/worker_entry.py`
  在测试里覆盖率是 **0%**，但它们是打包入口，**绝对不能用覆盖率或引用数判死**。
- **CLI 子命令**：`src/summit_workbench/cli/*.py` 通过 Typer 注册，引用是装饰器，不是 import。
- **Web 路由**：`src/summit_workbench/webapp/routers/*.py` 由 app factory 挂载。
- **提示词文件**：`prompts/` 下 **7 个 md 在运行时按名字读取**，文件名即契约，逐个都在用：
  `artifact-index.md`、`brief-ranker.md`、`capture-classifier.md`、`log-digest.md`、
  `meeting-merger.md`、`meeting-processor.md`、`qa-answer.md`。
  **不要**因为"grep 不到 import"就判定它们无引用。
- **Swift**：`scripts/build-macos-app.sh` 用**通配** `native/SummitWorkbench/*.swift` 编译——该目录下
  **每个** `.swift` 都会被编译进产物。而 `scripts/test-native-*.sh` 用的是**显式文件清单**，
  **没出现在测试清单里 ≠ 死代码**。
- **Web 入口链**：`web/src/` 的入口由 Vite/`web/scripts/build.mjs` 决定；
  `web/src/guide.md` 是**生成物、不入库**（`npm run sync-guide` 由 `docs/product/WEB_USAGE_GUIDE.md`
  生成）。不要手改生成物，也不要因为"文件不在 git 里"就以为可以删源文件。
- **脚本与工作流**：`scripts/*.sh`、`.github/workflows/*` 被 CI、git hook、打包脚本引用。

**Python 侧建议做法**：先跑 `ruff check`（已含未使用 import 规则）与 `vulture`（可为一次性只读
扫描，**不要**把它加进 CI）；再把候选项逐个按三重证据核对。**注意 `ruff format` 会格式化
Markdown 代码块里的 Python**，改写文档时如果插入了 Python 示例，记得跑一次
`ruff format docs/`，否则门禁会挂。

### 5. 「指南」页重写（本轮唯一的用户可见改动）

现状：需求方原话——"app 里的指南非常技术层面，不实用"。

**事实源是 `docs/product/WEB_USAGE_GUIDE.md`**（258 行 / 约 23.7 KB）。构建时由
`web/scripts/sync-guide.mjs` 拷贝成 `web/src/guide.md` 供 SPA「指南」页渲染（离线可用）。
**改这个 md，不要改生成物。**

要求：

- **目标读者**：非技术的账号所有者本人。判据是——**他能在不读任何代码、不打开终端的前提下，
  照着页面完成下面每个场景**。
- **按「我想做什么」组织**，例如：记一件事 / 处理今天的待办 / 导入一场会议 / 看项目进展 /
  多设备同步 / 出问题了怎么办。**不要**按架构分层（后端/前端/vault/路由…）组织。
- **默认只显示步骤**；原理、字段语义、边界条件等**技术细节收进折叠区**（现有页面已有
  「高级」折叠的先例，沿用同样的呈现习惯）。
- **保留渲染测试**：`web/scripts/test-browser-contract.mjs` 里针对指南的断言是**渲染机制**层面的
  （本地搜索 `guide-search`、目录 `guide-index-links`、按 H2/H3 分组、`data-guide-section` 的
  归属、目录跟随筛选），**不是**指南正文内容。所以**重写正文不会打断它们**——只要你没有改渲染器，
  这些断言应当原样继续绿。**若你把它们改绿了，要能解释原因；若你改了渲染器，请同步更新断言。**
- 改完必须**重新构建**并确认「指南」页签实际渲染正常（这是用户可见改动，不能只看源码）。

### 6. 文档清理

- 删除 §2 列出的 4 个空目录（确认后）。
- **更新现状类文档**：至少核对 `README.md`、`docs/product/PRD.md`、
  `docs/product/WEB_USAGE_GUIDE.md`、`docs/implementation/` 下的交接/实施记录，以及
  `docs/acceptance/` 里的基线信息——**凡是写着"待验证 / 未验证 / 计划做"而实际上已经做完或已被
  证伪的表述，都要按现状更正**。判据以 `OPEN-VERIFICATION-ITEMS.md` 为准。
- `docs/archive/`：**只加标注不改内容**。建议在 `docs/archive/` 下加一个索引文件
  （或在每篇开头加一行），标明"历史记录，结论可能已过期；当前状态见
  `docs/acceptance/OPEN-VERIFICATION-ITEMS.md`"。
- 文档里引用的路径/命令/文件名**必须仍然存在**。删任何一个文件前，先全仓搜索它是否被文档、
  测试、脚本引用。

### 7. 发布（完整链路）

先读既有实现，**沿用它们的约定**：`scripts/build-macos-app.sh`、`scripts/release-macos.sh`、
`scripts/verify-macos-release.sh`、`scripts/generate-update-feed.py`、
`scripts/install-macos-app.sh`、`.github/workflows/release.yml`、`.github/workflows/ci.yml`。

要求：

1. **版本/构建号**：按仓库现有规则 bump（找到唯一事实源，不要在多个地方各改一半）。
2. **CI 先全绿**再发布；本地先跑 `scripts/pre-push-gate.sh`（完整档，含前端）。
3. **打 tag 触发 `release.yml`**，产出**签名 DMG + `update-feed.json` + SBOM + SHA256SUMS**。
   历史上 `v0.4.4-rc.1` 是作为 **prerelease** 发布的，`latest` 仍指向旧版——注意 rc **不得**污染
   stable 通道；本次是正式版，`latest` 应当正确指向它。
4. **发布后逐项验证**（不要只看 workflow 绿）：DMG 的 SHA256 与产物一致；`update-feed.json` 里
   `latest` 指向本次版本且字段完整；下载 DMG → 校验 → 安装 → **启动 App 实际可用**
   （六页签可达、版本号正确、无 crash loop）。
5. 源码提交与静态产物提交**分开**。
6. 事后清理：不要留下临时 tag、临时分支、测试产物或占用的端口。

### 8. 这些坑本项目都真实踩过，请直接采信

1. **`grep` 不到 ≠ 死代码**（见 §4；本项目曾因类似误判差点删掉打包入口）。
2. **不要为了让测试通过而修改或删除测试。** 只有当被测代码本身被合法删除时，才连同它的测试
   一起删，并在提交信息里说明。新增的测试**必须做变异检查**——把修复/新增的那一行去掉，确认
   测试真的会失败；否则那是个"怎么都通过"的假测试。
3. **Web 的写操作会自动 commit 并 push。** `src/summit_workbench/webapp/legacy_app.py` 的
   `_run_web_mutation` 是**所有** web 写操作的公共入口，它**总是**传 `push_after_commit`。
   因此**任何会产生真实写回的验证都不要对着带远端的真实 vault 做**——那会把测试数据推到真实远端，
   而远端历史**无法用本地 `reset` 收回**（产品设计绝不 force-push）。正确形态是：
   **真实 `HOME` + 隔离 vault + 无远端**。
4. **`HOME` 不是一道干净的隔离墙。** 用临时 `HOME` 会同时切断：runtime 记录路径
   （`NSHomeDirectory()` 不认 `$HOME`，服务端 `Path.home()` 认）与 **Keychain 访问**
   （`security` CLI 按 `$HOME` 解析钥匙串，临时 HOME 下没有 `login.keychain-db`，凭据一律读不到）。
5. **管道会吞掉退出码。** `scripts/pre-push-gate.sh | tail` 的退出码是 `tail` 的——本项目因此
   把一次失败误读成通过。用 `set -o pipefail` 或重定向到文件后再 `echo $?`。
6. **别把临时文件写进仓库。** 曾有一次用 `$(cat /tmp/xxx 2>&1)` 取临时路径，文件不存在时
   `cat` 的**报错文本**变成了路径值，相对路径解析后把整棵夹具树种进了仓库目录，导致
   `ruff check .` 扫到垃圾文件而失败。跨命令传路径请显式断言非空。
7. **原生代码改动需重新打包才生效**；只改 `.swift` 而不重建，产物里没有变化。

### 9. 交付物

1. **提交历史**：按主题分多笔（例如 `chore(cleanup): 删除无引用模块`、
   `docs: 更正现状描述并标注归档`、`feat(guide): 重写为任务导向使用指南`、
   `docs: 补充两个单体文件的拆分方案`）。每笔都要能独立解释"为什么删/为什么改"。
2. **清理报告**（放在 `docs/implementation/` 下，或在最终回复里给）：分三档——
   **已删除**（附三重证据）/ **疑似但保留**（附存疑原因）/ **建议但本轮不动**。
3. **拆分方案**：`legacy_app.py` 与 `legacy-main.ts` 的拆分蓝图——按现有边界
   （`webapp/routers/*`、`web/src/features/*`）给出目标模块、依赖方向、迁移顺序与风险点。
   **只写方案，不改代码。**
4. **指南**：重写后的 `docs/product/WEB_USAGE_GUIDE.md` + 更新后的渲染测试 + 构建后实际页面证据。
5. **CI 全绿**，**覆盖率不低于 82.33%**。
6. **发布完成**：tag、release run 链接、DMG SHA256、`update-feed.json` 的 `latest` 指向、
   本机安装后启动可用的证据。

### 10. 明确不做

- 不改任何产品行为逻辑（含路由、写回边界、锁语义、outbox、schema/迁移）。
- 不做依赖大版本升级、不升 `dulwich`（`docs/acceptance/OPEN-VERIFICATION-ITEMS.md` §I 已有结论）。
- 不搬目录、不改包结构、不重命名模块。
- 不拆分那两个巨型文件（只出方案）。
- 不动 A6 / F1 两项开放项。
- 不碰真实 vault 的内容（只读了解结构可以）。
- 不为了让某条检查变绿而降低门槛（覆盖率、严格 mypy、契约测试都不许放宽）。

### 11. 拿不准就问，不要猜

遇到"这个能不能删 / 这个要不要改"的边界情况，**默认保留并写进报告**，然后在最终回复里
列出「需要需求方裁决的事项」。本次任务的授权范围只覆盖上面这些清理与发布动作。

## 复制区结束
