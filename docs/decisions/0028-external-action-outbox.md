# ADR 0028 · 飞书外部动作 Outbox 与不确定态

- 状态：✅ 已实现并通过离线质量门（2026-09-05）
- 日期：2026-09-05
- 里程碑：P0-04 · 多设备与可分发产品化
- 依据：产品化计划 P0-03/P0-04；ADR 0018（飞书重试）；ADR 0019（schema 版本）；NFR-3（非破坏性）与 NFR-6（失败可见）

## 背景

本地审批页的“批准”与飞书远端创建不是同一个事务。即使客户端只发送一次非幂等请求，服务端也可能已经创建任务/日历事件而客户端在收到响应前超时。若下一次 apply 直接再次 POST，就会产生重复副作用；如果进程在请求前退出，又不能把已准备的动作静默丢掉。

## 决策

### 追加型动作账本

所有飞书任务和会议创建先在 `_signals/external-actions/log.jsonl` 追加 `prepared`，随后追加 `sending`，再追加终态。账本使用显式 schema 版本、Pydantic 行模型和现有容错 JSONL 读写；损坏行告警并隔离到 `.quarantine`，不重写历史。

每条记录包含 operation id、candidate id、工作区 id、动作类型、规范化业务请求指纹、目标账号引用、状态、尝试次数、时间、远端 id、脱敏错误和是否允许重试。请求正文、Authorization、app secret、模型 key 和会议全文不落账本。当前尚无 P0-07 的 workspace marker 时，用工作区路径的不可逆短摘要作为兼容 workspace id，不创建新的 marker。

### 状态与重试边界

```text
prepared -> sending -> succeeded
                    -> failed
                    -> unknown
unknown -> reconciled-succeeded
         -> reconciled-not-found -> prepared（再次确认）
```

`failed` 只表示已确认远端拒绝或本地验证失败，可在下一次 apply 形成新的准备动作；`sending`、`unknown` 和尚未确认的 `reconciled-not-found` 禁止自动再次创建。已成功或已核对成功的动作重复 apply 只读取远端 id，不调用创建器。恢复重试复用同一 operation id 追加新的 `prepared` 事件，保留完整时间线。

### 网络和 UI

Outbox 状态写入不跨网络锁；`review_apply` 逐条捕获 FeishuError、验证错误和本地 IO 错误，单条失败不影响同批后续动作。任务继续使用稳定的 client token；会议使用 candidate id 与 operation id 的最小 WB marker。当前适配器没有可靠的远端按 marker 查询能力，因此“重新核对”会明确提示人工确认，面板提供确认已创建、确认未创建和二次确认重试。

## 后果

- 丢响应不再等价于“可以再建一次”，重复 apply 的边界由本地账本决定。
- 远端已经成功但本地状态写回失败时仍需人工核对；系统不猜测、不自动重试。
- 账本只保存指纹和最小标识，不能仅凭本地记录还原完整会议正文；这是避免把敏感输入变成长期审计数据的取舍。
- 当前没有真机 Feishu 查询能力，人工确认仍是 P0-04 的明确产品边界；后续若 provider 提供可靠查询，可在同一状态机上增加只读 recheck。

## 验收

- 目标测试覆盖未知结果禁止第二次 POST、成功幂等、单条 FeishuError 不阻断批量、prepared 重启可见、坏行隔离和工作区隔离。
- 使用 fake、MockTransport 和临时目录；未访问真实飞书、模型、Keychain 或真实工作目录。
