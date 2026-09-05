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

from summit_workbench.config.paths import WorkspacePaths, resolve_work_paths
from summit_workbench.domain.workspace import LocalProfile
from summit_workbench.repositories.profile_registry import (
    active_profile_id,
    load_profile,
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
