"""分叉详情提取与受保护的 P2-02 恢复准备/写回。

此模块只读取已 fetch 的本地 refs，并对两个提交树做比较。它不 fetch、merge、checkout、
替换工作树，也不在详情/预检阶段创建提交；实际写回必须经过显式确认和快照校验。
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import tempfile
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from summit_workbench.config.locking import LockBusy, workspace_lock
from summit_workbench.domain.sync import SyncState
from summit_workbench.domain.sync_conflict import (
    ConflictAction,
    ConflictKind,
    ConflictRecoveryPlan,
    classify_conflict_path,
)
from summit_workbench.domain.thread_activity import ThreadActivityEvent, render_thread_activity_view
from summit_workbench.repositories._atomic import atomic_write_bytes
from summit_workbench.repositories.git import GitError, GitRepo
from summit_workbench.repositories.git_backend import CommitIdentity, default_identity
from summit_workbench.repositories.thread_activity_events import ThreadActivityEventStore

RecoverySide = Literal["local", "remote"]
RECOVERY_AUDIT_PATH = "_signals/sync-conflict-recovery/log.jsonl"


class SelectionChoice(StrEnum):
    KEEP_LOCAL = "keep-local"
    KEEP_REMOTE = "keep-remote"
    PRESERVE_BOTH = "preserve-both"


@dataclass(frozen=True)
class ConflictSide:
    side: RecoverySide
    revision: str
    authored_at: str
    changed_path_count: int

    def as_dict(self) -> dict[str, object]:
        return {
            "side": self.side,
            "revision": self.revision,
            "authored_at": self.authored_at,
            "changed_path_count": self.changed_path_count,
        }


@dataclass(frozen=True)
class ConflictPathDetail:
    path: str
    kind: ConflictKind
    action: ConflictAction
    automatic: bool
    changed_on: tuple[RecoverySide, ...]
    local_sha256: str | None
    remote_sha256: str | None
    local_event: dict[str, str] | None = None
    remote_event: dict[str, str] | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "kind": self.kind.value,
            "action": self.action.value,
            "automatic": self.automatic,
            "changed_on": list(self.changed_on),
            "local_sha256": self.local_sha256,
            "remote_sha256": self.remote_sha256,
            "local_event": self.local_event,
            "remote_event": self.remote_event,
        }


@dataclass(frozen=True)
class DivergenceDetails:
    base_revision: str
    local: ConflictSide
    remote: ConflictSide
    paths: tuple[ConflictPathDetail, ...]

    @property
    def automatic_path_count(self) -> int:
        return sum(path.automatic for path in self.paths)

    @property
    def manual_path_count(self) -> int:
        return sum(not path.automatic for path in self.paths)

    def as_dict(self) -> dict[str, object]:
        return {
            "base_revision": self.base_revision,
            "local": self.local.as_dict(),
            "remote": self.remote.as_dict(),
            "automatic_path_count": self.automatic_path_count,
            "manual_path_count": self.manual_path_count,
            "paths": [path.as_dict() for path in self.paths],
        }


@dataclass(frozen=True)
class TemporaryValidation:
    """Result of validating automatic items in an ephemeral staging directory."""

    status: str
    event_count: int = 0
    aggregate_count: int = 0
    generated_view_count: int = 0
    rebuilt_view_count: int = 0
    error_code: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "ok": self.status == "validated",
            "event_count": self.event_count,
            "aggregate_count": self.aggregate_count,
            "generated_view_count": self.generated_view_count,
            "rebuilt_view_count": self.rebuilt_view_count,
            "error_code": self.error_code,
        }


@dataclass
class RecoveryPreparation:
    """A snapshot-bound staging result owned by the caller's context manager."""

    status: str
    base_revision: str | None = None
    local_revision: str | None = None
    remote_revision: str | None = None
    event_count: int = 0
    aggregate_count: int = 0
    generated_view_count: int = 0
    rebuilt_view_count: int = 0
    error_code: str | None = None
    staging_dir: Path | None = None
    candidate_paths: tuple[str, ...] = ()
    selection_summary: tuple[tuple[str, str], ...] = ()
    _temporary: tempfile.TemporaryDirectory[str] | None = field(
        default=None, repr=False, compare=False
    )

    @property
    def ready(self) -> bool:
        return self.status == "validated" and self.staging_dir is not None

    def as_dict(self) -> dict[str, object]:
        """Return a safe summary without exposing the temporary absolute path."""
        return {
            "status": self.status,
            "ok": self.ready,
            "base_revision": self.base_revision,
            "local_revision": self.local_revision,
            "remote_revision": self.remote_revision,
            "event_count": self.event_count,
            "aggregate_count": self.aggregate_count,
            "generated_view_count": self.generated_view_count,
            "rebuilt_view_count": self.rebuilt_view_count,
            "candidate_path_count": len(self.candidate_paths),
            "staging_ready": self.staging_dir is not None,
            "error_code": self.error_code,
        }

    def close(self) -> None:
        """Delete the ephemeral staging directory and release its ownership."""
        if self._temporary is not None:
            self._temporary.cleanup()
            self._temporary = None
            self.staging_dir = None

    def __enter__(self) -> RecoveryPreparation:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


