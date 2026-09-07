"""只读的分叉详情提取（P2-02）。

此模块只读取已 fetch 的本地 refs，并对两个提交树做比较。它不 fetch、merge、checkout、
替换工作树，也不创建提交；实际恢复仍必须由后续临时 worktree workflow 承担。
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import tempfile
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal

from summit_workbench.domain.sync import SyncState
from summit_workbench.domain.sync_conflict import (
    ConflictAction,
    ConflictKind,
    ConflictRecoveryPlan,
    classify_conflict_path,
)
from summit_workbench.domain.thread_activity import ThreadActivityEvent
from summit_workbench.repositories.git import GitError, GitRepo
from summit_workbench.repositories.thread_activity_events import ThreadActivityEventStore

RecoverySide = Literal["local", "remote"]


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
    error_code: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "ok": self.status == "validated",
            "event_count": self.event_count,
            "aggregate_count": self.aggregate_count,
            "generated_view_count": self.generated_view_count,
            "error_code": self.error_code,
        }


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


def _copy_regular_files(source: Path, destination: Path) -> None:
    """Copy only regular event files; symlinks never enter the staging area."""
    if not source.is_dir():
        return
    for path in source.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


def validate_automatic_recovery(
    vault_dir: Path,
    details: DivergenceDetails,
    *,
    workspace_id: str,
    backend_kind: str | None = None,
) -> TemporaryValidation:
    """Validate event items in an ephemeral staging area without repository writes.

    The staging area contains no ``.git`` directory and is deleted before return. The
    function intentionally validates only append-only events; generated views are a
    later rebuild step and therefore cannot make this result look like an applied merge.
    """
    if details.manual_path_count:
        return TemporaryValidation(status="manual-confirmation-required", error_code="manual_items")
    repo = GitRepo(vault_dir, backend_kind=backend_kind, workspace_id=workspace_id)
    event_paths = tuple(
        path for path in details.paths if path.kind is ConflictKind.APPEND_ONLY_EVENT
    )
    generated_views = sum(path.kind is ConflictKind.GENERATED_VIEW for path in details.paths)
    with tempfile.TemporaryDirectory(prefix=".summit-workbench-recovery-") as temporary:
        staging = Path(temporary)
        _copy_regular_files(vault_dir / "_events", staging / "_events")
        for path in event_paths:
            if len(path.changed_on) == 2 and path.local_sha256 != path.remote_sha256:
                return TemporaryValidation(
                    status="rejected",
                    generated_view_count=generated_views,
                    error_code="event_path_collision",
                )
            if "remote" in path.changed_on and "local" not in path.changed_on:
                data = repo.read_file_at(details.remote.revision, path.path)
                if data is None:
                    return TemporaryValidation(
                        status="rejected",
                        generated_view_count=generated_views,
                        error_code="remote_event_missing",
                    )
                target = staging / path.path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        try:
            store = ThreadActivityEventStore(
                staging,
                workspace_id=workspace_id,
                device_id="recovery-validation",
            )
            events = store.read_workspace_events()
            projection = store.project_workspace()
        except Exception:  # noqa: BLE001 - safe visible validation result
            return TemporaryValidation(
                status="projection-failed",
                generated_view_count=generated_views,
                error_code="event_projection_failed",
            )
    return TemporaryValidation(
        status="view-rebuild-pending" if generated_views else "validated",
        event_count=len(events),
        aggregate_count=len(projection),
        generated_view_count=generated_views,
    )


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
        if item.kind is ConflictKind.OPAQUE_BINARY and choice is not SelectionChoice.PRESERVE_BOTH:
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
    "SelectionChoice",
    "SelectionValidation",
    "TemporaryValidation",
    "inspect_divergence",
    "recovery_manifest_bytes",
    "validate_manual_selections",
    "validate_automatic_recovery",
]
