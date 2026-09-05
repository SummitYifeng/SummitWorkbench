# ADR 0031 · 多设备同步协调器与自动化主设备规则

- 状态：✅ 已实现（P0-10C 离线 production 接线与写边界收口完成；真实双设备/远端真机门未执行）
- 日期：2026-09-05
- 里程碑：v0.4.1 → P0-10（开发计划 PRODUCTIZATION_MULTI_DEVICE_DISTRIBUTION_PLAN；依赖 P0-02 本地写/自动提交事务边界、P0-09 Git 后端与凭据）
- 依据：计划 P0-10（状态机/实现要求 1–10/测试场景/验收）；NFR-3（非破坏性）

> 2026-09-05 `bf734d8` 复核曾记录上述生产缺口；P0-10C 已补齐并以本 ADR 末尾证据收口。真实私有 remote、第二台 Mac 与打包签名仍属于后续真机门，不在此处伪造通过。

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
- `automation_gate(profile)`：**只门控定时 writer**——active profile 必须同时匹配 vault
  内的 automation-primary 声明；secondary 或缺失声明返回 `not-primary`。手动同步不受角色门
  限制；env-compat（无 profile）保留开发兼容放行。
- `mutation_guard(snapshot)`：diverged/dirty 保护态拒绝修改共享 vault 的交互写
  （读/问答/浏览照常）。
- `current_snapshot()`：状态/下一步建议构建（轻量，无 fetch），从实际未推送 `wb:` 提交、
  ahead/behind、工作树与持久状态恢复 last success，并保留脱敏 remote host/逐仓库摘要。

P0-10C 还把 active profile 的显式 context、Dulwich backend、统一 mutation preflight、审批/
outbox/undo/会议导入等 Web 写路径和 commit 后 push 接入同一事务入口；网络推送始终在文件锁外。
主设备声明采用 vault 内 `automation-primary.json`，以 generation + 显式 takeover 防止旧设备心跳
自动抢主。

### 4. Web API 与 UI

- `GET /api/sync/status`：状态、pending、最后同步时间、next_step 等（不执行 git 写）；
  `/api/state` 增加 `sync_state` 摘要；`POST /api/sync/run`：手动触发一次同步。
- `/api/run/brief|weekly`（automation 定时 writer 入口）过角色门：secondary →
  HTTP 403 + `not_automation_primary`；`/api/capture` 过保护态 guard：
  diverged/dirty → 409 + `sync_diverged`（交互读不受影响）。
- SPA 顶部 sync banner：展示 state、pending、last success、ahead/behind、branch、脱敏 remote
  host、repo states、primary device/generation 与 next step；提供手动 retry 和本机脱敏 JSON export，
  不提供 force/覆盖远端按钮。

## 实现

新增/收口：`domain/sync.py`、`repositories/local_sync_state.py`、
`repositories/automation_primary.py`、`workflows/sync_coordinator.py`、统一
`workflows/local_mutation.py` 写门；Web 审批、outbox、undo、会议导入与其它共享写入口均接入；
前端 `web/src/main.ts` + `style.css` 展示完整状态并提供 retry/export（重新构建静态产物）。

## 验证

- 目标测试：A push/B ff（同 workspace_id 异 device_id）；双端离线写 → diverged 两侧
  不 force 不丢文件；offline pending 重启保留 + 联网 push 清零；auth 与 offline 明确
  区分；secondary 运行 scheduler 入口 403 not-primary（交互 brief 在 primary 上不受
  影响）；三连并发 sync 只产生一次实际 push；mutation guard；sync-state 持久化往返。
- P0-10C 目标测试覆盖实际 pending、last-success 保留、统一 guard、主设备 takeover/generation
  与 secondary 手动同步；全量门：`git diff --check`、ruff check/format、mypy（245 source files）、
  pytest（699 passed，1 skipped，2 warnings）；前端 build/verify-build 已通过。
- 全程本地 bare remote + 双 clone/双 HOME 模拟设备；未访问真实远端、
  真实 `~/Documents/Work` 或打包 App。

## 遗留 / 边界

- production 运行固定选 dulwich 后端 + 凭据 callback、remote clone 流程已由 P0-09C 提供；
  launchd/P1-01 helper 的角色门与租约细节、设置中心角色切换属后续包。
- UI banner 在打包 SPA 中生效；SSR 回退路径不展示 banner（开发态）。真实 HTTPS/双设备/
  clean-account/签名分发验证仍留在 P0-13 真机矩阵。

## P0-10C 收口证据

- active profile 的同步调用统一传入 `ActiveWorkspaceContext`、workspace-scoped `home` 与显式
  Dulwich backend；`sync-state.json` 恢复真实 pending、ahead/behind、branch、脱敏 host、逐仓库
  状态和 last success。
- `run_local_mutation` 作为 Web 共享写单一入口执行 compatibility/sync guard、业务写入、显式路径
  自动提交与锁外 push；审批、outbox、undo、会议导入及 SSR/API 写入口均已接线。手动同步不再
  错误受 automation-primary 角色门限制。
- `automation-primary.json` 以 workspace marker、唯一 device id、generation 与显式 takeover
  形成同步权威声明；API/SPA 提供完整状态、重试与脱敏导出。
- 目标回归：`tests/unit/test_sync_hardening.py`、`test_sync_coordinator.py`、`test_webapi_sync.py`、
  Web 路由回归（含上传兼容性）通过；全量 pytest `699 passed, 1 skipped`。
