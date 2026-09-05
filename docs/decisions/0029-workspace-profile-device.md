# ADR 0029 · Workspace / Profile / Device 领域与存储

- 状态：✅ 已实现（P0-07C 已完成离线 production 接线；真实 App/Keychain 真机门未执行）
- 日期：2026-09-05
- 里程碑：v0.4.1 → P0-07（开发计划 PRODUCTIZATION_MULTI_DEVICE_DISTRIBUTION_PLAN；承接 P0-06 WorkspacePaths/原子写/锁根统一）
- 依据：计划 §2.1（产品边界）、§2.3（数据落点）、§2.4（工作区兼容契约）、P0-07 工作包（领域模型/实现要求 1–8/测试矩阵）；NFR-3（不硬编码路径）、NFR-4（凭据不入文件/仓库）

> 2026-09-05 `bf734d8` 复核：领域模型、registry、Application Support 与解析三态已经实现；production Web/server/doctor/provider 尚未统一消费 active workspace context，兼容性写门和 LocalProfile 未知字段往返也需收口。以计划 P0-07C 完成证据作为本 ADR 转为“已实现”的条件。

## 背景与问题

产品仍默认「一位使用者、一台电脑、一个固定目录」：没有稳定 workspace 身份（P0-04 只用
vault 容器路径的 legacy 摘要）、没有本机安装级 device id、没有「active profile」概念，
路径全部来自 ``WORK_ROOT`` env 或默认 ``~/Documents/Work``。这无法支撑 Mac Studio + Air
双设备、同事独立工作区以及「App 低于 min 版本只读保护」的兼容门。

## 决策

### 1. 三个身份各归其位（领域模型 `domain/workspace.py`）

- **WorkspaceManifest**（vault 内 ``.summit-workbench/workspace.json``，随 Git 同步）：
  schema_version=1、workspace_id（UUID v4，创建后不可改）、display_name、created_at、
  min_reader_version、min_writer_version。未知字段容忍并随 model_dump 保留
  （前向兼容，重写不丢字段）；绝不携带 device id、本机绝对路径或秘密。
- **LocalProfile**（``~/Library/Application Support/SummitWorkbench/profiles/<id>/config.toml``，
  不同步）：workspace_id、display_name、本机 work_root/vault_dir、device_role、
  created_at/last_opened_at。provider 非秘密配置由 P0-08 onboarding 并入同一文件。
- **DeviceIdentity**（``device.json``，不同步）：device_id（UUID v4）首次运行生成一次，
  App 升级/重签名/移动路径都不变；device_name、created_at。device id/本机路径永不经 Git 同步。

### 2. 存储布局与权限（`config/app_support.py` + `repositories/profile_registry.py`）

- registry.json **只存** profile id 索引与 active workspace id；profile 详情独立存放。
- 本机文件一律 0600、目录 0700（测试兼容 umask，chmod 补足）；写入全部走 P0-06 原子原语
  （`_atomic.atomic_write_text(..., new_mode=0o600)`：唯一临时文件 + fsync + replace）。
- profile 配置用扁平 TOML（字段顺序稳定、人类可编辑、与 §2.3 布局一致）。

### 3. active workspace 单一解析入口（`config/profiles.py`）

`resolve_workspace()` 三态：
- registry active profile 命中 → `active`（携带 LocalProfile + WorkspacePaths；
  lock_root = vault 容器，P0-06 规则）；
- 无 profile 但设了 ``WORK_ROOT`` → `env-compat`（**仅 development/test 兼容**）；
- 都没有 → `onboarding-required`，**绝不**静默创建 ``~/Documents/Work`` 或任何目录
  （解析是纯读，不建 Application Support）。

阶段化落地：P0-08 onboarding 完成前，现有 CLI/launchd 继续走 env-compat；P0-07C 已将
production Web/server/doctor/status/brief/provider 接线切换到冻结的 active context，仍保留
显式 development/test env-compat。固定 home 路径只剩兼容代码与测试。

### 4. schema / 版本兼容门（Compatibility）

`evaluate_manifest_compatibility(manifest, app_version)`（正式发布位比较，忽略预发布后缀）：
- schema_version 为 1：``app < min_reader_version`` → `cannot-open`；
  ``app < min_writer_version`` → `read-only-upgrade-required`；否则 `read-write`。
- schema_version 更高（未来整数版本）→ `read-only-upgrade-required`（只读保护，不猜字段，§2.4）；
- schema_version ≤ 0 / 非数 → `cannot-open`。
- 无 marker 的旧 vault → manifest None，只能经 P0-08「升级现有工作区」显式生成。

### 5. 凭据 workspace 作用域（`config/secrets.py`）

