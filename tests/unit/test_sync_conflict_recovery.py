from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from summit_workbench.domain.thread_activity import MonotonicULIDGenerator, ThreadActivityEvent
from summit_workbench.repositories.git import GitRepo
from summit_workbench.repositories.git_backend import CommitIdentity
from summit_workbench.workflows.sync_conflict_recovery import (
    RECOVERY_AUDIT_PATH,
    SelectionChoice,
    apply_prepared_recovery,
    inspect_divergence,
    prepare_automatic_recovery,
    prepare_manual_recovery,
    validate_automatic_recovery,
    validate_manual_selections,
)

IDENTITY = CommitIdentity("Recovery test", "recovery@example.com")


def _commit(repo: GitRepo, root: Path, rel: str, content: str, message: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    repo.add([rel])
    repo.commit(message, author=IDENTITY)


def test_inspect_divergence_returns_safe_side_and_event_metadata(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    GitRepo(remote).backend.init(bare=True)
    studio = tmp_path / "studio"
    studio_repo = GitRepo(studio)
    studio_repo.backend.init()
    _commit(studio_repo, studio, "README.md", "base\n", "wb: base")
    studio_repo.backend.add_remote("origin", str(remote))
    studio_repo.push()

    air = tmp_path / "air"
    air_repo = GitRepo(air)
    air_repo.backend.clone(str(remote), air)
    event = ThreadActivityEvent(
        event_id=MonotonicULIDGenerator("studio").new(),
        workspace_id="workspace-1",
        device_id="studio",
        occurred_at=datetime(2026, 9, 7, 1, 2, 3, tzinfo=UTC),
        kind="thread.activity.work-log.created",
        aggregate_id="project-1",
        payload={"source_type": "work-log"},
        causation_operation_id="operation-1",
    )
    _commit(
        studio_repo,
        studio,
        f"_events/studio/2026/09/{event.event_id}.json",
        event.model_dump_json(),
        "wb: studio event",
    )
    studio_repo.push()

    _commit(air_repo, air, "notes.md", "air\n", "wb: air note")
    air_repo.fetch()
    details = inspect_divergence(air, paths=None)

    assert details.base_revision == air_repo.merge_base(
        studio_repo.head_revision(), air_repo.head_revision()
    )
    assert details.local.side == "local"
    assert details.remote.side == "remote"
    assert {item.path for item in details.paths} == {
        f"_events/studio/2026/09/{event.event_id}.json",
        "notes.md",
    }
    event_detail = next(item for item in details.paths if item.kind.value == "append-only-event")
    assert event_detail.remote_event is not None
    assert event_detail.remote_event["device_id"] == "studio"
    assert event_detail.remote_event["causation_operation_id"] == "operation-1"
    assert event_detail.local_event is None
    assert all("payload" not in item for item in (event_detail.remote_event or {}))

    note_detail = next(item for item in details.paths if item.path == "notes.md")
    missing = validate_manual_selections(
        details,
        base_revision=details.base_revision,
        local_revision=details.local.revision,
        remote_revision=details.remote.revision,
        selections={},
    )
    assert missing.status == "incomplete"
    assert missing.missing_paths == (note_detail.path,)
    selected = validate_manual_selections(
        details,
        base_revision=details.base_revision,
        local_revision=details.local.revision,
        remote_revision=details.remote.revision,
        selections={note_detail.path: SelectionChoice.KEEP_LOCAL},
    )
    assert selected.status == "validated"
    stale = validate_manual_selections(
        details,
        base_revision="0" * 40,
        local_revision=details.local.revision,
        remote_revision=details.remote.revision,
        selections={note_detail.path: SelectionChoice.KEEP_LOCAL},
    )
    assert stale.error_code == "conflict_snapshot_stale"

    event_only = inspect_divergence(air, paths=(event_detail.path,))
    validation = validate_automatic_recovery(
        air,
        event_only,
        workspace_id="workspace-1",
    )
    assert validation.status == "validated"
    assert validation.event_count == 1
    assert validation.aggregate_count == 1
    assert air_repo.head_revision() == event_only.local.revision


def test_inspect_divergence_path_filter_only_changes_selection(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    GitRepo(remote).backend.init(bare=True)
    root = tmp_path / "root"
    repo = GitRepo(root)
    repo.backend.init()
    _commit(repo, root, "base.md", "base\n", "wb: base")
    repo.backend.add_remote("origin", str(remote))
    repo.push()
    other = tmp_path / "other"
    other_repo = GitRepo(other)
    other_repo.backend.clone(str(remote), other)
    _commit(repo, root, "a.md", "a\n", "wb: a")
    repo.push()
    _commit(other_repo, other, "b.md", "b\n", "wb: b")
    other_repo.fetch()

    details = inspect_divergence(other, paths=("b.md",))
    assert [item.path for item in details.paths] == ["b.md"]
    assert details.paths[0].changed_on == ("local",)


def test_validate_automatic_recovery_stops_before_manual_content(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    GitRepo(remote).backend.init(bare=True)
    root = tmp_path / "root"
    repo = GitRepo(root)
    repo.backend.init()
    _commit(repo, root, "base.md", "base\n", "wb: base")
    repo.backend.add_remote("origin", str(remote))
    repo.push()
    other = tmp_path / "other"
    other_repo = GitRepo(other)
    other_repo.backend.clone(str(remote), other)
    _commit(repo, root, "_views/thread.json", "{}\n", "wb: view")
    repo.push()
    _commit(other_repo, other, "notes.md", "manual\n", "wb: note")
    other_repo.fetch()

    details = inspect_divergence(other)
    validation = validate_automatic_recovery(other, details, workspace_id="workspace-1")

    assert validation.status == "manual-confirmation-required"
    assert validation.error_code == "manual_items"


def test_unknown_generated_view_requires_preserve_both_fallback(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    GitRepo(remote).backend.init(bare=True)
    root = tmp_path / "root"
    repo = GitRepo(root)
    repo.backend.init()
    _commit(repo, root, "base.md", "base\n", "wb: base")
    repo.backend.add_remote("origin", str(remote))
    repo.push()
    other = tmp_path / "other"
    other_repo = GitRepo(other)
    other_repo.backend.clone(str(remote), other)
    _commit(repo, root, "_views/thread.json", "{}\n", "wb: view")
    repo.push()
    event = ThreadActivityEvent(
        event_id=MonotonicULIDGenerator("device").new(),
        workspace_id="workspace-1",
        device_id="device",
        occurred_at=datetime(2026, 9, 7, tzinfo=UTC),
        kind="thread.activity.work-log.created",
        aggregate_id="project-1",
        causation_operation_id="operation-1",
    )
    _commit(
        other_repo,
        other,
        f"_events/device/2026/09/{event.event_id}.json",
        event.model_dump_json(),
        "wb: event",
    )
    other_repo.fetch()

    details = inspect_divergence(other)
    unknown_view = next(item for item in details.paths if item.path == "_views/thread.json")
    assert unknown_view.kind.value == "unknown-generated-view"
    assert unknown_view.automatic is False

    validation = validate_automatic_recovery(other, details, workspace_id="workspace-1")

    assert validation.status == "manual-confirmation-required"
    assert validation.as_dict()["ok"] is False
    assert validation.error_code == "manual_items"

    rejected = validate_manual_selections(
        details,
        base_revision=details.base_revision,
        local_revision=details.local.revision,
        remote_revision=details.remote.revision,
        selections={unknown_view.path: SelectionChoice.KEEP_REMOTE},
    )
    assert rejected.status == "invalid"
    assert rejected.invalid_paths == (unknown_view.path,)

    selected = validate_manual_selections(
        details,
        base_revision=details.base_revision,
        local_revision=details.local.revision,
        remote_revision=details.remote.revision,
        selections={unknown_view.path: SelectionChoice.PRESERVE_BOTH},
    )
    assert selected.status == "validated"
    with prepare_manual_recovery(
        other,
        details,
        workspace_id="workspace-1",
        selections={unknown_view.path: SelectionChoice.PRESERVE_BOTH},
    ) as prepared:
        assert prepared.status == "validated"
        assert prepared.candidate_paths == ("_views/thread.json.remote",)
        assert prepared.staging_dir is not None
        assert not (prepared.staging_dir / "_views/thread.json").exists()
        assert (prepared.staging_dir / "_views/thread.json.remote").read_text() == "{}\n"
        applied = apply_prepared_recovery(
            other,
            prepared,
            workspace_id="workspace-1",
            confirm=True,
            author=IDENTITY,
        )
        assert applied.status == "committed"
        assert applied.revision is not None
        assert other_repo.commit_parent_count(applied.revision) == 2
        assert (other / "_views/thread.json.remote").read_text() == "{}\n"
        audit = json.loads((other / RECOVERY_AUDIT_PATH).read_text().splitlines()[-1])
        assert audit["merge_revision"] == applied.revision
        assert audit["applied_paths"] == ["_views/thread.json.remote"]
    other_repo.push()
    assert other_repo.ahead_behind().ahead == 0
    assert other_repo.ahead_behind().behind == 0


def test_validate_automatic_recovery_rebuilds_defined_view_in_staging(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    GitRepo(remote).backend.init(bare=True)
    root = tmp_path / "root"
    repo = GitRepo(root)
    repo.backend.init()
    _commit(repo, root, "base.md", "base\n", "wb: base")
    repo.backend.add_remote("origin", str(remote))
    repo.push()
    other = tmp_path / "other"
    other_repo = GitRepo(other)
    other_repo.backend.clone(str(remote), other)
    _commit(repo, root, "_views/thread-activity.json", "stale\n", "wb: stale view")
    repo.push()
    event = ThreadActivityEvent(
        event_id=MonotonicULIDGenerator("device").new(),
        workspace_id="workspace-1",
        device_id="device",
        occurred_at=datetime(2026, 9, 7, tzinfo=UTC),
        kind="thread.activity.work-log.created",
        aggregate_id="project-1",
        payload={"source_type": "work-log"},
        causation_operation_id="operation-1",
    )
    _commit(
        other_repo,
        other,
        f"_events/device/2026/09/{event.event_id}.json",
        event.model_dump_json(),
        "wb: event",
    )
    other_repo.fetch()

    details = inspect_divergence(other)
    validation = validate_automatic_recovery(other, details, workspace_id="workspace-1")

    assert validation.status == "validated"
    assert validation.generated_view_count == 1
    assert validation.rebuilt_view_count == 1
    assert validation.event_count == 1
    assert validation.aggregate_count == 1
    assert other_repo.head_revision() == details.local.revision

    with prepare_automatic_recovery(other, details, workspace_id="workspace-1") as prepared:
        awaiting_confirmation = apply_prepared_recovery(
            other, prepared, workspace_id="workspace-1", confirm=False
        )
        assert awaiting_confirmation.status == "confirmation-required"
        applied = apply_prepared_recovery(other, prepared, workspace_id="workspace-1", confirm=True)
        assert applied.status == "committed"
        assert applied.revision is not None
        assert other_repo.commit_parent_count(applied.revision) == 2
        assert (other / "_views/thread-activity.json").read_text().find(
            '"projection": "thread-activity"'
        ) >= 0
        audit = json.loads((other / RECOVERY_AUDIT_PATH).read_text().splitlines()[-1])
        assert audit["status"] == "committed"
        assert audit["merge_revision"] == applied.revision
        assert audit["local_revision"] == details.local.revision
        assert "vault" not in json.dumps(audit)
    other_repo.push()
    assert other_repo.ahead_behind().ahead == 0
    assert other_repo.ahead_behind().behind == 0


def test_prepare_automatic_recovery_owns_ephemeral_staging_and_rejects_stale_snapshot(
    tmp_path: Path,
) -> None:
    remote = tmp_path / "remote.git"
    GitRepo(remote).backend.init(bare=True)
    root = tmp_path / "root"
    repo = GitRepo(root)
    repo.backend.init()
    _commit(repo, root, "base.md", "base\n", "wb: base")
    repo.backend.add_remote("origin", str(remote))
    repo.push()
    other = tmp_path / "other"
    other_repo = GitRepo(other)
    other_repo.backend.clone(str(remote), other)
    _commit(repo, root, "_views/thread-activity.json", "stale\n", "wb: stale view")
    repo.push()
    event = ThreadActivityEvent(
        event_id=MonotonicULIDGenerator("device").new(),
        workspace_id="workspace-1",
        device_id="device",
        occurred_at=datetime(2026, 9, 7, tzinfo=UTC),
        kind="thread.activity.work-log.created",
        aggregate_id="project-1",
        payload={"source_type": "work-log"},
        causation_operation_id="operation-1",
    )
    _commit(
        other_repo,
        other,
        f"_events/device/2026/09/{event.event_id}.json",
        event.model_dump_json(),
        "wb: event",
    )
    other_repo.fetch()
    details = inspect_divergence(other)

    with prepare_automatic_recovery(other, details, workspace_id="workspace-1") as prepared:
        assert prepared.ready is True
        assert prepared.as_dict()["staging_ready"] is True
        assert prepared.staging_dir is not None
        staging = prepared.staging_dir
        assert not (staging / ".git").exists()
        assert (staging / f"_events/device/2026/09/{event.event_id}.json").is_file()
        rendered = json.loads((staging / "_views/thread-activity.json").read_text())
        assert rendered["projection"] == "thread-activity"
        assert rendered["aggregates"][0]["aggregate_id"] == "project-1"
    assert not staging.exists()

    _commit(other_repo, other, "after.md", "after\n", "wb: after snapshot")
    stale = prepare_automatic_recovery(other, details, workspace_id="workspace-1")
    assert stale.status == "stale"
    assert stale.error_code == "conflict_snapshot_stale"
    assert stale.staging_dir is None


def test_prepare_manual_recovery_applies_remote_choice_only_in_staging(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    GitRepo(remote).backend.init(bare=True)
    root = tmp_path / "root"
    repo = GitRepo(root)
    repo.backend.init()
    _commit(repo, root, "base.md", "base\n", "wb: base")
    repo.backend.add_remote("origin", str(remote))
    repo.push()
    other = tmp_path / "other"
    other_repo = GitRepo(other)
    other_repo.backend.clone(str(remote), other)
    _commit(repo, root, "notes.md", "remote\n", "wb: remote note")
    repo.push()
    _commit(other_repo, other, "notes.md", "local\n", "wb: local note")
    other_repo.fetch()

    details = inspect_divergence(other)
    with prepare_manual_recovery(
        other,
        details,
        workspace_id="workspace-1",
        selections={"notes.md": SelectionChoice.KEEP_REMOTE},
    ) as prepared:
        assert prepared.ready is True
        assert prepared.staging_dir is not None
        assert (prepared.staging_dir / "notes.md").read_text() == "remote\n"
        assert (other / "notes.md").read_text() == "local\n"
        assert other_repo.head_revision() == details.local.revision


def test_prepare_manual_recovery_preserves_remote_copy_deterministically(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    GitRepo(remote).backend.init(bare=True)
    root = tmp_path / "root"
    repo = GitRepo(root)
    repo.backend.init()
    _commit(repo, root, "base.md", "base\n", "wb: base")
    repo.backend.add_remote("origin", str(remote))
    repo.push()
    other = tmp_path / "other"
    other_repo = GitRepo(other)
    other_repo.backend.clone(str(remote), other)
    _commit(repo, root, "attachment.bin", "remote\n", "wb: remote binary")
    repo.push()
    _commit(other_repo, other, "attachment.bin", "local\n", "wb: local binary")
    other_repo.fetch()

    details = inspect_divergence(other)
    with prepare_manual_recovery(
        other,
        details,
        workspace_id="workspace-1",
        selections={"attachment.bin": SelectionChoice.PRESERVE_BOTH},
    ) as prepared:
        assert prepared.ready is True
        assert prepared.staging_dir is not None
        assert (prepared.staging_dir / "attachment.bin").read_text() == "local\n"
        assert (prepared.staging_dir / "attachment.bin.remote").read_text() == "remote\n"
