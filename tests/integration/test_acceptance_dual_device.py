"""P1-07D packaged-style dual-device acceptance against a temporary bare remote."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from summit_workbench.domain.sync import SyncState
from summit_workbench.domain.workspace import WorkspaceManifest
from summit_workbench.repositories.git import GitRepo
from summit_workbench.repositories.git_backend import CommitIdentity
from summit_workbench.repositories.workspace_manifest import manifest_path, write_workspace_manifest
from summit_workbench.workflows import sync_coordinator, workspace_migration
from summit_workbench.workflows.sync_conflict_recovery import (
    RECOVERY_AUDIT_PATH,
    SelectionChoice,
    apply_prepared_recovery,
    inspect_divergence,
    prepare_manual_recovery,
    validate_manual_selections,
)
from summit_workbench.workflows.workspace_migration import MigrationRegistry, MigrationStep

pytestmark = pytest.mark.integration

ID = CommitIdentity("acceptance", "acceptance@example.com")


def _dulwich(path: Path):
    from summit_workbench.repositories.dulwich_git import DulwichGitBackend

    return DulwichGitBackend(path)


def _seed(remote: Path, root: Path) -> tuple[str, bytes]:
    _dulwich(remote).init(bare=True)
    seed = root / "seed"
    repo = _dulwich(seed)
    repo.init()
    workspace_id = "9c5e0e4c-1f05-4b58-9b3e-9ad5d3b8d2d1"
    write_workspace_manifest(
        seed,
        WorkspaceManifest(
            schema_version=1,
            workspace_id=workspace_id,
            display_name="Dual device",
            created_at=datetime(2026, 9, 6),
            min_reader_version="0.4.1",
            min_writer_version="0.4.1",
        ),
    )
    (seed / "shared.txt").write_text("base\n", encoding="utf-8")
    repo.add([".summit-workbench/workspace.json", "shared.txt"])
    repo.commit("wb: acceptance baseline", author=ID)
    repo.add_remote("origin", str(remote))
    repo.push()
    return workspace_id, repo.head_revision().encode()


def test_two_homes_two_clones_migrate_ff_diverge_and_preserve_data(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Exercise v1->v2, ff, offline appends, reconnect, protected non-ff, and rollback."""
    # A local bare remote is the deterministic network substitute; production's HTTPS
    # scheme gate remains separately covered by unit tests and is bypassed only here.
    monkeypatch.setattr(workspace_migration, "require_https_remote", lambda _url: None)
    monkeypatch.setattr(sync_coordinator, "require_https_remote", lambda _url: None)

    remote = tmp_path / "remote.git"
    workspace_id, initial_head = _seed(remote, tmp_path)
    a = tmp_path / "clone-a"
    b = tmp_path / "clone-b"
    _dulwich(a).clone(str(remote), a)
    _dulwich(b).clone(str(remote), b)
    home_a = tmp_path / "home-a"
    home_b = tmp_path / "home-b"

    migration = workspace_migration.migrate_workspace(
        a,
        home=home_a,
        workspace_id=workspace_id,
        device_id="device-a",
        confirmed_device_id="device-a",
        repo=GitRepo(a, backend_kind="dulwich", workspace_id=workspace_id),
        app_version="0.4.2",
    )
    assert migration.status == "migrated"
    assert json.loads(manifest_path(a).read_text())["schema_version"] == 2

    state, _, _ = sync_coordinator.sync_workspace(
        b,
        home=home_b,
        workspace_id=workspace_id,
        backend_kind="dulwich",
    )
    assert state is SyncState.READY
    assert json.loads(manifest_path(b).read_text())["schema_version"] == 2

    # Both devices append while disconnected. A reconnects first and wins the push;
    # B's local commit must remain available and be protected as a divergence.
    (a / "from-a.txt").write_text("A\n", encoding="utf-8")
    repo_a = _dulwich(a)
    repo_a.add(["from-a.txt"])
    repo_a.commit("wb: offline A", author=ID)
    (b / "from-b.txt").write_text("B\n", encoding="utf-8")
    repo_b = _dulwich(b)
    repo_b.add(["from-b.txt"])
    repo_b.commit("wb: offline B", author=ID)
    repo_a.push()

    state, _, snapshot = sync_coordinator.sync_workspace(
        b,
        home=home_b,
        workspace_id=workspace_id,
        backend_kind="dulwich",
    )
    assert state is SyncState.DIVERGED_PROTECTED
    assert snapshot is not None
    assert (b / "from-b.txt").read_text(encoding="utf-8") == "B\n"
    assert (a / "from-a.txt").read_text(encoding="utf-8") == "A\n"
    assert _dulwich(remote).head_revision().encode() != initial_head

    # A failed migration restores the marker and never creates/pushes a commit.
    failed_remote = tmp_path / "failed-remote.git"
    _failed_id, failed_head = _seed(failed_remote, tmp_path / "failed")
    failed_clone = tmp_path / "failed-clone"
    _dulwich(failed_clone).clone(str(failed_remote), failed_clone)
    before = manifest_path(failed_clone).read_bytes()

    def fail_after_write(_raw: dict[str, object]) -> None:
        raise RuntimeError("injected migration failure")

    registry = MigrationRegistry(
        [
            MigrationStep(
                from_version=1,
                to_version=2,
                migration_id="test-migration-failure",
                apply=lambda raw: {**raw, "schema_version": 2},
                after_write=fail_after_write,
            )
        ]
    )
    with pytest.raises(workspace_migration.WorkspaceMigrationError):
        workspace_migration.migrate_workspace(
            failed_clone,
            home=tmp_path / "home-failed",
            device_id="device-f",
            confirmed_device_id="device-f",
            repo=GitRepo(failed_clone, backend_kind="dulwich", workspace_id=_failed_id),
            registry=registry,
        )
    assert manifest_path(failed_clone).read_bytes() == before
    assert _dulwich(failed_remote).head_revision().encode() == failed_head


