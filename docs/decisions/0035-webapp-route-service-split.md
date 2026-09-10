# ADR 0035 · Web 路由、应用工厂与服务边界拆分

- 状态：已实现（P1-03；route contract 与离线验收通过）
- 日期：2026-09-06
- Git commit：2f8019b（实现；计划/ADR 收口提交随后推送）
- 依据：产品化计划 P1-03、P0-12 会话边界、P0-07C active workspace runtime、P1-02 workspace migration

## 背景与决策

`webapp/app.py` 曾同时承担公开导入入口、FastAPI 工厂、认证/生命周期边界和全部领域路由。
后续 settings、onboarding、sync 与 diagnostics 继续扩展时，任何改动都会触碰同一个大文件。
本包把公开入口收敛为 `app.py` 兼容导出，把显式上下文工厂放在 `app_factory.py`，通过
`RouteDependencies` 将 FastAPI 应用、冻结的 `AppContext` 和 operation-id 解析器注入 router。

路由协议的稳定性由 `docs/contracts/web-route-contract.json` 固化：每条 FastAPI route 记录
method、path、请求字段、请求体模型、成功响应状态和实现中声明的稳定 error code。快照由
`scripts/update-web-route-contract.py` 从 app factory 生成，并由 contract test 校验。

## 拆分边界

`routers/system.py` 负责 version handshake 和一次性 session bootstrap；
`routers/workspace.py` 只解码 payload、映射错误 envelope 并调用 `services/workspace.py`；
workspace service 复用既有 migration workflow、Git backend 和 lock/rollback 语义，不复制业务机制。
其余领域目录已建立清晰的 ownership 边界，既有 handler 暂由 `legacy_app.py` compatibility bundle
注册，以保留闭包中的 lifespan、认证、profile switch 与 SSR 状态。此超限例外是有意的：一次机械
拆出全部 handler 会同时改变请求注册顺序和隐式运行时依赖，违背 P1-03 的“只移动、不改行为”门。
任何新增路由不得回写公开 `app.py`；后续迁移必须逐领域、逐快照完成。

## 验证证据

- route contract snapshot：59 条 route，包含 34 个请求体模型。
- `uv run pytest -q`：743 passed，1 skipped（既有需要 `WB_PACKAGED_APP` 的打包 smoke）。
- `uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy src tests` 通过。
- workspace migration、Web API、安全边界和旧 `webapp.app` monkeypatch 兼容回归通过。
- 未访问真实飞书、真实模型、Keychain、私有远端或第二台 Mac；本包不需要 Apple Developer ID。

## 后续约束

P1-04 未在本包开始。后续前端 feature 拆分必须先保持本 ADR 的 route contract 快照不变，
不得借机扩大后端路由行为或改变会话/错误 envelope。

## 2026-09-10 冗余审计收敛

本次仅删除未被 app factory、router 注册表、测试或构建引用的空路由边界文件；实际路由仍由
`legacy_app.py` compatibility bundle 或现有实现 router 注册，route contract 与错误 envelope 不变。
