# ADR 0029 · Workspace / Profile / Device 领域与存储

- 状态：🟡 部分完成（基础实现与既有质量门全绿；production active-profile 接线等待 P0-07C）
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

阶段化落地：P0-08 onboarding 完成前，现有 CLI/launchd 继续走 env-compat；P0-08 后各
入口逐步切换到本解析入口。固定 home 路径只剩兼容代码与测试。

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
普通读取不回退旧命名、新代码不写旧命名。provider 实际接线留 P0-08（拿到 active profile 后切换）。

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

## 遗留 / 边界

- onboarding 服务与 API（create/upgrade/connect）属 P0-08；provider 凭据接线、
  production 全面切换解析入口、doctor/status 展示 onboarding-required 随 P0-08/P0-12 落地。
- 打包 App 的真实 Application Support 路径与重签名稳定性属 P0-13 真机门。
