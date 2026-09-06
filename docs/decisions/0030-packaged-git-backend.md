# ADR 0030 · 可打包 Git 后端（system ↔ dulwich）与凭据适配

- 状态：✅ 已实现（P0-09C 离线 production/backend 与 remote clone 接线完成；P1-07D 已把打包运行的真实 HTTPS TLS 接到随 bundle 分发的 certifi CA，剩余真机门见「遗留 / 边界」）
- 日期：2026-09-05
- 里程碑：v0.4.1 → P0-09（开发计划 PRODUCTIZATION_MULTI_DEVICE_DISTRIBUTION_PLAN；依赖 P0-01 撤销信任边界、P0-07 workspace/profile 与凭据作用域）
- 依据：计划 P0-09（能力契约 / 实现要求 1–8 / 测试矩阵 / 决策门）；NFR-3（非破坏性）、NFR-4（凭据不入文件/仓库）

> 2026-09-05 `bf734d8` 复核：system/dulwich conformance、typed errors 与 workspace-scoped 凭据模型已经实现；凭据尚未进入 Dulwich clone/fetch/push transport，production backend 仍由环境变量选择，clone staging/marker 确认与 packaged CA smoke 未完成。以下 P0-09C 收口记录已更新这些结论。

## 背景与问题

目前所有 Git 操作都经系统 ``git`` CLI（subprocess）：Mac Studio 上可用，但全新 Mac 的
打包 App 会触发 Xcode Command Line Tools 安装弹窗，且凭据依赖系统 credential helper，
无法按 workspace 隔离。P0-09 要求生产（打包）环境不依赖系统 git，同时**不得一边换库
一边改变同步语义**。

## 决策

### 1. Backend Protocol + 双后端（`repositories/git_backend.py` / `system_git.py` / `dulwich_git.py`）

- `GitBackend` Protocol 定义能力契约：detect/init/clone、status 与
  staged/unstaged/untracked、add 显式路径、commit、log/filter、diff、revert wb commit、
  remote/upstream、fetch、ahead/behind、fast-forward、push、branch、identity、错误分类。
- `SystemGitBackend`：从旧 `GitRepo` 逐字提取的 subprocess 实现，行为零变化
  （development/CLI 默认）。
- `DulwichGitBackend`：生产后端（`dulwich>=0.22`，纯 Python），**绝不在任何路径调用
  系统 git**；revert 用「只支持撤销后未被后续提交改动的路径」的反向树重建 + 冲突 typed
  错误；push/fetch/ff 均只做快进，绝不 force/rebase/stash/reset。
- typed errors：`GitNonFastForward` / `GitConflictError` / `GitAuthError` /
  `GitTlsError` / `GitRemoteUnavailable` / `GitInvalidRevision`，全部派生 `GitError`，
  既有上层可统一捕获。
- conformance suite（`test_git_backends.py`）先于调用方迁移建立：两个后端对**同一临时
  bare remote** 跑同一场景（含 PATH 为空时 dulwich 完成 init/commit/fetch/ff/push 的
  证明）。
- 运行时选择：默认 `system`（开发/CLI 现状）；production/packaged 调用方通过显式 backend
  注入固定 `dulwich`，不依赖跨请求的进程环境；`WB_GIT_BACKEND=dulwich` 仅保留给
  development conformance 与离线调试。

### 2. 凭据（`config/git_credentials.py`）

- 只经 workspace-scoped Keychain（P0-07 API）：service=
  `com.summitworkbench.credentials.<workspace_id>`，account=`git:<host>:<username>`。
- 凭据**绝不**进入 remote URL / 磁盘 / 日志 / `repr` / 异常 / fixture：
  `strip_credentials()` 剥 userinfo 用于展示；`GitCredentials` 只承载 username +
  `SecretStr`，repr 不泄密（canary 测试锁定）。
- author 身份：`profile_identity(profile)` = profile 显示名 + 可选 `user_email`
  （LocalProfile 新增可选字段，config.toml 持久化）；缺省用本地占位 `wb@local`，
  **绝不复制开发者 identity**。

### 3. 评估记录（实现要求 7，打包/HTTPS 现状）

- 依赖/许可：dulwich 0.22.8（BSD-3-Clause）、urllib3（MIT，dulwich≥0.22 的 HTTPS 传输
  依赖）；仓库体量小（sdist ≈ 466KB），无原生扩展。
- 证书/代理：urllib3 走系统/环境 SSL 上下文与 HTTP(S)_PROXY；真实私有 HTTPS 远端与
  自签证书场景**离线未验证**（无真实远端/证书门）。
- 认证/TLS 错误：system 侧按 stderr 特征分类、dulwich 侧按异常类型分类（本包以确定性
  unit 覆盖分类逻辑）；HTTP(S) 假远端矩阵因 dulwich 0.22 未提供 WSGI 服务端而未建，
  属未验证项（真机门）。
- PyInstaller：dulwich/urllib3 均为纯 Python（urllib3 含少量可选 C 加速，缺失时自动
  回退），hooks 无需手工收集；打包 smoke 与架构 wheel 验证属 P0-13。

## 实现

