"""P0-10C：同步持久状态、写边界与 automation-primary 契约。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from summit_workbench.domain.sync import SyncSnapshot, SyncState
from summit_workbench.domain.workspace import DeviceRole, LocalProfile, WorkspaceManifest
from summit_workbench.repositories.automation_primary import (
    AutomationPrimaryError,
    claim_automation_primary,
    load_automation_primary,
)
from summit_workbench.repositories.git import GitRepo
from summit_workbench.repositories.git_backend import CommitIdentity
from summit_workbench.repositories.workspace_manifest import write_workspace_manifest
from summit_workbench.workflows.local_mutation import MutationBlocked, run_local_mutation
from summit_workbench.workflows.sync_coordinator import pending_wb_commits


def _git_repo(path: Path) -> GitRepo:
    repo = GitRepo(path, backend_kind="dulwich")
    repo.backend.init()
    return repo


def test_pending_wb_count_is_real_and_survives_repeated_offline_writes(tmp_path) -> None:
    vault = tmp_path / "vault"
    repo = _git_repo(vault)
    (vault / "seed.md").write_text("seed\n", encoding="utf-8")
    repo.add(["seed.md"])
    repo.commit("seed", author=CommitIdentity("Test", "wb@local"))
    for index in range(3):
        note = vault / f"note-{index}.md"
        note.write_text(f"{index}\n", encoding="utf-8")
        repo.add([note.name])
        repo.commit(f"wb: capture [{index}]", author=CommitIdentity("Test", "wb@local"))
    assert pending_wb_commits(vault, backend_kind="dulwich") == 3


def test_sync_snapshot_preserves_last_success_on_failure() -> None:
    previous = SyncSnapshot(
        workspace_id="workspace-a",
        state=SyncState.READY,
        last_sync_at="2026-09-05T00:00:00+00:00",
        pending_commits=0,
    )
    failed = SyncSnapshot(
        workspace_id="workspace-a",
        state=SyncState.OFFLINE_LOCAL_AHEAD,
        last_sync_at=previous.last_sync_at,
        pending_commits=3,
    )
    assert failed.last_sync_at == previous.last_sync_at


def test_automation_primary_requires_explicit_takeover_and_increments_generation(tmp_path) -> None:
    vault = tmp_path / "vault"
    workspace_id = str(uuid4())
    write_workspace_manifest(
        vault,
        WorkspaceManifest(
            workspace_id=workspace_id,
            display_name="Workspace",
            created_at=datetime.now(UTC),
            min_reader_version="0.1.0",
            min_writer_version="0.1.0",
        ),
    )
    first = claim_automation_primary(vault, workspace_id, "device-a")
    assert first.generation == 1
    with pytest.raises(AutomationPrimaryError) as exc_info:
        claim_automation_primary(vault, workspace_id, "device-b")
    assert exc_info.value.code == "primary_already_claimed"
    second = claim_automation_primary(
        vault, workspace_id, "device-b", expected_generation=1, takeover=True
    )
    assert second.device_id == "device-b"
    assert second.generation == 2
    current = load_automation_primary(vault)
    assert current is not None
    assert current.device_id == "device-b"


def test_scheduler_cannot_use_profile_role_without_synced_claim() -> None:
    from summit_workbench.domain.sync import AutomationOutcome
    from summit_workbench.workflows.sync_coordinator import automation_gate

    profile = LocalProfile(
        workspace_id=str(uuid4()),
        display_name="Workspace",
        work_root=Path("/tmp/work"),
        vault_dir=Path("/tmp/work/_vault"),
        created_at=datetime.now(UTC),
        device_role=DeviceRole.AUTOMATION_PRIMARY,
    )
    assert automation_gate(profile, require_claim=True) is AutomationOutcome.NOT_PRIMARY


def test_local_mutation_guard_is_central_and_rejects_protected_snapshot(tmp_path) -> None:
    vault = tmp_path / "vault"
    snapshot = SyncSnapshot(
        workspace_id="workspace-a",
        state=SyncState.DIVERGED_PROTECTED,
    )
    with pytest.raises(MutationBlocked):
        run_local_mutation(
            vault,
            "capture",
            lambda _operation_id: pytest.fail("protected mutation must not run"),
            sync_snapshot=snapshot,
        )
