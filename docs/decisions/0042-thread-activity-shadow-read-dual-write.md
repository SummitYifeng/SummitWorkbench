# ADR 0042 · P2-01B thread activity shadow-read → dual-write

- 状态：已实现（2026-09-07；旧 Markdown 仍为事实源）
- 范围：仅已有 thread activity 事件切片
- 前置：P2-01A（ADR 0040）、P1-07D（ADR 0041）

## 决策

1. P2-01B 只镜像已有 thread activity 写路径：`logs/*.md` 的 work-log 和
   `artifacts/*.md` 的 thread-doc。旧 Markdown 先写入并继续作为用户可见事实源；事件
   文件随后以追加不可变方式写入 `_events/<device>/<yyyy>/<mm>/<ulid>.json`。
2. 运行模式由 `WB_THREAD_ACTIVITY_MODE`（兼容别名
   `WB_THREAD_ACTIVITY_MIGRATION_MODE`）控制：`legacy` 关闭镜像、`shadow-read` 只读事件
   并出具比较报告、`dual-write` 在旧写入成功后追加事件并出具报告。未知值安全回退到
   `legacy`；本阶段不启用 event-primary。
3. 一致性报告比较每个 thread aggregate 的存在性、活动数量、最后活动日期、类型和
   脱敏元数据 payload，并输出稳定的差异字段。报告只包含相对 source path、日期、类型和
   计数，不包含正文、PAT、绝对本机路径或远端凭据。投影失败只进入报告，不回滚已经成功
   的旧 Markdown 写入。
4. dual-write 产生的 event 文件与旧 Markdown 进入同一次显式 Git 留痕路径集合；重复的
   causation operation 以相同 payload 幂等处理，冲突则诊断为失败。跨设备读取验证设备
   目录与事件 body 的 scope 一致后，再按 `(occurred_at, event_id)` 确定性合并投影。
5. 本阶段明确不迁移全局 inbox、会议决策、daily signal/completion events 或项目正文，
   也不重复 P1-07D 已完成的 remote preview/apply、schema 迁移、离线往返和
   diverged-protected 全套验收。

## 测试边界

新增测试覆盖乱序、重复事件、双设备离线写入、旧/新投影等价、projection failure、
dual-write 幂等和 legacy 回退；真机只需沿用 build 24 的增量冒烟结果，不要求重跑 P1-07D
全套场景。

2026-09-07 的 P2-02 build 28 双机复核确认：安装态默认 `legacy`，现场追加日志没有生成 event，
与设计中的安全默认值一致。后续若要用真实 event 验收冲突恢复，必须先记录并核对显式
`dual-write` 启用方式；若要求非技术用户自行切换，则需另做图形化配置，不能把环境变量视为
已经交付的用户设置。
