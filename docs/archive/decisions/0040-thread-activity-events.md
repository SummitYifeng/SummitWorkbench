# ADR 0040 · P2-01A thread activity 事件切片

- 状态：已完成（2026-09-07；作为 P2-01B 的事件基础）
- 日期：2026-09-06
- 依据：产品化计划 P2-01A、ADR 0027、P0-10 多设备同步边界

## 决策

thread activity 先使用 `_vault/_events/<device_id>/<yyyy>/<mm>/<ulid>.json` 的单文件事件
布局。事件包含 schema、event id、workspace/device、UTC `occurred_at`、kind、aggregate
id、payload 和 causation operation id。事件文件使用独占创建、flush/fsync 和目录 fsync；
同一 event id 的相同内容重复写入是幂等 no-op，冲突内容拒绝，代码不提供更新或删除路径。

事件 id 是带设备命名空间的单调 ULID：同一生成器在时钟相同或倒退时仍严格递增，离线设备
使用不同的稳定熵命名空间。投影按 `(occurred_at, event_id)` 稳定排序、按 event id 去重，
只生成 thread activity view；投影可从事件文件重建。P2-01B 还提供跨设备读取与合并投影，
不改变事件的追加不可变约束。

## 边界

本切片不迁移全局 inbox、meeting review decisions、daily signal/completion events 或项目
正文，不把 Git commit 当业务事件。shadow-read、dual-write 与 event-primary 的边界由 ADR
0042 决定；跨设备真实 Git 合并仍属于 P1-07D 的同步验收，不在本 ADR 中重复宣称。
