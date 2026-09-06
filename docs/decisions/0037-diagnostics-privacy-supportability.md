# ADR 0037 · 诊断包、结构化日志与隐私边界

- 状态：已实现（P1-05；脱敏、导出预览、容量上限与离线验收通过）
- 日期：2026-09-06
- 依据：产品化计划 P1-05、ADR 0032 macOS 内部发布、ADR 0036 前端生命周期边界

## 背景与决策

内部用户遇到问题时需要可复制、可导出的证据，但工作台包含会议正文、提示词、模型响应和
多种 provider 凭据。本包采用本地 JSONL 结构化日志和本地 zip 诊断包，不添加远程 telemetry，
也不依赖真实账号或网络。

Python 与 Swift 共同使用相同字段语义：`timestamp`、`level`、`component`、`event`、
`operation_id`、workspace/device 短码和 `error_code`。Swift 同时保留历史 `ts` 字段以兼容
既有生命周期摘要。Python logger 与 macOS launcher 写入同一路径；读取诊断时再次经过 redactor，
即使旧日志已有未脱敏内容也不会直接进入导出包。

中央 redactor 按字段名丢弃 secret/token/password/credential/prompt/response/body 等内容，
并按文本规则处理 Authorization、Bearer、Cookie、远程 URL userinfo、canary 和本机 `/Users/`
路径。日志单文件默认 5 MiB、保留 3 个轮转文件，写入使用锁、flush 和 fsync。

诊断包只包含一个 `diagnostics.json`，内容限定为版本/架构、构建信息、workspace schema 状态、
状态摘要、同步计数、provider config 键名、内部 ad-hoc 签名摘要和最近脱敏错误。设置页先展示
文件清单，再支持导出；macOS 原生桥提供打开 `~/Library/Logs`。浏览器环境使用 Blob 下载回退。

## 诊断能力与取舍

- auth：最近错误的稳定 `error_code` 加上安全的 `needs_reauthorize` 状态可识别认证失效。
- offline/server crash：错误日志保留组件、级别和稳定错误码，但不保留请求正文。
- schema：快照记录 `valid`/`invalid` 与 marker schema version，损坏 marker 不会让诊断出口失效。
- sync divergence：快照记录同步 state、ahead、behind 和 pending commits。
- crash report：继续由 macOS/本机日志承载；本包不上传任何内容。

## 验证证据

- `tests/unit/test_diagnostics.py`：canary、会议正文、Authorization、Cookie、远程凭据 URL、Home
  路径、日志轮转、配置键名、无真实 HOME 和 zip 单文件契约均通过。
- `native/tests/AutomationServiceManagerTests.swift`：Swift 侧 canary、Bearer、Cookie、正文、
  Home 路径与错误码保留契约通过。
- `uv run pytest -q`：748 passed，1 skipped（既有需 `WB_PACKAGED_APP` 的 packaged-app smoke）。
- `uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy src tests`、
  `npm --prefix web run test:frontend`、前端 `verify-build`、Swift arm64 编译测试和脚本语法检查通过。

## 未验证事项

未执行真实飞书/模型/远端、Apple Developer ID、第二台 Mac 或 packaged-app GUI 黑盒；本包不需要
这些条件。用户后续若要确认 GUI 下载行为，可在当前 Mac Studio 的设置页点击“查看诊断包清单”、
“导出诊断包”和“打开日志目录”，无需新权限。
