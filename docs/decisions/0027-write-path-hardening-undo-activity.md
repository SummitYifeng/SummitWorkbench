# ADR 0027 · 写路径并发加固 + 系统写回自动留痕与撤销 + 停滞语义修复（稳定性审计 P0/P0'/P1）

- 状态：✅ 已实现并全绿（2026-09-04；ruff + format + mypy strict + pytest **514 项全绿**；桌面 App 重新打包装机，v0.4.1 维护加固发布）
- 日期：2026-09-04
- 里程碑：v0.4.1 · 稳定性审计（实施范围与验证证据见本 ADR）
- 依据：稳定性审计会话「写路径并发丢更新 / 全库无撤销 / 停滞点名被机器活动刷失明」三项；NFR-3（非破坏性）、NFR-6（失败必须可见，不静默吞错）；承接 ADR 0016（工作区锁）、0017（JSONL 容错读）、0019（schema 版本）

## 背景与问题

v0.4.0 已有全套原子写 / 容错读 / 工作区锁基建，但存在三类真实缺口：

1. **写路径在锁外裸奔 → 并发静默丢更新**。workspace_lock 全库只有 4 个调用点；面板/工作流的大多数写路径（审批页 RMW、inbox 追加、当日简报、快照镜像、线程日志）都是「读文件 → 变换 → 整文件重写」且无互斥，多写入者（uvicorn 线程池 + launchd brief/weekly）并发时会静默互相覆盖。线程日志/产物的序号由「同名前缀文件数 + 1」推导，两个并发写入算出同一序号即相互覆盖、一条日志无声消失。幂等账本用裸 json.loads 逐行读，一条半截行让 apply 幂等判定整体崩溃。apply 收尾用旧快照整页重写审批页，会把窗口期内用户的并发勾选/编辑静默吞掉。
2. **全库无 undo/撤销**，git 自动提交只覆盖简报产物。面板用户的每一次系统写回（捕捉/日志/产物/状态确认/审批应用/项目建档/快照镜像……）都不可逆，误操作只能人工改文件或从 git 历史手工翻找。
3. **停滞点名被机器高频活动刷失明**。weekly/collect 与首页「>14 天未更新」都读档案 frontmatter updated，而 thread_notes._touch_projects_updated 在每次日志/产物入库时把它刷成今天——M3 的 AI 收尾会把它变成机器高频自刷新，停滞信号将永久失明。

## 决策

### P0 · 写路径并发加固（把 RMW 原语收进工作区锁）

- **锁根统一**：所有新加锁点用 workspace_lock(vault_dir.parent)（生产布局下 vault_dir.parent == work_root，与 publish_brief / sync 同一把 .wb.lock；测试 tmp 天然隔离）。锁只包**文件临界区**（parse → mutate → atomic_write），绝不跨 LLM/网络调用；默认超时沿用 60s，LockBusy 必须对用户可见（CLI「工作区忙，稍后重试」exit(1)；面板可见失败）。
- 覆盖面（repository 层逐函数收口，后续 workflow/端点加锁与之同线程重入不冲突）：审批页单条/批量/修改（review_edit._rewrite/set_decisions）、refresh_review_page 的读旧页→合并→整页重写、writeback 全部 append_* 与 set_project_status、daily_note.write_brief / weekly_review.write_weekly（同时把裸 write_text 改 atomic_write_text，当日笔记可能含用户锚点外手写内容）、meeting_archive 逐字稿落盘（新建文件原子写，无需锁）、signal_snapshot 快照镜像 mark_* 与 write_snapshot、note_status.update_note_status（显式传 vault_dir，RMW 落锁）、project_registry 建档/激活/归档、review_sweep(apply=True) 整段持锁（无外部调用）。
- **apply 收尾乐观合并（P0-5）**：apply 含分钟级外部写回，全程持全局锁不可接受 → 开头记录 page_snapshot，收尾重读最新页：未变则维持整页重写；已变则只移除「本次 handled 且最新页中裁决/可编辑字段未变」的候选，被并发改动的候选留页不动（审计账本已记 → 下次 apply 按 already-completed 幂等清理、不重复执行），失败 error 标注只合并进最新页。
- **幂等账本容错读（P0-3）**：review_audit 新增显式行模型 ExecutionRecordRow（extra=ignore），读写走 _jsonl.read_models/append_row——坏行只告警 + 隔离进 .quarantine，不再整本崩溃（承接 ADR 0017）。
- **线程序号防撞（P0-4）**：thread_notes 序号分配 + _write_note + 关联档案 touch 整体持锁，写前检测目标已存在则重取序号，绝不静默覆盖。
- 跨进程互斥验证（P0-6）：两个真实子进程并发 write_brief + write_snapshot，.wb.lock 上自动互斥，最终文件完整无交错（tests/integration）。

### P0' · 系统写回自动 commit + 面板撤销按钮