- 新增：`repositories/git_backend.py`、`repositories/system_git.py`、
  `repositories/dulwich_git.py`、`config/git_credentials.py`、`tests/unit/test_git_backends.py`、
  `tests/unit/test_git_credentials.py`；`git.py` 改为门面（API 不变，默认转发 system）；
  `domain/workspace.py::LocalProfile` 新增 `user_email`（可选，向后兼容）。
- pyproject 增加 `dulwich>=0.22,<0.23` 运行时依赖；mypy 对该无类型库模块局部放宽
  （no-untyped-call/no-any-return 等），其余 strict 保留。

## 验证

- 目标测试：conformance 双后端（本地历史/revert+冲突/revert 记录作者/语义一致）、
  远端 push→clone→fetch→ff、remote-missing/non-ff typed、PATH 为空下 dulwich 全链路、
  凭据 canary（secret 不进 URL/repr/异常）、profile_identity 邮箱与占位。
- 全量质量门：`git diff --check`、`ruff check .`、`ruff format --check .`、`mypy`
  （235 files）通过；`pytest`（665 passed，1 skipped：既有 `WB_PACKAGED_APP` 打包 smoke）。
- 全程使用临时仓库/临时目录与本地 bare remote；未访问真实远端、真实 Keychain、
  真实 `~/Documents/Work` 或打包 App。

## 遗留 / 边界

- 真实 HTTPS 远端（GitHub/GitLab）、代理、自签证书与 clean-account 打包运行属真机门
  （P0-13 前未验证）；本包用注入式 callback、脱敏错误与 CA bundle discovery 完成离线证据。
- remote clone 已由 `workflows/remote_onboarding.py` 提供 staging/confirm/cancel 服务；同步
  状态与全部共享 vault 写边界的显式 backend/context 接线留 P0-10C。

## P0-09C 收口

- `GitRepo` 支持每次调用显式传入 `backend_kind` 或注入 `GitBackend`；production 固定 helper
  返回 Dulwich，环境变量不参与该次调用的选择。
- `DulwichGitBackend` 的 clone/fetch/push 对 HTTPS 统一经 workspace id、host、username 的
  resolver 取得短生命周期凭据；不把密码写入 URL、磁盘、日志、异常或对象 repr。resolver
  异常统一降为脱敏 `GitAuthError`。
- remote onboarding 只接受 HTTPS 无 userinfo URL；clone staging 与目标同文件系统，marker、
  workspace id、当前 App compatibility 均在确认前校验；确认后 atomic move 并创建 secondary
  profile，失败/取消只清理本次 staging 并恢复 registry。
- `ca_bundle_path()` 现位于 `config/tls_trust.py`（`dulwich_git` re-export 兼容），可发现打包运行
  所需 CA 资源；PATH 为空时 Dulwich init/add/commit 已验证，未调用系统 Git。

## P0-09C 验证与边界

- 目标测试：`tests/unit/test_remote_onboarding.py` 11 项，联合既有 Git backend/credentials/
  packaging 测试共 28 passed。
- 全量质量门：ruff、format、mypy（243 files）通过；pytest（694 passed，1 skipped，跳过既有
  `WB_PACKAGED_APP` smoke）。真实私有 HTTPS、wrong credential/TLS 服务器、代理、clean-account
  与 Apple 签名/公证未执行，继续留在 P0-13 真机矩阵。

## P1-07D TLS 收口

- 打包 PyInstaller server 随 Python 分发的 OpenSSL，其编译期 `OPENSSLDIR` 指向 python.org
  框架路径（`/Library/Frameworks/...`），该路径既不存在也不随 bundle 分发；而 macOS 系统
  Keychain 无法被 OpenSSL 的 `set_default_verify_paths()` 读取。因此 dulwich/urllib3 默认的
  「系统 CA」在打包环境不可用，对 GitHub 报 `git_tls_failed`（系统 git 走 SecureTransport，
  因此不受影响）。
- 修复：`config/tls_trust.py` 提供 `ca_bundle_path()`（certifi → frozen
  `sys._MEIPASS/certifi/cacert.pem` → 系统 OpenSSL 默认路径）与 `configure_default_tls_trust()`
  （设 `SSL_CERT_FILE`）；`DulwichGitBackend.transport_kwargs` 通过 dulwich 的
  `default_urllib3_manager` + `http.sslCAInfo` 显式传入 CA bundle，`sslVerify=true` 保持 TLS
  校验开启；打包 server/worker 入口各调用一次 `configure_default_tls_trust()`。两个打包 spec
  均已收集 `(certifi.where(), "certifi")`。
- 分类边界保持：TLS 失败→`GitTlsError`、认证失败→`GitAuthError`、网络失败→
  `GitRemoteUnavailable`，绝不把 TLS 失败误报为离线/远端不可达；凭据不入 URL/日志/异常。
- 新增仅供集成测试调用的只读诊断：冻结 server 使用 `--tls-diagnostic`，worker 使用
  `WB_TLS_DIAGNOSTIC=1`，只返回 CA 来源/存在性、SSL context 校验模式和 Dulwich pool
  配置的布尔/枚举值，不输出路径或秘密。真实 PyInstaller server/worker 进程均已用该诊断
  证明 bundle CA 被找到、context 为 `CERT_REQUIRED` 且 HTTPS transport 实际使用该 CA。
