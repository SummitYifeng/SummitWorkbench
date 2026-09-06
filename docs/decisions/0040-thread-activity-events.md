# ADR 0040 · P2-01A thread activity 事件切片

- 状态：进行中（只完成第一个低风险 aggregate 的模型/存储/投影切片）
- 日期：2026-09-06
- 依据：产品化计划 P2-01A、ADR 0027、P0-10 多设备同步边界

## 决策

thread activity 先使用 `_vault/_events/<device_id>/<yyyy>/<mm>/<ulid>.json` 的单文件事件
布局。事件包含 schema、event id、workspace/device、UTC `occurred_at`、kind、aggregate
id、payload 和 causation operation id。事件文件使用独占创建、flush/fsync 和目录 fsync；
同一 event id 的相同内容重复写入是幂等 no-op，冲突内容拒绝，代码不提供更新或删除路径。

事件 id 是带设备命名空间的单调 ULID：同一生成器在时钟相同或倒退时仍严格递增，离线设备
使用不同的稳定熵命名空间。投影按 `(occurred_at, event_id)` 稳定排序、按 event id 去重，
只生成 thread activity view；投影可从事件文件重建。

## 边界

本切片不迁移全局 inbox、meeting review decisions、daily signal/completion events 或项目
正文，不接入 shadow-read、dual-write 或 event-primary，不把 Git commit 当业务事件。当前
属性测试覆盖时钟倒退、同刻离线设备、乱序/重复事件、范围隔离、幂等写入和损坏拒绝；跨设备
真实 Git 合并仍属于后续验收，不在本 ADR 中宣称已通过。