def test_dual_device_divergence_recovery_converges_with_two_parent_merge(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """P2-02 end to end: diverge, inspect, prepare, apply, push, and converge.

    The dual-device test above stops at DIVERGED_PROTECTED.  This one drives the
    recovery through the real production entry points and asserts the two-parent
    merge, the body-free audit, and that the peer fast-forwards onto it.
    """
    monkeypatch.setattr(workspace_migration, "require_https_remote", lambda _url: None)
    monkeypatch.setattr(sync_coordinator, "require_https_remote", lambda _url: None)

    remote = tmp_path / "remote.git"
    workspace_id, _ = _seed(remote, tmp_path)
    a = tmp_path / "clone-a"
    b = tmp_path / "clone-b"
    _dulwich(a).clone(str(remote), a)
    _dulwich(b).clone(str(remote), b)
    home_a = tmp_path / "home-a"
    home_b = tmp_path / "home-b"

    for clone, home in ((a, home_a), (b, home_b)):
        state, _, _ = sync_coordinator.sync_workspace(
            clone, home=home, workspace_id=workspace_id, backend_kind="dulwich"
        )
        assert state is SyncState.READY

    # Both devices commit while disconnected; A pushes first so B sees a real
    # divergence instead of a fast-forward.
    (a / "from-a.md").write_text("A\n", encoding="utf-8")
    repo_a = _dulwich(a)
    repo_a.add(["from-a.md"])
    repo_a.commit("wb: offline A", author=ID)
    repo_a.push()

    (b / "from-b.md").write_text("B\n", encoding="utf-8")
    repo_b = _dulwich(b)
    repo_b.add(["from-b.md"])
    repo_b.commit("wb: offline B", author=ID)
    b_head = repo_b.head_revision()

    state, _, _ = sync_coordinator.sync_workspace(
        b, home=home_b, workspace_id=workspace_id, backend_kind="dulwich"
    )
    assert state is SyncState.DIVERGED_PROTECTED
    # Protection never rewrites B's history or drops its file.
    assert repo_b.head_revision() == b_head
    assert (b / "from-b.md").read_text(encoding="utf-8") == "B\n"

    details = inspect_divergence(b)
    assert {item.path for item in details.paths} == {"from-a.md", "from-b.md"}
    assert details.base_revision

    selections = {
        "from-a.md": SelectionChoice.KEEP_REMOTE,
        "from-b.md": SelectionChoice.KEEP_LOCAL,
    }
    validation = validate_manual_selections(
        details,
        base_revision=details.base_revision,
        local_revision=details.local.revision,
        remote_revision=details.remote.revision,
        selections=selections,
    )
    assert validation.status == "validated"

    with prepare_manual_recovery(
        b, details, workspace_id=workspace_id, selections=selections
    ) as prepared:
        assert prepared.ready
        result = apply_prepared_recovery(
            b, prepared, workspace_id=workspace_id, confirm=True, author=ID
        )

    assert result.status == "committed"
    assert result.revision is not None
    assert result.audit_status == "committed"
    assert repo_b.commit_parent_count(result.revision) == 2

    # Both sides survive the merge and the audit stays body-free.
    assert (b / "from-a.md").read_text(encoding="utf-8") == "A\n"
    assert (b / "from-b.md").read_text(encoding="utf-8") == "B\n"
    audit_records = [
        json.loads(line)
        for line in (b / RECOVERY_AUDIT_PATH).read_text(encoding="utf-8").splitlines()
    ]
    assert [record["status"] for record in audit_records] == ["committed"]
    assert audit_records[0]["merge_revision"] == result.revision
    assert audit_records[0]["applied_paths"]
    assert "payload" not in json.dumps(audit_records[0])

    # An ordinary push; the peer then fast-forwards onto the same history.
    repo_b.push()
    assert _dulwich(remote).head_revision() == repo_b.head_revision()

    state, _, _ = sync_coordinator.sync_workspace(
        a, home=home_a, workspace_id=workspace_id, backend_kind="dulwich"
    )
    assert state is SyncState.READY
    assert _dulwich(a).head_revision() == repo_b.head_revision()
    assert (a / "from-b.md").read_text(encoding="utf-8") == "B\n"
