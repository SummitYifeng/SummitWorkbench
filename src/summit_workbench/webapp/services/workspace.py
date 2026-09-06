"""Workspace 相关 Web 应用服务。"""

from __future__ import annotations

from typing import Any

from summit_workbench.domain.workspace import Compatibility
from summit_workbench.repositories.git import GitRepo
from summit_workbench.workflows import workspace_migration


def migrate_workspace(context: Any, confirmed_device_id: str) -> Any:
    """在已注入的 active workspace 上执行 schema migration workflow。"""
    active = context.active_workspace
    if active is None or active.profile is None or active.device_id is None:
        raise ValueError("workspace_not_configured")
    if context.compatibility is Compatibility.CANNOT_OPEN:
        raise ValueError("workspace_not_configured")
    return workspace_migration.migrate_workspace(
        context.vault_dir,
        home=active.home,
        workspace_id=active.workspace_id,
        device_id=active.device_id,
        confirmed_device_id=confirmed_device_id,
        repo=GitRepo(
            context.vault_dir,
            backend_kind=context.git_backend_kind,
            workspace_id=active.workspace_id,
            username=active.profile.git_username,
        ),
    )


def migration_result_payload(result: Any) -> dict[str, object]:
    """Encode the stable migration response without exposing domain objects."""
    return {
        "ok": True,
        "status": result.status,
        "workspace_id": result.workspace_id,
        "from_version": result.from_version,
        "to_version": result.to_version,
        "backup_dir": str(result.backup_dir) if result.backup_dir is not None else None,
        "backup_manifest": (
            str(result.backup_manifest) if result.backup_manifest is not None else None
        ),
        "backup_snapshot": (
            str(result.backup_snapshot) if result.backup_snapshot is not None else None
        ),
    }


__all__ = ["migration_result_payload", "migrate_workspace"]
