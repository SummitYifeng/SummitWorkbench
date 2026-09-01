# ADR 0019 · 持久化数据 schema 版本号（正式使用前加固）

- 状态：✅ 已实现并合并（离线全绿：ruff + ruff format + mypy --strict + pytest 338 项）
- 日期：2026-09-02
- 里程碑：正式使用前加固（高杠杆项 #1；非新功能，为存量数据的可演进性打地基）
- 依据：正式启用前评审「数据格式演进 / 迁移成本」维度；承接 ADR 0016–0018 韧性线

## 背景与问题（要规避的未来成本）

系统有三类 **系统自身回读、correctness 依赖** 的机器状态落盘：

- `repositories/meeting_state.py` → `_signals/meeting-state/log.jsonl`：每次状态变迁一行，
  是防重的事实源。
- `repositories/usage_ledger.py` → `_signals/model-usage/YYYY-MM.jsonl`：每次模型调用一行，
  是计费与软预算的事实源（记录数最多，随使用线性累积）。
- `repositories/signal_snapshot.py` → `_signals/YYYY-MM-DD.json`：每日一份快照，用于北极星
  指标基线与幂等核对。

此前这三类落盘 **都不带版本标识**。在「尚未正式使用、数据量近零」的当下这无所谓；一旦开始
正式使用，真实记录就持续累积，**将来任何格式演进都要面对存量线上数据**——要么写迁移脚本、
要么在读路径里靠字段有无去「猜」这行是旧格式还是新格式。两者都比「一开始就带版本号」贵得多。
这是一个 **时间窗口敏感** 的加固：现在做只是加一个默认值，事后补则要迁移 + 多版本兼容读。

（本 ADR 刻意 **不覆盖** vault 内的 markdown 笔记 frontmatter：那些是人类可读、宽松再解析、
且可再生的产物，迁移压力小，如需版本化另立 ADR。此处聚焦纯机器状态。）

## 决策

给上述三类机器状态各内嵌一个 `schema_version`，并把版本号集中到 **单一登记表**。

- **统一字段名**：`schema_version`（`repositories/_schema.py::SCHEMA_VERSION_FIELD`）。
- **单一事实源**：各工件的当前版本号集中在 `_schema.py`（`MEETING_STATE_VERSION` /
  `USAGE_LEDGER_VERSION` / `SIGNAL_SNAPSHOT_VERSION`），演进格式时在此 +1 并登记迁移说明。
- **从 1 起、缺失即 v1**：引入本机制前写的历史行不含该字段——读取模型把缺失默认解读为 `1`，
  因此旧数据 **无需回填**（承接 ADR 0017 的 `extra="ignore"` 漂移容忍思路：附加式演进，
  向后兼容读者不报错）。
- **写侧打版**：两本 JSONL 在 `record_task` / `append_usage` 组行时前置 `schema_version`；
  快照在 `write_snapshot` 顶层前置。读侧不因版本拒绝，只把字段带出供将来迁移代码分支。
- **零新增依赖**。

## 实现

- 新增 `src/summit_workbench/repositories/_schema.py`：字段名常量 + 三个版本号常量 + 策略文档。
- `meeting_state.py`：`MeetingStateRow` 加 `schema_version: int = 1`；`record_task` 写入时前置。
- `usage_ledger.py`：`UsageRow` 加 `schema_version: int = 1`；`append_usage` 写入时前置。
- `signal_snapshot.py`：`write_snapshot` 顶层前置版本号，并 **顺带把落盘改为原子写**
  （`_atomic.atomic_write_text`）——这是此前唯一一处仍用裸 `write_text` 覆盖写的持久化点，
  补齐后与 ADR 0016/0017 的原子写/容错读对称（断电/被 kill 不再留半截 JSON 污染当日快照）。

## 验收

- Ruff + ruff format + mypy --strict + pytest **338 项全绿**（较 335 +3 新用例）。
- 新用例：状态行/用量行写盘后 `schema_version` == 当前版本；缺该字段的旧行读取解读为 v1
  且防重查询/汇总照常；快照顶层带版本且覆盖写幂等。

## 稳定性 / 扩展性收益

- 三类事实源从「无版本、将来迁移要靠字段猜」→ **每条记录自带版本**，将来格式演进可在读路径
  按 `schema_version` 精确分支，迁移成本从「事后补」降到「一开始就有」。
- 附带：每日快照落盘变原子，补齐最后一处非原子写。

## 遗留

- vault markdown frontmatter 未版本化（见「背景」括注），如需另立 ADR。
- 读侧目前对「未来更高版本」不设防（附加式演进下仍可读）；真出现破坏性变更时，在 `_schema.py`
  登记并于读路径显式分支处理，而非在热读路径加通用迁移框架（避免过度工程）。
