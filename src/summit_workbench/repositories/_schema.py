"""持久化数据的 schema 版本登记（正式使用前加固）。

**动机**：一旦开始正式使用，真实数据就持续累积（用量账本每次模型调用一行、状态账本
每次变迁一行、每日一份快照）。将来任何持久化格式演进，都要对 **存量线上数据** 做兼容读
或迁移。在每条记录 / 每个文件里内嵌一个 ``schema_version``，是把「事后对线上数据做多版本
兼容读」变成可能的前置条件——现在加只是一个默认值，等积累了半年数据再补就得写迁移脚本
并兼容多版本。这个只有在数据尚少（正式使用前）做才便宜。

**单一事实源**：各持久化工件的当前版本号集中在此，一处 bump、一处登记迁移说明。

**版本策略**：从 ``1`` 起。历史数据在引入本机制之前写就、行内不含该字段——读取模型把
缺失的 ``schema_version`` 默认解读为 ``1``，因此旧数据无需回填即视为 v1。字段是 **附加**
（additive）演进：新增字段时保持向后兼容读者不报错（各行模型 ``extra="ignore"``），仅在
发生 **破坏性** 语义变更时才 +1 并在此登记对应的迁移处理。
"""

from __future__ import annotations

#: 所有持久化工件统一使用的版本字段名。
SCHEMA_VERSION_FIELD = "schema_version"

#: 会议处理状态账本（``_signals/meeting-state/log.jsonl``）一行的 schema 版本。
MEETING_STATE_VERSION = 1

#: 模型用量账本（``_signals/model-usage/YYYY-MM.jsonl``）一行的 schema 版本。
USAGE_LEDGER_VERSION = 1

#: 每日信号快照（``_signals/YYYY-MM-DD.json``）文件的 schema 版本。
SIGNAL_SNAPSHOT_VERSION = 1

#: 定时任务运行心跳（``_signals/run-heartbeat/log.jsonl``）一行的 schema 版本。
RUN_HEARTBEAT_VERSION = 1

#: 飞书授权健康度（``_signals/feishu-auth.json``）文件的 schema 版本。
FEISHU_AUTH_STATE_VERSION = 1