- **写入即留痕**：每次系统侧写回成功后自动对触碰文件做 git commit（新 repositories/autocommit.py::commit_paths）——只 add 显式路径（绝不 add -A）、消息带 wb: 前缀、非 git 仓库返回 not-git 不抛错、空暂存幂等跳过、失败转可见状态不阻断写回；add → commit 序列放在 P0 同一把锁内（与 publish 一致）。埋点集中在 webapp 端点层 + review sweep CLI（不在 repository 写函数里，避免测试全变 git 环境）：capture / threads logs·artifacts·state / review apply / projects create·activate·archive·rename / tasks complete·update 与 meetings update（当日快照镜像）/ meetings import；launchd brief/weekly 沿用既有 publish，不重复埋。
- **撤销**：list_wb_commits（git log --grep '^wb:' + 每提交触碰文件）→ revert_commit（先校验该提交触碰路径工作树干净，脏则拒绝；git revert --no-edit，冲突自动 abort 并返回可见错误）→ 面板顶栏「↩ 撤销」：最近自动提交列表 + 差异预览 + 一键还原。边界：只作用于 vault 文件；**飞书侧副作用（已建任务/会议、已完成状态）不可撤销**，API 响应与 UI 文案明示。

### P1 · 停滞信号语义修复（updated ↔ activity_at 拆分）

- updated = **实质更新**，只在建档/激活/归档/改名（registry）与用户显式确认的状态写回（threads/state）时刷新；审批 applied 写回项目文件保持不刷（避免 AI 文案污染）。
- thread_notes 的 touch 改写新字段 **activity_at**（活动痕迹），不再动 updated。
- 读侧归一（meta_date_iso，兼容 YAML 未加引号 date 对象）：project_scan.ProjectState、/api/state projects 载荷、project_view.build_project_view 增加 activity_at。
- 首页「最近活跃」改读 activity_at（展示活跃）；「>14 天未更新」与周复盘停滞点名继续读 updated（语义变准）；周复盘停滞判据本身不变。

## 实现

- P0：锁集中在 config/locking.py::workspace_lock 既有语义上逐 repository 收口；原子写统一走 repositories/_atomic.py::atomic_write_text；审计账本复用 repositories/_jsonl.py；apply 收尾新增 _candidate_unchanged_since 判据。
- P0'：新增 repositories/autocommit.py（CommitStatus / commit_paths / list_wb_commits / revert_commit / commit_diff_text）；repositories/git.py 增 files_changed_by / log_grep / is_dirty_paths / revert / show_patch；webapp/app.py 增 _commit_suffix 埋点与 GET /api/undo/history、GET /api/undo/diff、POST /api/undo/revert；前端顶栏「↩ 撤销」模态（列表 → 差异 → 还原，含飞书侧不可撤销文案）。
- P1：thread_notes._touch_projects_activity 写 activity_at；project_scan / project_view / /api/state 与前端 chips（最近活跃 vs >14 天停滞）同步。

## 验收

- Ruff + format + mypy strict（200 文件）+ pytest **514 项全绿**（基线 491，净增 23）。
- 新增 tests/unit/test_write_concurrency.py（T1 并发 set_decision 双保留 / T2 apply 执行中并发裁决保留与反悔留页 / T3 并发 inbox 追加 / T4 并发推进日志不同文件名 / T5 brief×完成镜像文件完整 / T6 坏账本行不崩幂等 + 隔离）；tests/integration/test_cross_process_brief_lock.py（P0-6 跨进程）；tests/unit/test_autocommit.py（U1–U3）+ tests/unit/test_webapi_undo.py（U4 三端点冒烟）；weekly S2 与 project_view/project_state S1 语义测试。
- 人工冒烟（面板）：连续勾选两个审批裁决 → 拖入逐字稿导入 → 顶栏「↩ 撤销」还原一次写回 → 页面与文件一致。

## 稳定性收益

- 写路径并发：从「多写入者静默丢更新 / 一条日志无声消失 / apply 吞用户并发操作」→ 所有 RMW 在 .wb.lock 上互斥、单文件原子落盘、坏账本行只隔离不崩、apply 收尾保留并发裁决。
- 撤销：面板每次系统写回可查（git log wb:）+ 一键还原（git revert），飞书外部副作用边界在 UI 明示，误操作成本从「人肉翻 git」降到一次点击。
- 停滞语义：updated 变准后，>14 天停滞点名与首页提示对「实质停摆」负责，AI 收尾的高频机器活动不再刷失明。

## 遗留

- Work 仓库内文件的写回（如仓库项目 input/inbox.md）不进 vault 自动提交/撤销（它们随 wb sync 走各自仓库），面板「↩ 撤销」只覆盖 vault 文件——与「撤销只作用于 vault」边界一致。
- apply 外部写回与页面重读之间仍存在极小窗口语义（写回已发生但用户随后改回 pending）：候选留页、飞书侧副作用不回滚——这是撤销边界的显式取舍，账本幂等保证不重复执行。
- 坏行隔离文件（.quarantine）随读累积，人工清理或日后再加压实命令（承接 ADR 0017 遗留）。
