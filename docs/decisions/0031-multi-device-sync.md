# ADR 0031 · 多设备同步协调器与自动化主设备规则

- 状态：🟡 部分完成（状态机与既有质量门全绿；生产持久化/全写边界/主设备声明等待 P0-10C）
- 日期：2026-09-05
- 里程碑：v0.4.1 → P0-10（开发计划 PRODUCTIZATION_MULTI_DEVICE_DISTRIBUTION_PLAN；依赖 P0-02 本地写/自动提交事务边界、P0-09 Git 后端与凭据）
- 依据：计划 P0-10（状态机/实现要求 1–10/测试场景/验收）；NFR-3（非破坏性）

> 2026-09-05 `bf734d8` 复核：十态模型、基础协调器、API 与 banner 已实现；active-profile 状态持久化、准确 pending/last-success、统一写前保护与提交后 push、完整 UI 字段、remote clone 和主设备唯一声明尚未闭环。以计划 P0-10C 完成证据作为本 ADR 转为“已实现”的条件。

## 背景与问题

现有多设备形态缺失可观察的同步状态机：工作树脏、分叉、离线本地领先、认证失败混在
普通失败里，用户无法判断「能不能写、下一步做什么」；也没有 automation-primary 角色门
（两台设备可能都跑 launchd 定时 writer 重复生成简报/周报）。

## 决策

### 1. 状态机（`domain/sync.py`，纯模型无 IO）

十态：unconfigured / ready / syncing / offline-local-ahead / remote-ahead /
local-ahead / diverged-protected / dirty-protected / auth-required / error。
纯函数负责分类与合并：`is_offline_error`（连接/超时/不可达关键词，与 auth/TLS 明确
区分）、`classify_repo_error`、`combine_repo_states`（优先级 auth > diverged >
dirty > offline > error > ahead/behind > ready）、`state_from_counts`、`next_step_for`
（UI 下一步建议，不含凭据/路径）。`SyncSnapshot` 为持久化模型（pending 计数、
最后同步时间、ahead/behind、branch 等）。

### 2. 本机状态持久化（`repositories/local_sync_state.py`）

`profiles/<workspace_id>/sync-state.json`（P0-07 布局，不同步），原子写、文件 0600、
目录 0700。**仅 ACTIVE profile 场景（调用方显式传 home）落盘**；env-compat（未建档
旧形态）不写盘，避免在无 profile 时触碰真实 Application Support。

### 3. 协调器（`workflows/sync_coordinator.py`）

- `sync_workspace(vault_dir, ...)`：workspace 锁内对 vault 及 work_root 直接子仓库
  执行 fetch →（clean）ff-merge → push；**绝不 force/rebase/stash/reset**；ff 失败且
  非离线/auth 即 `diverged-protected`（不丢任一侧本地提交）；push 非快进 →
  `diverged-protected`；auth → `auth-required`；网络关键词 → `offline-local-ahead`。
- `push_after_commit()`：wb commit 之后的中心推送能力（锁外、失败不回滚、保留本地
  提交与 pending 计数，联网后再次同步即清零）。
- `automation_gate(profile)`：**只门控定时 writer**——active profile 为 secondary →
  `not-primary`（不执行并记录）；env-compat（无 profile）放行（保持 launchd 开发用法，
  P0-11 设置中心接管后切换）。
- `mutation_guard(snapshot)`：diverged/dirty 保护态拒绝修改共享 vault 的交互写
  （读/问答/浏览照常）。
- `current_snapshot()`：状态/下一步建议构建（轻量，无 fetch）。

### 4. Web API 与 UI

- `GET /api/sync/status`：状态、pending、最后同步时间、next_step 等（不执行 git 写）；
  `/api/state` 增加 `sync_state` 摘要；`POST /api/sync/run`：手动触发一次同步。
- `/api/run/brief|weekly`（automation 定时 writer 入口）过角色门：secondary →
  HTTP 403 + `not_automation_primary`；`/api/capture` 过保护态 guard：
  diverged/dirty → 409 + `sync_diverged`（交互读不受影响）。
- SPA 顶部最小 sync banner：仅当状态非 ready/unconfigured 时显示
  「同步：<state>（待推送 N）— 下一步」；每 60s 轮询刷新。

## 实现

新增：`domain/sync.py`、`repositories/local_sync_state.py`、
`workflows/sync_coordinator.py`、`tests/unit/test_sync_coordinator.py`、
`tests/unit/test_webapi_sync.py`；`webapp/app.py` 加端点与门；前端
`web/src/main.ts` + `style.css` banner（重新构建静态产物）。

## 验证

- 目标测试：A push/B ff（同 workspace_id 异 device_id）；双端离线写 → diverged 两侧
  不 force 不丢文件；offline pending 重启保留 + 联网 push 清零；auth 与 offline 明确
  区分；secondary 运行 scheduler 入口 403 not-primary（交互 brief 在 primary 上不受
  影响）；三连并发 sync 只产生一次实际 push；mutation guard；sync-state 持久化往返。
- 全量门：`git diff --check`、`ruff check .`、`ruff format --check .`、`mypy`
  （240 files）、`pytest`（677 passed, 1 skipped）通过；`npm --prefix web run build`
  与 `node web/scripts/verify-build.mjs src/summit_workbench/webapp/static` 通过。
- 全程本地 bare remote + 双 clone/双 HOME 模拟设备；未访问真实远端、
  真实 `~/Documents/Work` 或打包 App。

## 遗留 / 边界

- production 运行固定选 dulwich 后端 + 凭据 callback、remote clone 流程、
  pending push 的逐端点触发策略、launchd/P1-01 helper 接入角色门与租约细节随
  P0-13/P1-01 落地；设置中心角色切换与 banner 交互深化属 P0-11。
- UI banner 在打包 SPA 中生效；SSR 回退路径不展示 banner（开发态）。