Keychain service = ``com.summitworkbench.credentials.<workspace_id>``，account =
``llm:<provider>:<name>`` / ``feishu:<app_id>:app_secret|refresh_token`` /
``git:<host>:<username>``。新 API（`workspace_credential_ref/resolve/store_workspace_credential`）
只操作作用域命名；旧命名读取只经显式迁移入口 `resolve_legacy_credential_for_migration`，
普通读取不回退旧命名、新代码不写旧命名。provider 实际接线由 P0-07C 完成，onboarding 负责写入对应 profile 的非秘密配置。

### 6. outbox 工作区 id 升级

`workspace_id_for_vault`：有 marker 优先用 canonical workspace_id（跨设备稳定）；
无/损坏 marker 回退 legacy 摘要（P0-04 兼容），P0-08 升级后自然收敛。

## 实现

- 新增：`domain/workspace.py`、`config/app_support.py`、`config/profiles.py`、
  `repositories/profile_registry.py`、`repositories/workspace_manifest.py`；
  扩展 `config/secrets.py`（作用域凭据）、`repositories/_atomic.py`（`new_mode` 参数）；
  修改 `workflows/external_actions.py::workspace_id_for_vault`。
- 新增测试 46 项：领域模型/兼容映射（旧/新/未知 schema）、App Support 布局、
  device id 首生成后稳定/两模拟 Home 不同、registry+profile 原子写与 0600/0700 权限、
  两 workspace profile/凭据互不污染、marker 跨设备同 id/未知字段不回丢/损坏可见、
  解析三态（active > env-compat > onboarding-required，空安装不触真实目录）、
  凭据作用域隔离与显式迁移。

## 验证

- 全量质量门：`git diff --check`、`ruff check .`、`ruff format --check .`、`mypy`（225 files）
  通过；`pytest`（632 passed，1 skipped：既有需 `WB_PACKAGED_APP` 的打包 smoke）。
- 全程使用临时 HOME/临时目录与 fake Keychain，未访问真实 `~/Documents/Work`、真实
  Keychain、真实飞书或模型。

## P0-07C 收口

`ActiveWorkspaceContext` 是 production 入口的唯一运行时上下文：它一次性解析 active
profile，派生 `WorkspacePaths`、profile config、workspace/device id，并读取 marker 计算
`read-write`、`read-only-upgrade-required` 或 `cannot-open`。打包 server 与 `wb web` 使用
`allow_env_fallback=False`；没有 active profile 时不创建旧的 `~/Documents/Work`，只提供版本、
onboarding 与脱敏诊断所需的受限控制面。development/test 仍可显式使用 `WORK_ROOT` 兼容态。

Web、doctor、status、brief runner 和 Feishu/LLM 配置都从冻结上下文取得路径、配置文件和
workspace-scoped credential refs；旧全局 Keychain 命名没有静默回退。Web unsafe route 在
compatibility 门控下统一拒绝写入，read-only 仍可浏览；profile TOML 的未知字段以 TOML
扩展表形式保留，避免读写丢字段。

## 验证与边界

- 新增 `test_active_profile_runtime.py`：覆盖 active context、空安装、未知字段往返、provider
  作用域与 schema compatibility/restricted control plane。
- 全量质量门：ruff、format、mypy（241 files）通过；pytest（682 passed，1 skipped，既有
  `WB_PACKAGED_APP` 条件打包 smoke）。
- 离线 fake/临时 HOME 验证通过；真实 Keychain、真实 HTTPS remote、clean-account、第二台
  Mac 与 Apple 签名/notarization 未执行，不能视为真机门通过。

## P0-11B 设置中心收口

设置中心复用本 ADR 的 active profile、路径与 workspace-scoped credential 契约：profile 列表只向 UI
暴露当前 profile 的绝对路径，其它 profile 仅显示目录名；provider 非秘密配置写回对应本机 profile，
secret 只通过 `store_workspace_credential` 写入 workspace-scoped Keychain，不写入 TOML 或响应。profile
切换使用 prepare/commit 计划，目标 compatibility 在 prepare 与 commit 双重校验，commit 只更新本机
registry 并要求原生壳重启，从而重新建立目标 workspace/session；切换期间共享 vault mutation 被拒绝。
默认移除只清理本机 profile/runtime/draft，vault、remote 和 Keychain 均保持不变。doctor 复用既有领域
检查，默认离线，在线检查须由用户明确确认。

验证：`tests/unit/test_profile_settings.py` 与 Web 安全/应用回归通过；全量 pytest `715 passed,
1 skipped`，mypy 252 files，前端 build/verify-build 通过。真实 Keychain、App 黑盒与第二台 Mac 未执行。