@dataclass(frozen=True)
class SelectionValidation:
    """Preflight result for explicit human choices; it never changes the vault."""

    status: str
    missing_paths: tuple[str, ...] = ()
    unexpected_paths: tuple[str, ...] = ()
    invalid_paths: tuple[str, ...] = ()
    error_code: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "ok": self.status == "validated",
            "missing_paths": list(self.missing_paths),
            "unexpected_paths": list(self.unexpected_paths),
            "invalid_paths": list(self.invalid_paths),
            "error_code": self.error_code,
        }


@dataclass(frozen=True)
class RecoveryApplyResult:
    """Result of an explicitly confirmed local recovery commit."""

    status: str
    revision: str | None = None
    applied_paths: tuple[str, ...] = ()
    error_code: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "ok": self.status == "committed",
            "revision": self.revision,
            "applied_paths": list(self.applied_paths),
            "error_code": self.error_code,
        }


def _digest(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def _event_identifiers(data: bytes | None) -> dict[str, str] | None:
    if data is None:
        return None
    try:
        event = ThreadActivityEvent.model_validate(json.loads(data.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return {"parse_status": "invalid-event"}
    return {
        "event_id": event.event_id,
        "workspace_id": event.workspace_id,
        "device_id": event.device_id,
        "occurred_at": event.occurred_at.isoformat(),
        "kind": event.kind,
        "aggregate_id": event.aggregate_id,
        "causation_operation_id": event.causation_operation_id,
    }


def _safe_paths(paths: tuple[str, ...] | None) -> set[str] | None:
    if paths is None:
        return None
    safe: set[str] = set()
    for path in paths:
        safe.add(classify_conflict_path(path).path)
    return safe


def inspect_divergence(
    vault_dir: Path,
    *,
    backend_kind: str | None = None,
    workspace_id: str | None = None,
    paths: tuple[str, ...] | None = None,
) -> DivergenceDetails:
    """Read local/upstream tree metadata for a previously fetched divergence."""
    repo = GitRepo(vault_dir, backend_kind=backend_kind, workspace_id=workspace_id)
    if not repo.is_git_repo() or not repo.has_upstream():
        raise GitError("当前仓库没有可读取的 upstream 分叉")
    local_revision = repo.head_revision()
    remote_revision = repo.upstream_revision()
    base_revision = repo.merge_base(local_revision, remote_revision)
    local_paths = set(repo.files_changed_between(base_revision, local_revision))
    remote_paths = set(repo.files_changed_between(base_revision, remote_revision))
    selected = _safe_paths(paths)
    changed_paths = sorted(
        (local_paths | remote_paths)
        if selected is None
        else (local_paths | remote_paths) & selected
    )

    local_meta = repo.commit_metadata(local_revision)
    remote_meta = repo.commit_metadata(remote_revision)
    path_details: list[ConflictPathDetail] = []
    for path in changed_paths:
        item = classify_conflict_path(path)
        local_data = repo.read_file_at(local_revision, path) if path in local_paths else None
        remote_data = repo.read_file_at(remote_revision, path) if path in remote_paths else None
        changed_on: list[RecoverySide] = []
        if path in local_paths:
            changed_on.append("local")
        if path in remote_paths:
            changed_on.append("remote")
        path_details.append(
            ConflictPathDetail(
                path=item.path,
                kind=item.kind,
                action=item.action,
                automatic=item.automatic,
                changed_on=tuple(changed_on),
                local_sha256=_digest(local_data),
                remote_sha256=_digest(remote_data),
                local_event=_event_identifiers(local_data)
                if item.kind is ConflictKind.APPEND_ONLY_EVENT
                else None,
                remote_event=_event_identifiers(remote_data)
                if item.kind is ConflictKind.APPEND_ONLY_EVENT
                else None,
            )
        )
    return DivergenceDetails(
        base_revision=base_revision,
        local=ConflictSide("local", local_meta.revision, local_meta.authored_at, len(local_paths)),
        remote=ConflictSide(
            "remote", remote_meta.revision, remote_meta.authored_at, len(remote_paths)
        ),
        paths=tuple(path_details),
    )


def _copy_regular_files(
    source: Path, destination: Path, *, excluded_top_level: frozenset[str] = frozenset()
) -> None:
    """Copy only regular event files; symlinks never enter the staging area."""
    if not source.is_dir():
        return
    for path in source.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(source)
        if relative.parts and relative.parts[0] in excluded_top_level:
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


def _snapshot_matches(repo: GitRepo, details: DivergenceDetails) -> bool:
    try:
        local_revision = repo.head_revision()
        remote_revision = repo.upstream_revision()
        base_revision = repo.merge_base(local_revision, remote_revision)
    except GitError:
        return False
    return (
        local_revision == details.local.revision
        and remote_revision == details.remote.revision
        and base_revision == details.base_revision
    )


def prepare_automatic_recovery(
    vault_dir: Path,
    details: DivergenceDetails,
    *,
    workspace_id: str,
    backend_kind: str | None = None,
) -> RecoveryPreparation:
    """Prepare automatic items in a snapshot-bound ephemeral staging area.

    The returned object owns a temporary directory until ``close`` or context-manager
    exit. It contains no ``.git`` directory and never changes the source repository.
    Only append-only events and the defined thread activity view are prepared. Unknown
    generated views are manual items and must be preserved as explicit ``.remote`` copies.
    """
    if details.manual_path_count:
        return RecoveryPreparation(
            status="manual-confirmation-required",
            base_revision=details.base_revision,
            local_revision=details.local.revision,
            remote_revision=details.remote.revision,
            error_code="manual_items",
        )
    repo = GitRepo(vault_dir, backend_kind=backend_kind, workspace_id=workspace_id)
    if not _snapshot_matches(repo, details):
        return RecoveryPreparation(
            status="stale",
            base_revision=details.base_revision,
            local_revision=details.local.revision,
            remote_revision=details.remote.revision,
            error_code="conflict_snapshot_stale",
        )
    if repo.is_dirty():
        return RecoveryPreparation(
            status="rejected",
            base_revision=details.base_revision,
            local_revision=details.local.revision,
            remote_revision=details.remote.revision,
            error_code="current_worktree_dirty",
        )
    event_paths = tuple(
        path for path in details.paths if path.kind is ConflictKind.APPEND_ONLY_EVENT
    )
    generated_view_items = tuple(
        path for path in details.paths if path.kind is ConflictKind.GENERATED_VIEW
    )
    generated_views = len(generated_view_items)
    rebuildable_views = tuple(
        path for path in generated_view_items if path.path == "_views/thread-activity.json"
    )
    candidate_paths = {
        path.path
        for path in event_paths
        if "remote" in path.changed_on and "local" not in path.changed_on
    }
    candidate_paths.update(path.path for path in rebuildable_views)
    temporary = tempfile.TemporaryDirectory(prefix=".summit-workbench-recovery-")
    staging = Path(temporary.name)
    try:
        _copy_regular_files(vault_dir / "_events", staging / "_events")
        for path in event_paths:
            if len(path.changed_on) == 2 and path.local_sha256 != path.remote_sha256:
                temporary.cleanup()
                return RecoveryPreparation(
                    status="rejected",
                    base_revision=details.base_revision,
                    local_revision=details.local.revision,
                    remote_revision=details.remote.revision,
                    generated_view_count=generated_views,
                    error_code="event_path_collision",
                )
            if "remote" in path.changed_on and "local" not in path.changed_on:
                data = repo.read_file_at(details.remote.revision, path.path)
                if data is None:
                    temporary.cleanup()
                    return RecoveryPreparation(
                        status="rejected",
                        base_revision=details.base_revision,
                        local_revision=details.local.revision,
                        remote_revision=details.remote.revision,
                        generated_view_count=generated_views,
                        error_code="remote_event_missing",
                    )
                target = staging / path.path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        store = ThreadActivityEventStore(
            staging,
            workspace_id=workspace_id,
            device_id="recovery-validation",
        )
        events = store.read_workspace_events()
        projection = store.project_workspace()
    except Exception:  # noqa: BLE001 - safe visible validation result
        temporary.cleanup()
        return RecoveryPreparation(
            status="projection-failed",
            base_revision=details.base_revision,
            local_revision=details.local.revision,
            remote_revision=details.remote.revision,
            generated_view_count=generated_views,
            error_code="event_projection_failed",
        )
    if rebuildable_views:
        target = staging / "_views" / "thread-activity.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(render_thread_activity_view(projection))
    return RecoveryPreparation(
        status="validated",
        base_revision=details.base_revision,
        local_revision=details.local.revision,
        remote_revision=details.remote.revision,
        event_count=len(events),
        aggregate_count=len(projection),
        generated_view_count=generated_views,
        rebuilt_view_count=len(rebuildable_views),
        staging_dir=staging,
        candidate_paths=tuple(sorted(candidate_paths)),
        _temporary=temporary,
    )


def validate_automatic_recovery(
    vault_dir: Path,
    details: DivergenceDetails,
    *,
    workspace_id: str,
    backend_kind: str | None = None,
) -> TemporaryValidation:
    """Validate automatic recovery and clean its staging area before returning."""
    prepared = prepare_automatic_recovery(
        vault_dir,
        details,
        workspace_id=workspace_id,
        backend_kind=backend_kind,
    )
    try:
        return TemporaryValidation(
            status=prepared.status,
            event_count=prepared.event_count,
            aggregate_count=prepared.aggregate_count,
            generated_view_count=prepared.generated_view_count,
            rebuilt_view_count=prepared.rebuilt_view_count,
            error_code=prepared.error_code,
        )
    finally:
        prepared.close()


def prepare_manual_recovery(
    vault_dir: Path,
    details: DivergenceDetails,
    *,
    workspace_id: str,
    selections: Mapping[str, SelectionChoice | str],
    backend_kind: str | None = None,
) -> RecoveryPreparation:
    """Prepare a complete human-selected candidate tree without writing the vault.

    The candidate starts from the clean local worktree. ``keep-remote`` replaces
    one selected path from the fetched remote revision; ``preserve-both`` keeps
    the local path and writes the remote bytes to a deterministic ``.remote``
    sibling. Unknown generated views are restricted to ``preserve-both`` because
    they have no registered deterministic rebuild procedure. Automatic event collection
    and the defined view rebuild use the same rules as :func:`prepare_automatic_recovery`.
    """
    selection = validate_manual_selections(
        details,
        base_revision=details.base_revision,
        local_revision=details.local.revision,
        remote_revision=details.remote.revision,
        selections=selections,
    )
    if selection.status != "validated":
        return RecoveryPreparation(
            status=selection.status,
            base_revision=details.base_revision,
            local_revision=details.local.revision,
            remote_revision=details.remote.revision,
            error_code=selection.error_code,
        )
    repo = GitRepo(vault_dir, backend_kind=backend_kind, workspace_id=workspace_id)
    if not _snapshot_matches(repo, details):
        return RecoveryPreparation(
            status="stale",
            base_revision=details.base_revision,
            local_revision=details.local.revision,
            remote_revision=details.remote.revision,
            error_code="conflict_snapshot_stale",
        )
    if repo.is_dirty():
        return RecoveryPreparation(
            status="rejected",
            base_revision=details.base_revision,
            local_revision=details.local.revision,
            remote_revision=details.remote.revision,
            error_code="current_worktree_dirty",
        )

    event_paths = tuple(
        path for path in details.paths if path.kind is ConflictKind.APPEND_ONLY_EVENT
    )
    generated_view_items = tuple(
        path for path in details.paths if path.kind is ConflictKind.GENERATED_VIEW
    )
    generated_views = len(generated_view_items)
    rebuildable_views = tuple(
        path for path in generated_view_items if path.path == "_views/thread-activity.json"
    )
    candidate_paths = {
        path.path
        for path in event_paths
        if "remote" in path.changed_on and "local" not in path.changed_on
    }
    temporary = tempfile.TemporaryDirectory(prefix=".summit-workbench-recovery-")
    staging = Path(temporary.name)
    try:
        _copy_regular_files(vault_dir, staging, excluded_top_level=frozenset({".git"}))
        for path in event_paths:
            if len(path.changed_on) == 2 and path.local_sha256 != path.remote_sha256:
                raise ValueError("event_path_collision")
            if "remote" in path.changed_on and "local" not in path.changed_on:
                data = repo.read_file_at(details.remote.revision, path.path)
                if data is None:
                    raise ValueError("remote_event_missing")
                target = staging / path.path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)

        manual_paths = {path.path: path for path in details.paths if not path.automatic}
        for raw_path, raw_choice in selections.items():
            normalized_path = classify_conflict_path(raw_path).path
            item = manual_paths[normalized_path]
            choice = SelectionChoice(raw_choice)
            if choice is SelectionChoice.KEEP_LOCAL:
                continue
            remote_data = repo.read_file_at(details.remote.revision, item.path)
            if remote_data is None:
                raise ValueError("remote_content_missing")
            if choice is SelectionChoice.KEEP_REMOTE:
                target = staging / item.path
                candidate_paths.add(item.path)
            else:
                target = staging / f"{item.path}.remote"
                if target.exists():
                    raise ValueError("preserve_both_path_collision")
                candidate_paths.add(f"{item.path}.remote")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(remote_data)

        store = ThreadActivityEventStore(
            staging,
            workspace_id=workspace_id,
            device_id="recovery-validation",
        )
        events = store.read_workspace_events()
        projection = store.project_workspace()
        if rebuildable_views:
            target = staging / "_views" / "thread-activity.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(render_thread_activity_view(projection))
            candidate_paths.update(path.path for path in rebuildable_views)
    except ValueError as exc:
        temporary.cleanup()
        error_code = str(exc) or "manual_recovery_failed"
        return RecoveryPreparation(
            status="rejected",
            base_revision=details.base_revision,
            local_revision=details.local.revision,
            remote_revision=details.remote.revision,
            generated_view_count=generated_views,
            error_code=error_code,
        )
    except Exception:  # noqa: BLE001 - safe visible validation result
        temporary.cleanup()
        return RecoveryPreparation(
            status="projection-failed",
            base_revision=details.base_revision,
            local_revision=details.local.revision,
            remote_revision=details.remote.revision,
            generated_view_count=generated_views,
            error_code="event_projection_failed",
        )
    return RecoveryPreparation(
        status="validated",
        base_revision=details.base_revision,
        local_revision=details.local.revision,
        remote_revision=details.remote.revision,
        event_count=len(events),
        aggregate_count=len(projection),
        generated_view_count=generated_views,
        rebuilt_view_count=len(rebuildable_views),
        staging_dir=staging,
        candidate_paths=tuple(sorted(candidate_paths)),
        selection_summary=tuple(
            sorted(
                (classify_conflict_path(path).path, SelectionChoice(choice).value)
                for path, choice in selections.items()
            )
        ),
        _temporary=temporary,
    )


def _refs_match_preparation(repo: GitRepo, prepared: RecoveryPreparation) -> bool:
    if (
        prepared.base_revision is None
        or prepared.local_revision is None
        or prepared.remote_revision is None
    ):
        return False
    try:
        local_revision = repo.head_revision()
        remote_revision = repo.upstream_revision()
        base_revision = repo.merge_base(local_revision, remote_revision)
    except GitError:
        return False
    return (
        local_revision == prepared.local_revision
        and remote_revision == prepared.remote_revision
        and base_revision == prepared.base_revision
    )


def _safe_target(root: Path, relative: str) -> Path | None:
    item = classify_conflict_path(relative)
    target = root / item.path
    current = root
    for part in Path(item.path).parts[:-1]:
        current /= part
        if current.is_symlink():
            return None
    return target


def _append_recovery_audit(
    vault_dir: Path,
    prepared: RecoveryPreparation,
    *,
    merge_revision: str,
) -> None:
    """Persist a body-free recovery audit after the merge commit succeeds."""
    target = _safe_target(vault_dir, RECOVERY_AUDIT_PATH)
    if target is None or target.is_symlink() or target.is_dir():
        raise GitError("恢复审计路径不安全")
    previous = target.read_bytes() if target.is_file() else b""
    record = {
        "schema_version": 1,
        "kind": "sync-conflict-recovery",
        "status": "committed",
        "recorded_at": datetime.now(UTC).isoformat(),
        "base_revision": prepared.base_revision,
        "local_revision": prepared.local_revision,
        "remote_revision": prepared.remote_revision,
        "merge_revision": merge_revision,
        "event_count": prepared.event_count,
        "aggregate_count": prepared.aggregate_count,
        "generated_view_count": prepared.generated_view_count,
        "rebuilt_view_count": prepared.rebuilt_view_count,
        "applied_paths": list(prepared.candidate_paths),
        "selections": dict(prepared.selection_summary),
    }
    audit = (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    atomic_write_bytes(target, previous + audit, ensure_parents=True)


def apply_prepared_recovery(
    vault_dir: Path,
    prepared: RecoveryPreparation,
    *,
    workspace_id: str,
    confirm: bool = False,
    backend_kind: str | None = None,
    author: CommitIdentity | None = None,
) -> RecoveryApplyResult:
    """Apply a validated candidate as a normal two-parent merge commit.

    This is the only workflow in this module that writes the vault. It requires
    an explicit confirmation, a live revision match, a clean worktree, and a
    live staging directory. It never fetches, force-pushes, resets, rebases, or
    stashes. The web caller may attempt an ordinary push after this local commit.
    """
    if not prepared.ready:
        return RecoveryApplyResult(
            status="preparation-not-ready",
            error_code=prepared.error_code or "recovery_not_ready",
        )
    if not confirm:
        return RecoveryApplyResult(
            status="confirmation-required", error_code="explicit_confirmation"
        )
    if prepared.staging_dir is None:
        return RecoveryApplyResult(status="preparation-not-ready", error_code="staging_missing")
    repo = GitRepo(vault_dir, backend_kind=backend_kind, workspace_id=workspace_id)
    paths = tuple(sorted(set(prepared.candidate_paths)))
    try:
        with workspace_lock(vault_dir.parent):
            if not _refs_match_preparation(repo, prepared):
                return RecoveryApplyResult(status="stale", error_code="conflict_snapshot_stale")
            if repo.is_dirty():
                return RecoveryApplyResult(status="rejected", error_code="current_worktree_dirty")
            sources: list[tuple[str, Path, Path]] = []
            for relative in paths:
                source = _safe_target(prepared.staging_dir, relative)
                target = _safe_target(vault_dir, relative)
                if source is None or target is None:
                    return RecoveryApplyResult(status="rejected", error_code="recovery_path_unsafe")
                if source.is_symlink() or not source.is_file():
                    return RecoveryApplyResult(status="rejected", error_code="staged_file_missing")
                sources.append((relative, source, target))
            for _, source, target in sources:
                atomic_write_bytes(target, source.read_bytes(), ensure_parents=True)
            repo.add(list(paths))
            if not _refs_match_preparation(repo, prepared):
                return RecoveryApplyResult(
                    status="stale-after-write", error_code="conflict_snapshot_changed"
                )
            repo.commit_merge(
                f"wb: sync recovery events={prepared.event_count} "
                f"views={prepared.generated_view_count} paths={len(paths)}",
                prepared.remote_revision or "",
                author=author,
            )
            merge_revision = repo.head_revision()
            _append_recovery_audit(vault_dir, prepared, merge_revision=merge_revision)
            repo.add([RECOVERY_AUDIT_PATH])
            repo.commit("wb: sync recovery audit", author=author or default_identity())
            return RecoveryApplyResult(
                status="committed",
                revision=merge_revision,
                applied_paths=paths,
            )
    except LockBusy:
        return RecoveryApplyResult(status="busy", error_code="workspace_locked")
    except GitError:
        return RecoveryApplyResult(status="failed", error_code="recovery_commit_failed")


def validate_manual_selections(
    details: DivergenceDetails,
    *,
    base_revision: str,
    local_revision: str,
    remote_revision: str,
    selections: Mapping[str, SelectionChoice | str],
) -> SelectionValidation:
    """Validate a complete, current manual-selection snapshot without writing."""
    if (
        details.base_revision != base_revision
        or details.local.revision != local_revision
        or details.remote.revision != remote_revision
    ):
        return SelectionValidation(status="stale", error_code="conflict_snapshot_stale")

    normalized: dict[str, SelectionChoice | str] = {}
    for raw_path, choice in selections.items():
        try:
            path = classify_conflict_path(raw_path).path
        except ValueError:
            return SelectionValidation(status="invalid", error_code="manual_selection_invalid_path")
        if path in normalized:
            return SelectionValidation(
                status="invalid", error_code="manual_selection_duplicate_path"
            )
        normalized[path] = choice
    manual = {path.path: path for path in details.paths if not path.automatic}
    received = set(normalized)
    missing = tuple(sorted(set(manual) - received))
    unexpected = tuple(sorted(received - set(manual)))
    invalid: list[str] = []
    for path, raw_choice in normalized.items():
        item = manual.get(path)
        if item is None:
            continue
        try:
            choice = SelectionChoice(raw_choice)
        except ValueError:
            invalid.append(path)
            continue
        if (
            item.kind
            in {
                ConflictKind.OPAQUE_BINARY,
                ConflictKind.UNKNOWN_GENERATED_VIEW,
            }
            and choice is not SelectionChoice.PRESERVE_BOTH
        ):
            invalid.append(path)
    if missing or unexpected or invalid:
        return SelectionValidation(
            status="incomplete" if missing else "invalid",
            missing_paths=missing,
            unexpected_paths=unexpected,
            invalid_paths=tuple(sorted(invalid)),
            error_code="manual_selection_incomplete" if missing else "manual_selection_invalid",
        )
    return SelectionValidation(status="validated")


def recovery_manifest_bytes(
    state: SyncState,
    plan: ConflictRecoveryPlan,
    details: DivergenceDetails | None = None,
) -> bytes:
    """Create a single-file, body-free recovery package for local handoff."""
    manifest: dict[str, object] = {
        "schema_version": 1,
        "kind": "sync-recovery-manifest",
        "state": state.value,
        "recovery_plan": plan.as_dict(),
        "details": details.as_dict() if details is not None else None,
        "content_policy": "paths-and-digests-only; no vault body, logs, credentials, or remote URL",
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "sync-recovery-manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        )
    return output.getvalue()


__all__ = [
    "ConflictPathDetail",
    "ConflictSide",
    "DivergenceDetails",
    "RecoveryPreparation",
    "RecoveryApplyResult",
    "SelectionChoice",
    "SelectionValidation",
    "TemporaryValidation",
    "inspect_divergence",
    "apply_prepared_recovery",
    "prepare_automatic_recovery",
    "prepare_manual_recovery",
    "recovery_manifest_bytes",
    "validate_manual_selections",
    "validate_automatic_recovery",
]
