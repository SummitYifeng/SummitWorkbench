# P0/P0'/P1 加固交接（新对话窗口从这里继续）

> 由稳定性审计会话整理。目标：新对话能零成本接续，按本清单实现
> 「写路径并发加固（P0）→ 系统写回自动 commit + 撤销按钮（P0'）→ 停滞信号语义修复（P1）」。
> 这是**实施清单**，不是讨论稿：每一项都给出了文件、函数、改法与验收方式。

> **实施状态：✅ 已按 P0 → P0' → P1 串行完成并全部通过质量门（2026-09-04）。** P0 提交 b389b3c（ruff/mypy/pytest 499 全绿）→ P0' 提交 ba74066（512 全绿）→ P1 提交 f3e348a（514 全绿）；配套文档与装机随 v0.4.1 发布（ADR 0027、CHANGELOG [0.4.1]）。下方条目即为落地记录。

## 现状一句话

SummitWorkbench v0.4.0（M3 尚未开始）。审计结论：代码有全套**原子写 / 容错读 / 工作区锁**基建，
但 workspace_lock 全库只有 4 个调用点（feishu/session、sync、brief/publish），几乎所有
面板/工作流写路径（审批页 RMW、inbox append、当日简报、快照镜像、线程日志）都在锁外裸奔，
存在多写入者并发 → **静默丢失更新**；同时**全库无 undo/撤销**，git 自动提交只覆盖简报产物。

## 使用者画像（决定范围的三个事实，勿偏离）

1. **纯桌面 App 面板用户，不用 CLI**（CLI review/meeting 系列不在日常回路，只顺带收口，不阻塞）。
2. **平时不打开 Obsidian 手改 wb 写过的文件**（只在回溯项目时点开）——不需要做
   Obsidian 冲突检测 UI；文件层原子写保护即可。
3. 面板（uvicorn 线程池，默认并发）是唯一人写入口；外部进程只有 launchd 两个：
   weekly（周一 07:30）、brief（每日 08:00）。

## 权威资料（先读）

1. README.md —— 架构、命令、硬边界、质量门。
2. docs/plans/DEVELOPMENT_PLAN.md + docs/plans/HANDOFF_P3.md —— 仓库计划与交接文档风格。
3. docs/decisions/0016-workspace-lock.md、0017-jsonl-tolerant-read.md、0019-schema-versioning.md
   —— 本次改造直接复用的既有决策（锁、容错读、schema 版本）。
4. 实现必读：src/summit_workbench/config/locking.py（锁语义：flock + 线程内重入 + 超时 LockBusy）、
   src/summit_workbench/repositories/_atomic.py、repositories/_jsonl.py、
   webapp/app.py（全部写端点）、workflows/review_apply.py、
   repositories/{review_edit,writeback,thread_notes,daily_note,signal_snapshot,review_audit}.py、
   workflows/weekly/collect.py。

