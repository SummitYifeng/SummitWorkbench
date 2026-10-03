"""Per-app coordinator for local file mutations.

The profile-switch guard and per-workspace process lock remain here. File
synchronization is owned by the user's sync client and workspace Git is retired.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse

from summit_workbench.config.app_support import profile_dir
from summit_workbench.domain.sync import SyncSnapshot
from summit_workbench.webapp.context import WebContext
from summit_workbench.workflows.local_mutation import (
    LocalMutationOutcome,
    LocalMutationResult,
    MutationBlocked,
    run_local_mutation,
)


def _commit_suffix(ctx: WebContext, paths: Sequence[Path | str], summary: str) -> str:
    """Deprecated callsite shim. It intentionally performs no workspace Git action."""
    del ctx, paths, summary
    return ""


class MutationRuntime:
    """One instance per app; runs atomic local mutations under a workspace lock."""

    def __init__(self, context: WebContext, *, operation_id: Callable[[Request], str]) -> None:
        self._ctx = context
        self._operation_id = operation_id
        self._profile_switch_in_progress = False
        self._switch_condition = threading.Condition()
        self._active_mutations = 0

    @property
    def profile_switch_in_progress(self) -> bool:
        return self._profile_switch_in_progress

    def begin_profile_switch(self, *, timeout: float = 30.0) -> bool:
        """Stop admitting writes and wait for already-started local mutations to finish."""
        with self._switch_condition:
            self._profile_switch_in_progress = True
            completed = self._switch_condition.wait_for(
                lambda: self._active_mutations == 0,
                timeout=timeout,
            )
            if not completed:
                self._profile_switch_in_progress = False
                self._switch_condition.notify_all()
            return completed

    def end_profile_switch(self) -> None:
        with self._switch_condition:
            self._profile_switch_in_progress = False
            self._switch_condition.notify_all()

    def snapshot(self) -> SyncSnapshot:
        """Deprecated read-only compatibility hook for old diagnostics routes."""
        from summit_workbench.domain.sync import SyncState

        return SyncSnapshot(workspace_id=self._ctx.workspace_id or "", state=SyncState.UNCONFIGURED)

    def run[T](
        self, action: str, mutation: Callable[[str], LocalMutationOutcome[T]]
    ) -> LocalMutationResult[T]:
        with self._switch_condition:
            if self._profile_switch_in_progress:
                raise MutationBlocked("工作台正在切换，请等待本机服务重启后再修改")
            self._active_mutations += 1
        try:
            context = self._ctx.active_workspace
            lock_root = (
                profile_dir(self._ctx.workspace_id, context.home if context else None)
                if self._ctx.workspace_id
                else self._ctx.vault_dir.parent
            )
            return run_local_mutation(
                self._ctx.vault_dir,
                action,
                mutation,
                lock_root=lock_root,
            )
        finally:
            with self._switch_condition:
                self._active_mutations -= 1
                self._switch_condition.notify_all()

    def sync_blocked(self, request: Request) -> JSONResponse | None:
        """Legacy guard hook; external sync state no longer gates local writes."""
        del request
        return None

    def mutation_blocked(self, request: Request) -> JSONResponse | None:
        """Legacy guard hook; local file writes are independent of cloud sync state."""
        del request
        return None

    def commit_suffix(self, paths: Sequence[Path | str], summary: str) -> str:
        return _commit_suffix(self._ctx, paths, summary)
