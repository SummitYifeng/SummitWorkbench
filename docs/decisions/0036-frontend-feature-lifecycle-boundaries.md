# ADR 0036 · 前端 feature 边界与 workspace 生命周期

- 状态：已实现（P1-04；等价重构、作用域隔离与构建验收通过）
- 日期：2026-09-06
- 依据：产品化计划 P1-04、ADR 0035 Web route contract、P0-11B profile 切换、P0-12 native lifecycle

## 背景与决策

前端原本把 API fetch、版本握手、草稿恢复、问答 localStorage、同步 banner、审批和设置交互
全部放在 `web/src/main.ts`。profile 切换和动态服务重启加入后，这会让一个页面的状态污染另一个
workspace，也让请求在切换期间继续回写旧页面。

本包保持 vanilla TypeScript，不引入大型框架；`main.ts` 只负责导入样式、导入启动器和启动应用。
API 统一经 `api/client.ts`，失败响应按服务端 error envelope 归一化为 `ApiError`，每个请求受
AbortController 管理，profile commit 后由 client `dispose()` 中止未完成请求。active workspace
由 `core/workspace-store.ts` 管理，存储键使用 `workspaceScopedKey()`；store 也提供订阅和 dispose，
避免 profile 切换后留下旧 workspace 的观察者。

## Feature 边界

`features/onboarding`、`workspace`、`projects`、`threads`、`review`、`sync`、`settings` 均有
独立入口边界；本包保留原有 DOM 字符串渲染、CSS、键盘行为和 native bridge。既有大型等价 UI
实现暂由 `legacy-main.ts` 作为兼容 feature bundle 承载，新基础层从该 bundle 接入；之后新增或
迁移 feature 必须从对应目录导入，不得重新堆回 composition root。

存储迁移不复用未知 workspace 的旧键：draft 在未完成 version handshake 时落到显式 `unknown`
作用域，握手成功后切换到真实 workspace id；问答线程始终按当前 workspace id 存取。旧的无作用域
draft 键仅在清理时删除，不会被读取恢复。

## 验证证据

- `web/src/main.ts`：6 行 composition root。
- `npm --prefix web run test:frontend`：build identity、feature structure、onboarding/sync/review/
  profile 浏览器交互契约通过。
- `npx tsc --noEmit`、生产 build 与 `verify-build.mjs` 通过；产物 build identity 为
  `v2026.09.06-02bef98-edf6ec8e`。
- `uv run pytest -q`：743 passed，1 skipped（既有 packaged-app smoke）。Python 质量门全部通过。
- 未访问真实飞书、模型、Keychain、私有远端或第二台 Mac。

## 后续约束

P1-05 未在本包开始。P1-05 的诊断包不得读取或导出 workspace 正文、问答内容、prompt、cookie
或凭据；其日志字段必须与本包的 operation id 和 workspace scope 对齐。
