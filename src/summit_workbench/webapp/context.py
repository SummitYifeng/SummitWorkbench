"""Web 应用运行时上下文。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from summit_workbench.config.profiles import ActiveWorkspaceContext
from summit_workbench.config.settings import default_config_file
from summit_workbench.domain.time import business_date
from summit_workbench.domain.workspace import Compatibility


@dataclass(frozen=True)
class WebContext:
    vault_dir: Path
    work_root: Path
    timezone: str
    # P0-06：工作区锁根（WorkspacePaths.lock_root）。None 时回退旧语义（env 默认）。
    lock_root: Path | None = None
    # P0-07C：production 由 active profile 冻结的运行时上下文。
    active_workspace: ActiveWorkspaceContext | None = None
    config_file: Path | None = None

    @classmethod
    def from_active_workspace(cls, context: ActiveWorkspaceContext) -> WebContext | None:
        if context.paths is None or context.profile is None or not context.can_read:
            return None
        return cls(
            vault_dir=context.paths.vault_dir,
            work_root=context.paths.work_root,
            timezone=context.timezone,
            lock_root=context.paths.lock_root,
            active_workspace=context,
            config_file=context.config_file,
        )

    def provider_config_file(self) -> Path:
        return self.config_file or default_config_file()

    @property
    def workspace_id(self) -> str | None:
        return self.active_workspace.workspace_id if self.active_workspace else None

    @property
    def compatibility(self) -> Compatibility:
        if self.active_workspace and self.active_workspace.compatibility is not None:
            return self.active_workspace.compatibility
        return Compatibility.READ_WRITE

    def today(self) -> str:
        return business_date(datetime.now(UTC))

    @property
    def git_backend_kind(self) -> str | None:
        """production active profile 固定 Dulwich；旧兼容 context 不覆盖默认 backend。"""
        return "dulwich" if self.active_workspace is not None else None


__all__ = ["WebContext"]