## 质量门（推送前全绿，逐项做完即跑）

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```

---

## P0 · 写路径并发加固（1–2 人天，Patch）

### 铁律（贯穿 P0/P0'）

- **锁根统一**：所有新加锁点用 workspace_lock(vault_dir.parent)（生产布局下
  vault_dir.parent == work_root，与 publish_brief/sync 同一把 .wb.lock；
  测试用 tmp_path 天然隔离）。
- **锁只包文件临界区，绝不横跨 LLM/网络调用**（模型调用在锁外完成，锁内只做
  parse→mutate→atomic_write）。锁默认超时沿用 _DEFAULT_TIMEOUT（60s）。
- **LockBusy 必须可见化**：web 端点已 catch Exception 返回 {"ok": false}（新增锁点沿用）；
  CLI 侧新增锁点时 catch LockBusy → typer 输出「工作区忙，稍后重试」并 exit(1)。
- 锁可重入（同线程嵌套安全），Repository 层加锁与 workflow 层将来再加锁不冲突。

### P0-1 给「单文件 RMW 写原语」逐处加锁（核心）

把「读文件 → 变换 → atomic_write_text 整文件重写」整体包进锁。清单：

| 文件/函数 | 现行为 | 改法 |
|---|---|---|
| repositories/review_edit.py::_rewrite（set_decision/set_decisions/update_fields 共用） | 无锁 RMW 审批页 | 整个 parse→replace→atomic_write 包 workspace_lock |
| repositories/review_page.py::refresh_review_page | 无锁 RMW 审批页（sweep/refresh/import 汇入） | 同上 |
| repositories/writeback.py::_append_under_heading（append_project_* / append_global_inbox / append_thread_inbox 共用） | 无锁 RMW inbox/项目档案（读→marker 检查→整文件原子重写） | 同上 |
| repositories/writeback.py::set_project_status | 无锁 RMW 项目「当前状态」区块 | 同上 |
| repositories/writeback.py::_ensure_heading / 各 _ensure_* | 裸 write_text 补区块/建文件 | 补区块改锁内 RMW；建新文件改 atomic_write_text(ensure_parents=True) |
| repositories/daily_note.py::write_brief | **裸 write_text** RMW 当日笔记（含用户锚点外内容） | 锁内 RMW + 改用 atomic_write_text |
| repositories/weekly_review.py::write_weekly | 裸 write_text 覆盖周复盘 | atomic_write_text + 锁 |
| repositories/meeting_archive.py（L123 write_text 落逐字稿） | 裸写 | atomic_write_text（文件新建，无需锁） |
| repositories/thread_notes.py::_write_note 及其调用链（append_work_log / save_thread_artifact） | 裸 atomic（无锁） | 见 P0-4（序号分配 + 落盘一起锁） |
| repositories/signal_snapshot.py::mark_task_completed / mark_task_edited / mark_meeting_edited | 无锁 RMW 当日快照 | read_snapshot→mutate→write_snapshot 整体包锁 |
| repositories/note_status.py::update_note_status | 无锁 RMW frontmatter（被 _touch_projects_updated 等高频调用） | 整体包锁（锁很轻，可接受） |
| workflows/review_apply.py 收尾页重写 | 无锁整页重写 | 见 P0-5 乐观合并（不能全程持锁——apply 含分钟级外部调用） |
| workflows/review_sweep.py::sweep_meeting_review（apply=True） | 多处串行 RMW（set_decisions + update_note_status + record_task） | 整段包锁（无外部调用）最简 |

### P0-2 原子写补丁（无锁、纯文件层）

daily_note.py::write_brief、weekly_review.py::write_weekly、meeting_archive.py L123
从裸 write_text 改 atomic_write_text（P0-1 表内已列，此处强调「不依赖锁也必须原子」——
断电/kill 不留下半截文件，尤其当日笔记含用户手写内容）。

### P0-3 幂等账本容错读（一致性补丁）

repositories/review_audit.py 的 completed_ids / completed_decisions 现在用裸
json.loads 逐行读——与 _jsonl.read_models 的容错通道不一致，一条半截行即让 apply
幂等判定整体崩溃。改法：新增显式行模型（如 ExecutionRecordRow，extra="ignore"），
读写改用 _jsonl.append_row / read_models（坏行隔离进 .quarantine，只告警不崩）。

### P0-4 线程日志/产物序号冲突（确定性静默覆盖）

repositories/thread_notes.py::_next_seq 用「同名前缀文件数 + 1」取文件名
（YYYY-MM-DD-<seq>.md / <project>-<seq>.md）：两个并发写入算出同一 seq → 同路径
原子覆盖，**一条日志静默消失**。改法（推荐 a）：
a) 序号分配 + _write_note 整体放进 workspace_lock（与 P0-1 同锁），并在写前
   检测目标已存在则重取序号；
b) 文件名追加时间戳/随机后缀保证唯一（改动命名会牵连任何按 -NNN 解析的读者，需先 grep 确认无）。

### P0-5 apply 收尾「乐观合并」（防审批页被整页重写吞掉并发操作）

workflows/review_apply.py::apply_meeting_review：apply 从**旧快照**解析后逐个做外部写回
（分钟级），最后 atomic_write_text(page, render_review_page(remaining)) 会把窗口期内
用户在页上的勾选/编辑**静默覆盖**。全程持全局锁会阻塞 capture/日志等一切写入（不可接受）。
改法：
1. apply 开始时记录 page_snapshot = page.read_text()；
2. 收尾写页前**重读最新页**；若与 page_snapshot 一致 → 维持现状；
3. 若已变化 → 解析最新页，**只移除本次 handled 且最新页中裁决未变的候选**；
   对「本次 handled 但最新页已被并发改动」的候选**留在页上不动**（审计账本已记
   applied/rejected → 下次 apply 会按 already-completed 幂等清理，不会重复执行）；
   失败候选的 error 标注同样只合并进最新页。
4. 新增测试覆盖：apply 执行期间并发 decide 同一/不同候选，最终页必须保留并发裁决。

### P0-6 跨进程互斥说明（不新增代码，确认语义即可）

launchd brief（08:00）与面板「生成简报」走同一 run_brief 写路径：两者都会经
daily_note.write_brief / signal_snapshot.write_snapshot 写**同一批文件**。P0-1 的
repository 级锁让两个进程在 .wb.lock 上自动互斥——**验证**：写测试/脚本同时起两个
进程各跑一次 write_brief+write_snapshot，断言最终文件完整、无交错（放 tests/integration/）。

### P0 新增测试（tests/unit/ 或 tests/integration/）

- T1：两个线程并发 set_decision（不同候选）→ 两个裁决都保留（此前必丢一个）。
- T2：apply_meeting_review（apply=True）进行中并发 set_decision → 收尾后并发裁决保留（P0-5）。
- T3：两个进程/线程并发 append_global_inbox（不同 candidate_id）→ 两条都在。
- T4：并发 append_work_log 同日两条 → 两个不同文件名，均完整（P0-4）。
- T5：write_brief 与 mark_task_completed 并发 → 快照与当日笔记都完整（P0-6 语义）。
- T6：review_audit 日志含一条半截行 → apply 幂等判定不崩、坏行进 quarantine（P0-3）。

---

## P0' · 系统写回自动 commit + 面板撤销按钮（2–3 人天）

### 设计（已与使用者对齐）

- **写入即留痕**：每次「系统侧写回」成功后自动对触碰文件做一次 git commit（消息带
  wb: 前缀），供撤销与历史查看；推送交给既有 wb sync/launchd（不新增强制 push）。
- **面板撤销按钮**：用户点击 → 展示「最近 N 次 wb 自动提交 + 每次的 before/after 差异」→
  一键还原（等价 git revert），还原后刷新页面。
- **边界**：只对 vault 内文件生效；**飞书侧副作用（已建任务/会议、已完成状态）不可撤销**，
  按钮旁文案必须明示；工作树对该文件有未提交人工改动时拒绝还原（避免覆盖用户手改）。

### P0'-1 新 helper：repositories/autocommit.py

- commit_paths(vault_dir, paths, message)：非 git 仓库 → 返回 not-git 状态不抛错；
  沿用 GitRepo 显式 add 指定路径（绝不 add -A）；空暂存 → 跳过；
  失败 → 返回可见状态（不阻断业务写回）。调用方放入 P0 同一把锁内（与 publish 一致）。
- list_wb_commits(vault_dir, limit=20)：git log --grep '^wb:' 取最近提交
  （sha、消息、时间、触碰文件 --stat 摘要）。
- revert_commit(vault_dir, sha)：先校验该文件工作树干净（is_dirty 仅对该路径）→
  git revert --no-edit <sha>（或 checkout <parent> -- <paths> + commit，二选一并在
  测试里锁死行为）；冲突/失败返回可见错误。

### P0'-2 埋点（业务写回成功后调 commit_paths）

触碰路径多数函数已返回 Path，收集即可：

- POST /api/capture → inbox.md
- POST /api/threads/logs → 新建日志文件 + 关联项目档案（updated 刷新）
- POST /api/threads/artifacts → 新建产物文件 + 关联档案
- POST /api/threads/state → 项目档案
- POST /api/review/apply（apply=True 实际写回）→ 写回目标文件 + 审批页 + 审计归档
- wb review sweep --apply（CLI 顺带）→ 笔记状态 + 审批页
- POST /api/meetings/import（拖拽导入）→ 逐字稿/笔记/审批页
- POST /api/projects/{create,activate,archive,rename} → 档案
- POST /api/tasks/complete|update、/api/meetings/update → 当日快照镜像
- launchd brief/weekly 已有 publish 提交，**不要重复埋**。

> 说明：面板是唯一人入口，故埋点集中在 webapp 端点层 + 两个 workflow（apply/sweep）。
> 不把 commit 塞进 repository 写函数（会让 tests 全变 git 环境，污染隔离）。

### P0'-3 Web API + 前端

- GET /api/undo/history → 最近 wb 提交列表（含 per-commit 文件与状态）。
- GET /api/undo/diff?sha= → 该提交的 before/after（git show 输出转可读）。
- POST /api/undo/revert {sha} → 执行还原，返回结果与提示（含「飞书侧不受影响」文案）。
- web/src/main.ts：设置/工具区入口「撤销系统改动」→ 列表 → 差异预览 → 确认还原。
- 失败全部可见化（{"ok": false, "message"}），绝不影响既有操作。

### P0' 新增测试

- U1：commit_paths 非 git 目录不抛错；dirty 仓库只 add 指定路径。
- U2：list_wb_commits / revert_commit 端到端（构造 wb 提交 → 还原 → 文件回原状）。
- U3：还原前该文件有未提交改动 → 拒绝并给提示。
- U4：web API 三端点冒烟（含错误分支）。

---

## P1 · 停滞信号语义修复（0.5–1 人天，M3 前顺手）

### 问题

weekly/collect.py L158–175 线程停滞点名与首页「>14 天未更新」都读档案 frontmatter
updated；而 thread_notes._touch_projects_updated 在**每次推进日志/产物入库**时都把
updated 刷成今天——AI 收尾（M3）会把它变成机器高频自刷新，停滞点名将失明。

### 改法（语义拆分）

1. updated = **实质更新**，只在以下时机刷新：项目建档/激活/归档/改名（registry）、
   用户显式确认的状态写回（threads/state）、审批 applied 写回项目文件后（writeback 现不刷，
   **保持不刷**，避免 AI 文案污染）。
2. thread_notes._touch_projects_updated 改为写新字段 activity_at（活动痕迹），
   不再动 updated。
3. project_scan / project_view / /api/state projects payload 增加 activity_at
   （读侧走 meta_date_iso 归一，注意 YAML 未加引号 date 对象问题——已有 vault.py 先例）。
4. 首页「>14 天未更新」提示与 weekly 停滞点名继续读 updated（语义变准）；
   首页「最近更新」若原读 updated 则改用 activity_at（展示活跃）。
5. 周复盘停滞判据（git 项目本周零提交、线程 updated 超阈值 + 有未决/未闭环跟进）不变。

### P1 新增测试

- S1：只写一条推进日志 → 档案 updated 不变、activity_at 刷新。
- S2：停滞线程（>14 天无 updated、有未闭环跟进）即使最近有日志也不被点名豁免。

---

## 验收顺序与入口

按 **P0 → P0' → P1** 串行；每完成一个 P 跑一次质量门（见上）。
人工冒烟（面板）：开面板 → 快速连点两个审批裁决（验证 T1 语义）→ 拖一条逐字稿导入 →
点「撤销系统改动」还原一次写回 → 页面与文件一致。
P0' 冒烟后如需装机：scripts/build-macos-app.sh + scripts/install-macos-app.sh
dist/SummitWorkbench.app --replace-running（自包含包，改 Python 后必须重打包；终端
open 拉起会带会话环境导致服务卡住，用启动台验证）。

## 明确不做（范围外）

- CLI 全量收口（用户不用，仅 P0 表内顺带项）。
- Obsidian 侧冲突检测/合并 UI。
- undo 覆盖飞书外部状态（任务/会议/完成态）——只做 vault 侧 + 明示文案。
- 向量库 / RAG / 常驻服务（README 硬边界）。
