# ADR 0030 · 可打包 Git 后端（system ↔ dulwich）与凭据适配

- 状态：🟡 部分完成（双 backend 与既有质量门全绿；HTTPS 凭据/remote clone/production 接线等待 P0-09C）
- 日期：2026-09-05
- 里程碑：v0.4.1 → P0-09（开发计划 PRODUCTIZATION_MULTI_DEVICE_DISTRIBUTION_PLAN；依赖 P0-01 撤销信任边界、P0-07 workspace/profile 与凭据作用域）
- 依据：计划 P0-09（能力契约 / 实现要求 1–8 / 测试矩阵 / 决策门）；NFR-3（非破坏性）、NFR-4（凭据不入文件/仓库）

> 2026-09-05 `bf734d8` 复核：system/dulwich conformance、typed errors 与 workspace-scoped 凭据模型已经实现；凭据尚未进入 Dulwich clone/fetch/push transport，production backend 仍由环境变量选择，clone staging/marker 确认与 packaged CA smoke 未完成。以计划 P0-09C 完成证据作为本 ADR 转为“已实现”的条件。

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
- 运行时选择：默认 `system`（开发/CLI 现状）；`WB_GIT_BACKEND=dulwich` 显式启用生产
  后端。打包/生产固定选 dulwich 的接线随 P0-10/P0-13 落地——本包以「契约 + conformance +
  PATH 为空证明」为离线验收，不宣称 clean Mac 已可用（真机门 P0-13）。

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

- 真实 HTTPS 远端（GitHub/GitLab）、证书校验、代理与 clean-account 打包运行属真机门
  （P0-13 前未验证）；生产运行固定选 dulwich 与凭据 callback 接线随 P0-10/P0-13。
- 新工作区的 git init/远端 clone 对业务的接入（onboarding/sync）随 P0-10 落地。
