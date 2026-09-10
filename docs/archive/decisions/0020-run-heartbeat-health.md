# ADR 0020 · 定时任务运行心跳 + 健康度 + 连续失败告警（正式使用前加固）

- 状态：✅ 已实现并合并（离线全绿：ruff + ruff format + mypy --strict + pytest 347 项）
- 日期：2026-09-02
- 里程碑：正式使用前加固（高杠杆项 #2；落地 memory 挂账的「跨日健康度 / 连续失败告警」）
- 依据：正式启用前评审「无人值守可见性」维度；NFR-6（失败必须可见）；承接 ADR 0019

## 背景与问题（要根治的故障类）

`wb brief` / `wb weekly` 由 launchd 无人值守定时运行（每日 08:00 / 周一 07:30，见 ADR 0015
M2-7）。一旦某天失败——飞书 token 过期、模型耗尽、磁盘满、异常崩溃——目前唯一痕迹是
launchd 的 `StandardErrorPath` 日志文件，用户 **不会主动去看**。桌面通知走 `osascript`，而
launchd 上下文常无活跃 GUI 会话，通知可能发不出（`notifier` 会安全空转返回 False）。于是
故障 **静默失联**：可能连续多天没出简报而毫不知情——恰是无人值守最危险的失效模式。

## 决策

每次真实运行落一条 **心跳**，由纯规则推导每个任务的健康度，`wb status` 醒目呈现，并在
连续失败跨阈值时按去重规则告警一次。

- **心跳落盘**：append-only JSONL `_signals/run-heartbeat/log.jsonl`，每次运行追加一行结局
  （`success` / `degraded` / `failed`）。沿用状态账本写法，带 `schema_version`（ADR 0019）、
  走容错读通道（ADR 0017，坏行不拖垮健康度汇总）。
- **记录点在 CLI 边界**：`brief_command` / `weekly_command` 包 try/except——正常产出记
  success（飞书不可用或排序回退记 `degraded`），抛异常记 `failed` 后重新抛出。`--dry-run`
  预览不记（不污染运行史）。
- **记录最佳努力、绝不反噬**：`observability/heartbeat.record_run_safely` 吞掉记录自身的
  落盘异常——宁可少一条心跳，也不让「日志器失败」掩盖或替换任务的真实结局。
- **健康度是纯领域**：`domain/run_health.evaluate_runs` 输入按时间排列的心跳事件，输出每个
  任务的 `JobHealth`（上次何时跑、上次结局、当前**连续失败连击**、总运行数）。降级也算
  「跑出来了」（`ok`），仅 `failed` 计入失败连击。
- **告警去重**：连续失败 ≥ 阈值（默认 3，memory 定）即发一条 `run` 通知；`NotifyState` 新增
  `run_failures_alerted`（每任务已告警到的失败数）去重——连击继续增长才再告警，一旦成功
  清零则未来新连击可重新告警。复用既有 `check_and_update` 读写去重状态的通道。
- **零新增依赖**。

## 实现

- `repositories/_schema.py`：新增 `RUN_HEARTBEAT_VERSION = 1`。
- `domain/run_health.py`（纯）：`RunStatus`（StrEnum）、`RunEvent`、`JobHealth`、
  `evaluate_runs`、`KNOWN_JOBS`、`CONSECUTIVE_FAILURE_ALERT_THRESHOLD`。
- `repositories/run_heartbeat.py`：`RunHeartbeatRow`（`extra="ignore"`）、`record_run`、
  `read_events`（容错读→`RunEvent`）。
- `observability/heartbeat.py`：`record_run_safely`（吞异常）。
- `cli/brief.py` / `cli/weekly.py`：CLI 边界记心跳（成功/降级/失败）。
- `observability/status.py`：`StatusReport` 增 `runs: dict[str, JobHealth]`，`build_status`
  读心跳汇总，`as_dict` 输出。
- `cli/status.py`：新增「定时任务健康度」区块（✅/⚠️/❌ + 最近运行日 + 连续失败数）。
- `observability/alerts.py` + `repositories/notify_state.py`：连续失败告警 + 去重状态字段
  （`.get` 默认读，向后兼容旧 state.json）。

## 验收

- Ruff + ruff format + mypy --strict + pytest **347 项全绿**（较 338 +9 新用例）。
- 新增 `tests/unit/test_run_health.py`：健康度推导（从未运行/失败连击只数末尾/降级破连击且
  算 ok/ran_on）、心跳读写带版本、旧行无版本读作 v1、半截末行不破坏读、连续失败 3 次告警
  一次且去重、未达阈值不告警、连击增长再告警、成功清零可重新告警。

## 稳定性收益

- 无人值守失败从「静默失联、只在 stderr 日志里」→ **`wb status` 一眼可见**「简报最近何时
  跑、成没跑出、是否连续失败 N 次」；连续失败还会触发一次去重告警。
- 心跳记录失败被吞，绝不反过来令任务失败（日志器不是新的故障点）。

## 遗留

- **「今日未运行」不主动告警**：健康度只在有心跳时判定「上次何时跑」。「本应跑却没跑」
  （launchd 未触发/机器关机）需要「预期时刻表」知识，未做——避免误报，留待需要时接入。
- **「连续 N 天零信号」未纳入**：memory 另有「连续 7 天零信号」诉求，属简报内容层信号
  （非运行成败），与本 ADR 的运行心跳正交，另议。
- 告警仍走既有 `wb status --notify` + `osascript` 通道；GUI 缺失时通知本身仍可能发不出，
  但心跳与 `wb status` 文本呈现不依赖 GUI，可见性已根本改善。
