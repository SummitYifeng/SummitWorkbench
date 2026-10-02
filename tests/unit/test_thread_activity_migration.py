from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from summit_workbench.domain.thread_activity import ThreadActivityEvent, project_thread_activity
from summit_workbench.repositories.thread_activity_events import ThreadActivityEventStore
from summit_workbench.repositories.thread_notes import append_work_log, save_thread_artifact
from summit_workbench.workflows.local_mutation import LocalMutationOutcome, run_local_mutation
from summit_workbench.workflows.thread_activity_migration import (
    THREAD_DOC_ACTIVITY_KIND,
    WORK_LOG_ACTIVITY_KIND,
    ThreadActivityMigration,
    ThreadActivityMigrationMode,
    thread_activity_mode_from_environment,
)


def _migration(
    vault: Path,
    device: str = "device-a",
    mode: ThreadActivityMigrationMode = ThreadActivityMigrationMode.DUAL_WRITE,
) -> ThreadActivityMigration:
    return ThreadActivityMigration(
        vault,
        workspace_id="workspace-1",
        device_id=device,
        mode=mode,
    )


def test_mode_is_fail_closed_and_legacy_is_a_real_rollback_switch() -> None:
    assert (
        thread_activity_mode_from_environment("shadow-read")
        is ThreadActivityMigrationMode.SHADOW_READ
    )
    assert (
        thread_activity_mode_from_environment("dual-write")
        is ThreadActivityMigrationMode.DUAL_WRITE
    )
    assert thread_activity_mode_from_environment("unexpected") is ThreadActivityMigrationMode.LEGACY


def test_shadow_read_keeps_legacy_write_and_reports_without_event_write(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    migration = _migration(vault, mode=ThreadActivityMigrationMode.SHADOW_READ)

    path = append_work_log(
        vault,
        projects=["thread-a"],
        text="safe source text",
        now=datetime(2026, 1, 2, tzinfo=UTC),
        activity_migration=migration,
        causation_operation_id="operation-1",
    )

    assert path.is_file()
    assert not (vault / "_events").exists()
    assert migration.last_report.status == "mismatch"
    assert migration.last_report.differences[0].field == "presence"


def test_dual_write_mirrors_log_and_artifact_without_copying_body(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    migration = _migration(vault)
    occurred_at = datetime(2026, 1, 2, 9, 0, tzinfo=UTC)

    append_work_log(
        vault,
        projects=["thread-a", "thread-b"],
        text="PAT must never enter the event payload",
        now=occurred_at,
        activity_migration=migration,
        causation_operation_id="operation-log",
    )
    save_thread_artifact(
        vault,
        project="thread-a",
        text="private artifact body",
        now=occurred_at + timedelta(seconds=1),
        activity_migration=migration,
        causation_operation_id="operation-artifact",
    )

    events = migration.store.read_workspace_events()
    assert {event.kind for event in events} == {WORK_LOG_ACTIVITY_KIND, THREAD_DOC_ACTIVITY_KIND}
    assert all("PAT" not in str(event.payload) for event in events)
    assert all("private artifact body" not in str(event.payload) for event in events)
    assert migration.last_report.status == "match"
    assert migration.last_report.legacy_aggregate_count == 2
    assert migration.last_report.event_aggregate_count == 2


def test_dual_write_retry_is_idempotent_for_same_operation(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    migration = _migration(vault)
    path = vault / "logs/2026-01-02-001.md"
    path.parent.mkdir(parents=True)

    first = migration.record_work_log(
        path,
        projects=["thread-a"],
        activity_date="2026-01-02",
        causation_operation_id="operation-1",
        occurred_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    second = migration.record_work_log(
        path,
        projects=["thread-a"],
        activity_date="2026-01-02",
        causation_operation_id="operation-1",
        occurred_at=datetime(2026, 1, 2, tzinfo=UTC),
    )

    assert first.event_ids == second.event_ids
    assert len(migration.store.read_events()) == 1


def test_workspace_projection_handles_unordered_duplicate_offline_events(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    first = ThreadActivityEventStore(vault, workspace_id="workspace-1", device_id="device-a")
    second = ThreadActivityEventStore(vault, workspace_id="workspace-1", device_id="device-b")
    event_a = first.new_event(
        kind=WORK_LOG_ACTIVITY_KIND,
        aggregate_id="thread-a",
        payload={
            "activity_date": "2026-01-02",
            "source_path": "logs/a.md",
            "source_type": "work-log",
        },
        occurred_at=datetime(2026, 1, 2, 10, tzinfo=UTC),
        causation_operation_id="offline-a",
    )
    event_b = second.new_event(
        kind=WORK_LOG_ACTIVITY_KIND,
        aggregate_id="thread-a",
        payload={
            "activity_date": "2026-01-03",
            "source_path": "logs/b.md",
            "source_type": "work-log",
        },
        occurred_at=datetime(2026, 1, 3, 10, tzinfo=UTC),
        causation_operation_id="offline-b",
    )
    first.append(event_a)
    second.append(event_b)

    merged = first.read_workspace_events()
    projected = first.project_workspace()
    assert {event.event_id for event in merged} == {event_a.event_id, event_b.event_id}
    assert first.project_workspace() == first.project_workspace()
    assert projected["thread-a"].event_ids == (event_a.event_id, event_b.event_id)
    assert first.project_workspace() == project_thread_activity([event_b, event_a, event_a])


def test_projection_failure_is_reported_without_exposing_paths(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    migration = _migration(vault, mode=ThreadActivityMigrationMode.SHADOW_READ)

    def fail() -> list[ThreadActivityEvent]:
        raise RuntimeError("simulated projection failure")

    migration.store.read_workspace_events = fail  # type: ignore[method-assign]
    report = migration.inspect()
    assert report.status == "projection-failed"
    assert report.error_code == "thread_activity_projection_failed"
    assert report.diagnostic == "RuntimeError"
    assert str(vault) not in str(report.as_dict())


def test_dual_write_event_and_note_are_declared_local_files(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    migration = _migration(vault)

    def mutate(operation_id: str) -> LocalMutationOutcome[Path]:
        path = append_work_log(
            vault,
            projects=["thread-a"],
            text="legacy note",
            now=datetime(2026, 1, 2, tzinfo=UTC),
            activity_migration=migration,
            causation_operation_id=operation_id,
        )
        return LocalMutationOutcome(path, (path, *migration.last_write_paths))

    result = run_local_mutation(vault, "threads/logs", mutate)
    assert "logs/2026-01-02-001.md" in {
        p.relative_to(vault).as_posix() for p in result.changed_paths
    }
    assert any(
        p.relative_to(vault).as_posix().startswith("_events/device-a/")
        for p in result.changed_paths
    )
    assert not (vault / ".git").exists()


def test_local_mutation_includes_path_business_return(tmp_path: Path) -> None:
    """Business return paths are included even when the caller lists only projections."""
    vault = tmp_path / "vault"
    vault.mkdir()
    migration = _migration(vault)

    def mutate(operation_id: str) -> LocalMutationOutcome[Path]:
        path = append_work_log(
            vault,
            projects=["thread-a"],
            text="legacy note",
            now=datetime(2026, 1, 3, tzinfo=UTC),
            activity_migration=migration,
            causation_operation_id=operation_id,
        )
        # Simulate a caller that reports only the projection path.
        return LocalMutationOutcome(path, migration.last_write_paths)

    result = run_local_mutation(vault, "threads/logs", mutate)
    assert vault / "logs/2026-01-03-001.md" in result.changed_paths
    assert any("_events/device-a" in str(path) for path in result.changed_paths)
