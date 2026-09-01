# ADR 0022 · 飞书 token 失效的优雅降级 + 可见性（正式使用前加固）

- 状态：✅ 已实现并合并（离线全绿：ruff + ruff format + mypy --strict + pytest 355 项）
- 日期：2026-09-02
- 里程碑：正式使用前加固（高杠杆项 #4）
- 依据：正式启用前评审「凭据失效 / 无人值守可见性」维度；NFR-6；承接 ADR 0020

## 背景与问题

飞书 refresh_token 会过期或被吊销。一旦失效，无人值守的 `wb brief` 已经会 **优雅降级**
（`runner.build_facts_source` 捕获飞书异常，飞书事实源缺失、简报照常出，健康度标注降级）——
这是对的。但**只降级不留痕**：用户可能连续多天不知道飞书那半边已经瞎了（会议/任务不再进
简报），直到某天偶然想起才发现要重新授权。加固 #2 的运行心跳只知道「简报跑出来了」，无法
区分「飞书正常」与「飞书 token 死了但降级出稿」。

## 决策

把「当前是否需要重新授权」持久化，并在 `wb status` 与 `wb brief` 输出里醒目提示。

- **精确识别**：`auth.refresh_token` 已把 `invalid_grant`/`invalid_request` 映射为
  `FeishuAuthError(needs_reauthorize=True)`。`build_facts_source` 改为返回结构化
  `FeishuOutcome(reason, needs_reauthorize)`——把「token 失效」与「配置缺失 / 网络抖动」等
  其它不可用原因区分开。
- **持久化授权健康度**：新增单文件状态 `_signals/feishu-auth.json`（带 `schema_version`，
  ADR 0019；原子写）。`run_brief` 在**真实运行**（write=True）且确实「拿到过飞书结论」时更新：
  token 失效→标记需重新授权（保留最早的 `since_day`，连续失效不刷新起点）；飞书恢复正常→
  清空。配置缺失等**模糊**情形不写，避免把「还没配」误标成「需重新授权」。
- **醒目呈现**：
  - `wb status` 新增一行「⚠ 飞书授权已失效（自 YYYY-MM-DD）：请 wb feishu login」，JSON 出
    `feishu_auth`。
  - `wb brief` 降级提示按是否 `needs_reauthorize` 分级：token 失效给出「请重新授权」的可执行
    路径，其它不可用仍是普通降级提示。

## 实现

- `repositories/_schema.py`：新增 `FEISHU_AUTH_STATE_VERSION = 1`。
- 新增 `repositories/feishu_auth_state.py`：`FeishuAuthState`、`read_auth_state`、
  `write_auth_state`（幂等、保留最早 since_day、恢复即清空、原子写、损坏即视为正常不误报）。
- `workflows/brief/runner.py`：`FeishuOutcome`；`build_facts_source` 结构化返回；`run_brief`
  写授权健康度并把 `feishu_needs_reauthorize` 带进 `BriefRun`。
- `cli/brief.py`：needs_reauthorize 时打印可执行的重新授权提示；JSON 增字段。
- `observability/status.py`：`StatusReport.feishu_auth` + `as_dict`。
- `cli/status.py`：需重新授权时醒目提示行。

## 验收

- Ruff + ruff format + mypy --strict + pytest **355 项全绿**（新增 4 用例：缺状态视为正常、
  读写含版本、since_day 保留最早直到恢复清空、`wb status` JSON+human 端到端暴露需重新授权）。

## 稳定性收益

- 飞书 token 失效从「静默降级、多天无人知」→ **一次失效即持久化并推到 `wb status` 与
  `wb brief`**，附「wb feishu login」的可执行修复路径；恢复后自动清除。
- 简报本身仍优雅降级照常产出（不因飞书失效而失败），可见性与可用性两不误。

## 遗留

- 目前只在**简报运行时**更新授权健康度（brief 是每日触发的高频入口，足够及时）；未额外为它
  单独轮询。若日后需要更早发现，`wb doctor --online`（ADR 0021）可主动验证。
- 尚未就「需重新授权」发去重桌面通知（`wb status` 文本已醒目、且 GUI 缺失时通知本就可能发不
  出）；如需要可复用 ADR 0020 的 NotifyState 去重通道补一条 `feishu` 通知。
