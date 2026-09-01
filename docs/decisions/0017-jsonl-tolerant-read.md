# ADR 0017 · JSONL 日志容错读 + Pydantic 逐行兜底（韧性加固 LHF #2）

- 状态：✅ 已实现并合并（离线全绿：ruff + ruff format + mypy --strict + pytest）
- 日期：2026-09-01
- 里程碑：韧性加固（低垂果实 LHF #2；非新功能，兜底既有 append-only 读路径）
- 依据：底层韧性评审「文件并发读写」维度；NFR-3（非破坏性）、NFR-6（失败必须可见，
  不静默吞错）；承接 ADR 0016 遗留段 LHF #2

## 背景与问题（要根治的故障类）

系统有两本 **追加型（append-only）JSONL** 日志，是防重与计费的事实源：

- `repositories/meeting_state.py` → `_vault/_signals/meeting-state/log.jsonl`：每次会议
  处理状态变迁追加一行，`latest_task` / `all_latest` 取同一幂等键的最后一条即当前状态，
  供防重判定与 `wb status` 汇总。
- `repositories/usage_ledger.py` → `_vault/_signals/model-usage/YYYY-MM.jsonl`：每次模型
  调用追加一行，`monthly_totals` 逐行累加算当月费用，供软预算告警。

追加写本身 **不是原子的**：进程被 `kill`、磁盘写满、断电，都可能在 `write()` 中途留下
一条 **半截行**（末行 JSON 未闭合）。此前两处都用裸 `json.loads(line)` 逐行读——

1. **一条坏行让整本崩溃**。`json.loads` 遇半截行抛 `JSONDecodeError`，直接冒泡出
   `_iter_rows` / `monthly_totals`，令 **整本** 读取失败。哪怕坏的只是最后一行，前面成百
   条完好历史也一起读不出来：`wb status` 崩、防重查询崩（可能导致重复处理同一会议）、
   当月费用汇总崩。越老、越无辜的历史，越是被末行连坐。
2. **缺键即 `KeyError`**。`meeting_state._task_from_row` 用 `row["idem_key"]` 等硬索引，
   任何一行缺键（早期 schema、手工误编辑、半截行的前半段侥幸是合法 JSON 但字段不全）
   都抛 `KeyError`，同样掀翻整本。

（写侧的单文件覆盖写此前已用 tmp + `os.replace` 原子落盘；见 ADR 0016 背景段与配套的
`repositories/_atomic.py` 归并。append-only 日志无法照搬「整文件换名」，故读侧容错是这条
故障类的正解。）

## 决策

给两本 append-only 日志一处 **通用容错读**，把「整本全损」降为「只丢坏的那一行」，
而不是逐仓库打补丁。

- **逐行校验、坏行跳过**：不再 `json.loads` 裸解析，改为逐行
  `Model.model_validate_json(line)`；解析或校验失败的行 **跳过** 而非中断整本。
- **失败可见（NFR-6）**：每条坏行 `warnings.warn(..., CorruptLogLine)`——默认落 stderr，
  定时任务/CLI 都看得见，不静默吞。
- **隔离取证、原文不动（NFR-3）**：坏行原样抄进旁挂的 `<log>.quarantine`（带时间戳与
  行号），供事后排查；**原日志一字不改**——不重写、不删行、不「修复」，只读。
- **显式 schema + 容忍漂移**：为每本日志建对应 Pydantic 行模型，`extra="ignore"` 容忍
  未来新增字段（旧读者不因未知键报错）；枚举字段（`source` / `state`）直接由 Pydantic
  校验，非法值即判该行坏、跳过，而不会污染防重判定。
- **零新增依赖**：Pydantic、`warnings` 均为既有栈内，新增外部依赖 **0 个**。

## 实现

- 新增 `src/summit_workbench/repositories/_jsonl.py`：
  - `read_models(log, model, *, quarantine=True)`：容错读整本，返回顺序保留、已校验的
    模型实例列表；文件不存在返回 `[]`（尚未写过是正常态）。
  - `CorruptLogLine(UserWarning)`：坏行告警类别（便于测试用 `pytest.warns` 断言、
    调用方按需 `filterwarnings`）。
  - `append_row(log, mapping)`：顺带统一两仓库的追加写（父目录按需建、
    `ensure_ascii=False` 保中文可读、一行一条）。
- `repositories/meeting_state.py`：新增 `MeetingStateRow`（`extra="ignore"`，`source`/`state`
  校验成枚举，`.to_task()` 转 `MeetingTask`）；`latest_task` / `all_latest` 走 `read_models`。
- `repositories/usage_ledger.py`：新增 `UsageRow`（只声明参与汇总的字段，其余 `ignore`）；
  `monthly_totals` 走 `read_models`。

## 验收

- Ruff + ruff format + mypy --strict（103 源文件）+ pytest **335 项全绿**。
- 新增 `tests/unit/test_jsonl.py`：缺文件返回空、好行按序、半截末行不崩且好行照读、
  缺键行跳过（非 `KeyError`）、坏行告警、隔离且原文不动、`quarantine=False` 不落盘、
  `extra` 漂移被忽略、空行忽略。
- `test_meeting_state.py` / `test_usage_ledger.py` 各补一条「半截末行不破坏查询/汇总」用例。

## 稳定性收益

- 半截末行（被 kill / 断电 / 磁盘满）从「整本读取崩溃、拖垮 `wb status` / 防重 / 计费」
  → **只丢那一行**，其余历史照常可用。
- 缺键行 `KeyError` 掀翻整本 → 该行被跳过并隔离告警。
- 附带：`.quarantine` 旁挂文件把「有坏行」这件事变成 **可见、可取证** 的一行记录，而不是
  一个崩溃堆栈。

## 遗留

- **坏行不自动回收**：`read_models` 只读、不改原日志，坏行会在每次读时被重复告警 +
  重复隔离（quarantine 是追加）。这是刻意的非破坏性取舍——真要清理，交由人工在确认后
  处理，而非让读路径去改写事实源。若日后坏行常态化累积，可加一个显式的 `wb` 维护子命令
  做「压实」（读出好行 → 原子重写整本），但不放进热读路径。
- **半截行的「前半合法」子集**：极少数情况下半截行的前缀恰好是一段合法 JSON 且字段齐全，
  会被当作好行收下。这在当前 schema 下概率极低（末行截断几乎必然破坏 JSON 结构），未做
  额外防护；如需更强保证可在写入行内加长度/校验和前缀，但那是过度工程，暂不引入。
