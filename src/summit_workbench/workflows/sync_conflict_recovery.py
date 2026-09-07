"""只读的分叉详情提取（P2-02）。

此模块只读取已 fetch 的本地 refs，并对两个提交树做比较。它不 fetch、merge、checkout、
替换工作树，也不创建提交；实际恢复仍必须由后续临时 worktree workflow 承担。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from summit_workbench.domain.sync_conflict import (
    ConflictAction,
    ConflictKind,
    classify_conflict_path,
)
from summit_workbench.domain.thread_activity import ThreadActivityEvent
from summit_workbench.repositories.git import GitError, GitRepo

RecoverySide = Literal["local", "remote"]


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
    changed_paths = sorted((local_paths | remote_paths) if selected is None else selected)

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


__all__ = [
    "ConflictPathDetail",
    "ConflictSide",
    "DivergenceDetails",
    "inspect_divergence",
]
