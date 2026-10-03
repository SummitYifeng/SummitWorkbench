"""active workspace 单一解析入口（P0-07）。

:func:`resolve_workspace` 是本包起**核心业务路径的来源**：先读本机 registry 的
active profile（权威），否则退回 development/test 的 ``WORK_ROOT`` env 兼容，
两者都没有时返回 ``onboarding-required``——**绝不**静默创建 ``~/Documents/Work``
或任何目录（空安装行为，§0.1 / P0-07 要求 7）。

解析本身是纯读操作：不创建 Application Support 目录、不写 registry。
现有 CLI/launchd 在 P0-08 onboarding 落地前继续经 ``WORK_ROOT`` env 兼容路径运行；
P0-08 之后各入口逐步切换到本解析入口取 profile/WorkspacePaths。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from summit_workbench import __version__
from summit_workbench.config.app_support import (
    app_support_dir,
    home_dir,
    profile_config_file,
)
from summit_workbench.config.paths import WorkspacePaths, resolve_work_paths
from summit_workbench.domain.workspace import (
    Compatibility,
    LocalProfile,
    evaluate_manifest_compatibility,
)
from summit_workbench.repositories.profile_registry import (
    active_profile_id,
    ensure_device_identity,
    load_profile,
)
from summit_workbench.repositories.workspace_contract import load_contract_manifest
from summit_workbench.repositories.workspace_manifest import (
    WorkspaceManifestError,
    load_workspace_manifest,
)


class ProfileResolutionState(StrEnum):
    """解析结果三态。"""

    ACTIVE = "active"  # registry active profile 命中（生产形态）
    ENV_COMPAT = "env-compat"  # 无 profile，退回 WORK_ROOT env（development/test）
    ONBOARDING_REQUIRED = "onboarding-required"  # 空安装：需要新建/连接工作区


@dataclass(frozen=True)
class WorkspaceResolution:
    """一次解析的完整结果：状态 +（可选的）profile 与派生路径。"""

    state: ProfileResolutionState
    profile: LocalProfile | None = None
    paths: WorkspacePaths | None = None
    reason: str = ""


@dataclass(frozen=True)
class ActiveWorkspaceContext:
    """已经完成一次 active-profile 解析的 production 运行时上下文。

    业务入口只应消费这个对象，而不是再次读取全局 settings、HOME 或 WORK_ROOT。
    ``profile``/``paths`` 在 onboarding-required 时为空；该形态只允许受限控制面使用。
    """

    resolution: WorkspaceResolution
    profile: LocalProfile | None
    paths: WorkspacePaths | None
    workspace_id: str | None
    device_id: str | None
    compatibility: Compatibility | None
    home: Path
    application_support: Path
    config_file: Path | None
    timezone: str = "Asia/Shanghai"

    @property
    def is_onboarding_required(self) -> bool:
        return self.resolution.state is ProfileResolutionState.ONBOARDING_REQUIRED

    @property
    def can_read(self) -> bool:
        return self.compatibility in {
            Compatibility.READ_WRITE,
            Compatibility.READ_ONLY_UPGRADE_REQUIRED,
        }

    @property
    def can_write(self) -> bool:
        return self.compatibility is Compatibility.READ_WRITE

    @property
    def runtime_dir(self) -> Path | None:
        if self.profile is None:
            return None
        from summit_workbench.config.app_support import runtime_dir

        return runtime_dir(self.profile.workspace_id, home=self.home)


def resolve_workspace(
    home: Path | None = None,
    *,
    allow_env_fallback: bool = True,
) -> WorkspaceResolution:
    """解析当前 active workspace。

    :param home: 本机 home（默认 :func:`~summit_workbench.config.app_support.home_dir`），
        测试传临时 home 隔离。
    :param allow_env_fallback: 是否允许无 profile 时退回 ``WORK_ROOT`` env
        （development/test 覆盖；production 语义应传 False）。
    :returns: :class:`WorkspaceResolution`——state 为 ACTIVE 时携带 profile 与
        ``WorkspacePaths``（work_root/vault_dir/lock_root，P0-06 单一规则）。
    """
    profile_id = active_profile_id(home=home)
    if profile_id is not None:
        profile = load_profile(profile_id, home=home)
        if profile is not None:
            paths = resolve_work_paths(work_root=profile.work_root, vault_dir=profile.vault_dir)
            return WorkspaceResolution(
                state=ProfileResolutionState.ACTIVE,
                profile=profile,
                paths=paths,
                reason=f"active workspace：{profile.workspace_id}",
            )

    env_root = os.environ.get("WORK_ROOT")
    if allow_env_fallback and env_root:
        paths = resolve_work_paths(work_root=env_root)
        return WorkspaceResolution(
            state=ProfileResolutionState.ENV_COMPAT,
            paths=paths,
            reason="未建档，使用 WORK_ROOT 环境变量（仅 development/test 兼容）",
        )

    return WorkspaceResolution(
        state=ProfileResolutionState.ONBOARDING_REQUIRED,
        reason="尚未创建或连接任何工作区：请先完成 onboarding（P0-08）",
    )


def resolve_active_workspace(
    home: Path | None = None,
    *,
    allow_env_fallback: bool = False,
    app_version: str | None = None,
) -> ActiveWorkspaceContext:
    """解析并冻结当前运行时上下文。

    Production 默认禁止 ``WORK_ROOT`` 回退。active profile 存在时会读取 vault marker
    并计算 compatibility；marker 缺失、损坏或 workspace id 不匹配均进入 cannot-open，
    不会猜测身份。首次为已有 active profile 建立 device identity 是安装级本地初始化，
    不会触碰 vault 或默认工作目录。
    """
    resolved_home = (home or home_dir()).expanduser()
    resolution = resolve_workspace(
        home=resolved_home,
        allow_env_fallback=allow_env_fallback,
    )
    if resolution.state is not ProfileResolutionState.ACTIVE or resolution.profile is None:
        return ActiveWorkspaceContext(
            resolution=resolution,
            profile=resolution.profile,
            paths=resolution.paths,
            workspace_id=None,
            device_id=None,
            compatibility=Compatibility.READ_WRITE if resolution.paths is not None else None,
            home=resolved_home,
            application_support=app_support_dir(resolved_home),
            config_file=None,
            timezone="Asia/Shanghai",
        )

    profile = resolution.profile
    paths = resolution.paths
    assert paths is not None
    device = ensure_device_identity(home=resolved_home)
    compatibility = Compatibility.CANNOT_OPEN
    reason = resolution.reason
    try:
        manifest = load_workspace_manifest(paths.vault_dir)
    except WorkspaceManifestError as exc:
        manifest = None
        reason = str(exc)
    try:
        portable = load_contract_manifest(paths.vault_dir)
    except ValueError as exc:
        portable = None
        reason = str(exc)
    if manifest is None:
        reason = reason or "active profile 对应 vault 缺少 workspace marker"
    elif manifest.workspace_id != profile.workspace_id:
        reason = "active profile 与 vault workspace marker 不一致"
    elif portable is None:
        reason = reason or "active profile 对应 vault 缺少兼容的 SWB 工作库契约"
    elif portable.workspace_id != profile.workspace_id:
        reason = "active profile 与便携工作库契约身份不一致"
    else:
        legacy_compatibility = evaluate_manifest_compatibility(manifest, app_version or __version__)
        if legacy_compatibility is Compatibility.READ_WRITE:
            compatibility = Compatibility.READ_WRITE
        else:
            compatibility = Compatibility.CANNOT_OPEN
            reason = "工作库版本不兼容；请升级应用或显式重新连接工作库"

    resolved = WorkspaceResolution(
        state=resolution.state,
        profile=profile,
        paths=paths,
        reason=reason,
    )
    return ActiveWorkspaceContext(
        resolution=resolved,
        profile=profile,
        paths=paths,
        workspace_id=profile.workspace_id,
        device_id=device.device_id,
        compatibility=compatibility,
        home=resolved_home,
        application_support=app_support_dir(resolved_home),
        config_file=profile_config_file(profile.workspace_id, home=resolved_home),
        timezone=profile.timezone,
    )


# Descriptive alias for callers that want to make the production-only policy explicit.
resolve_active_context = resolve_active_workspace
