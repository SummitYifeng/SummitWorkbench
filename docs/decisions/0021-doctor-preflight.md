# ADR 0021 · 统一预检 `wb doctor`（正式使用前加固）

- 状态：✅ 已实现并合并（离线全绿：ruff + ruff format + mypy --strict + pytest 355 项；
  真机 `wb doctor` 14 项全绿 exit 0）
- 日期：2026-09-02
- 里程碑：正式使用前加固（高杠杆项 #3）
- 依据：正式启用前评审「上线预检 / 单点验证」维度；承接 ADR 0019/0020

## 背景与问题

`wb diagnose` 只查底座（运行时 / 路径 / 系统工具）；各 provider 的连通性此前散在
`wb feishu smoke` / `wb model smoke`，vault 校验在 `wb vault check`，launchd 是否装好只能
自己 `launchctl list`。启用那一刻最怕的失效模式是「**配了，但某一环没通**」——某条凭据没
存进 Keychain、飞书 token 早过期、模型配置漏了、launchd 没装——而它们分散在多条命令里，
没有一处能一眼回答「明天早上的定时简报到底能不能跑」。

## 决策

一条 `wb doctor` 把端到端就绪度收敛成一张检查表，**默认完全离线、无副作用**。

- **覆盖面**：底座（复用 `diagnostics.collect`）→ vault schema（复用 `check_vault`）→ 飞书
  配置 + app_secret/refresh_token 凭据可解析 → 模型配置 + api key 可解析 → launchd 两个
  plist 是否安装。
- **三态**：`ok` / `warn`（未就绪但不阻断：未配置、可按需创建、可选组件缺失）/ `fail`
  （已配置却坏了，或硬性不达标）。退出码只由 `fail` 决定（0/1），`warn` 不影响——便于
  安装脚本 / CI 判定，同时不因「还没配」误判失败。
- **默认零副作用、绝不泄密**：只读配置与 Keychain。凭据检查走
  `security find-generic-password`，**只验证能否解析，绝不打印秘密值**；不联网、不轮换任何
  token、不产生模型费用。
- **`--online` 才碰网络**：追加一次真实飞书 token 刷新（`FeishuSession.access_token()`，会
  正常轮换 refresh_token）——这是对「每日简报飞书事实源」最直接的预检；token 失效会被识别
  为 `needs_reauthorize` 并给出「请 wb feishu login」的可执行提示（与加固 #4 同源）。
- **硬/软工具区分**：git/security 缺失=FAIL（核心）；launchctl 缺失=WARN（仅定时任务需要）。

## 实现

- 新增 `src/summit_workbench/cli/doctor.py`：`CheckStatus`（StrEnum）、`Check`、纯函数
  `run_checks(settings, *, config_file, online)`（可测，不含 typer）、`doctor_command`。
- `cli/main.py` 注册 `wb doctor`。

## 验收

- Ruff + ruff format + mypy --strict + pytest **355 项全绿**（新增 3 用例：未配置时为 WARN
  非 FAIL 且不解析凭据、`--json` exit 0、human 输出「预检通过」）。
- **真机 `wb doctor`（2026-09-02）**：14 项全绿、exit 0——Python/工具/路径/配置/vault
  schema/飞书 app_id 与两条凭据可解析/模型 deepseek-v4-flash 与 api key/ launchd brief+weekly
  均已安装。

## 稳定性收益

- 启用前「配了没通」从「散在多条命令、靠自己逐个试」→ **一条命令一张就绪表**，`fail` 才拦。
- 默认离线无副作用，可随时反复跑（含 CI）；`--online` 才做有代价的真实 token 刷新。

## 遗留

- **模型可达性不在默认预检内**：真实模型调用要花钱，故 doctor 只验证「配置完整 + api key
  可解析」，不发探测请求。真正的模型连通性仍由 `wb model smoke` 按需验证。
- **launchd 只查 plist 是否安装、不查是否 loaded/last-run 成功**：运行成败由加固 #2 的
  `wb status` 定时任务健康度回答，两者互补。
