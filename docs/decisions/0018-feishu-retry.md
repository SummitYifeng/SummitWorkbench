# ADR 0018 · 飞书 HTTP 客户端复用公共退避重试 + 尊重 Retry-After（韧性加固 LHF #3）

- 状态：✅ 已实现并合并（离线全绿：ruff + ruff format + mypy --strict + pytest）
- 日期：2026-09-01
- 里程碑：韧性加固（低垂果实 LHF #3；非新功能，兜底既有联网读路径）
- 依据：底层韧性评审「外部依赖瞬时故障」维度；NFR-6（失败必须可见，不静默吞错）、
  L41（模型调用失败重试策略）；承接 ADR 0016 遗留段 LHF #3

## 背景与问题（要根治的故障类）

两套 HTTP 出口的重试策略 **各行其是**：

- `providers/llm/client.py`（云端模型）早已有完整的指数退避重试：瞬时故障（超时 / 429 /
  5xx）按 `0.5 * 2^n` 退避最多重试 3 次（共 4 次调用），非重试类（4xx）立即抛（L41）。
- `providers/feishu/client.py`（业务 GET/POST）与 `providers/feishu/auth.py`（token 端点）
  仍是 **单发**：一次瞬时抖动——连接重置、网关 502、限流 429——就让整趟拉取直接报废，
  把一个「等 1 秒重试就好」的抖动无谓地上抛到用户面前。晨间简报/会议链路一次拉取跨多个
  飞书接口，任一接口抖一下就整链失败。

此外两处 **都没尊重 `Retry-After`**：飞书 429 限流响应会带 `Retry-After` 头指明该等多久，
盲目指数退避要么等不够（再次撞限流）、要么等过头。

另有一个隐蔽故障类：长驻 `httpx.Client` 的连接池默认无 keep-alive 过期，一条在池里 **静置
过久** 的连接，对端可能早已关闭（半开连接），下次复用它的首个请求必然失败一次。

## 决策

把退避循环抽成 **上游无关** 的公共件，飞书与 LLM 共用；补齐 `Retry-After` 与连接存活上限。

- **单一退避实现**：`send_with_retry` 承载「尝试 → 判可重试 → 退避 → 再试 / 上抛」的循环，
  上游差异通过注入点表达：`retry_on`（参与判定的异常类型）、`is_retryable`（是否瞬时）、
  `retry_after`（从异常取服务端指定等待秒数）。LLM 与飞书各自的错误语义留在各自客户端里，
  循环本身不认识任何一方。逻辑与原 LLM 循环 **等价**（既有 LLM 契约测试不改动即全绿）。
- **尊重 `Retry-After`**：`parse_retry_after` 解析该头（整数秒或 HTTP 日期，非法/缺失回退到
  指数退避）；429/503 时优先按服务端指定时长等待。两侧错误类型补 `retry_after` 字段承载。
- **飞书重试范围**：业务客户端与 token 端点现对「超时 / 网络抖动 / 429 / 5xx」重试；业务
  `code != 0`（如无权限）与其它 4xx 属 **语义失败**，立即上抛不重试（不静默吞错，NFR-6）。
- **半开连接防护**：长驻客户端统一经 `build_client` 构造，带
  `httpx.Limits(keepalive_expiry=30s)`，静置超时的连接下次重建而非复用。
- **零新增依赖**：`httpx` / `email.utils` 均既有，新增外部依赖 **0 个**。

## 实现

- 新增 `src/summit_workbench/providers/_resilient.py`：`send_with_retry[T]`、
  `parse_retry_after`、`build_client`。
- `providers/llm/client.py`：`complete` 的手写退避循环替换为 `send_with_retry`（行为等价）；
  429/5xx 的 `LLMAPIError` 带上 `parse_retry_after(resp)`；默认客户端改由 `build_client` 造。
- `providers/feishu/client.py`：`_request` 用 `send_with_retry` 包住 `_attempt_once`；先判
  HTTP 层 429/5xx（可重试，带 `Retry-After`）再解析信封；网络/超时归可重试；`code != 0`
  与其它 4xx 不重试。构造函数新增可注入的 `sleep` / `max_retries`（便于测试）。
- `providers/feishu/auth.py`：`_post_json` 把「POST + 瞬时故障重试」收成一处，`_post_token`
  与 `get_tenant_access_token` 共用；默认客户端改由 `build_client` 造。
- `LLMAPIError` / `FeishuAPIError` / `FeishuAuthError` 各补 `retryable` / `retry_after` 字段。

## 验收

- Ruff + ruff format + mypy --strict（103 源文件）+ pytest **335 项全绿**。
- 契约测试：飞书新增 5xx 抖动重试后成功、持久 5xx 耗尽重试、`code != 0` 不重试、超时重试、
  `Retry-After` 按服务端秒数等待；LLM 既有重试用例全部不改仍绿，另补 `Retry-After` 用例。
- 单测 `tests/unit/test_resilient.py`：首次成功不 sleep、退避序列（0.5/1.0…）、耗尽上抛、
  非重试立即抛、未列异常直穿、`Retry-After` 覆盖退避；`parse_retry_after` 秒数/缺失/非法/
  HTTP 日期（未来/过期归零）；`build_client` 超时透传。

## 稳定性收益

- 飞书单次瞬时抖动（连接重置 / 502 / 429）让整趟拉取报废 → **退避后自动重试**，抖动被吸收。
- 限流响应从「盲等或不等」→ 按 `Retry-After` 精确等待，减少二次撞限流。
- 长驻客户端半开连接的首请求必失败 → `keepalive_expiry` 令过期连接重建，规避。
- 附带：飞书与 LLM 从此共用同一退避实现，重试语义只有一处、行为一致、只需维护一处。

## 遗留

- **POST 重试的非幂等风险**：`send_with_retry` 对飞书 POST（如 `create_task`）也会在超时后
  重试；若请求已被服务端处理但响应在网络上丢失，重试会 **重复创建**。这与既有 LLM 客户端
  对 POST 的重试策略一致，且本工具单用户、`create_task` 触发稀疏、代价可接受，故沿用同一
  策略未做特判。若日后接入更敏感的写接口，应引入幂等键（客户端生成的 request-id）再放开
  其重试。
- **token 端点重试与单次轮换的相互作用**：飞书 `refresh_token` 单次轮换（见 ADR 0016）。
  刷新 POST 若在服务端已消费后超时，旧 RT 已作废、新 RT 未收到，重试会得到 `invalid_grant`
  → 落到既有的 `needs_reauthorize` 路径。这不比「不重试」更糟（两者都走重新授权），而对
  「连接层就没打通」的抖动则确有救。刷新的并发自毁已由 ADR 0016 的工作区锁根治，本 ADR
  不改变该结论。
