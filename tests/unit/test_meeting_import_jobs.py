from __future__ import annotations

import json
from pathlib import Path

from summit_workbench.domain.pipeline import MeetingTask, ProcessingState, SourceKind
from summit_workbench.repositories.meeting_archive import MeetingArchiveInput, archive_transcript
from summit_workbench.repositories.meeting_import_jobs import (
    ImportJobStage,
    ImportJobStatus,
    ImportJobStore,
)
from summit_workbench.repositories.meeting_state import record_task
from summit_workbench.webapp.context import WebContext
from summit_workbench.webapp.meeting_import import MeetingImportManager


def test_import_jobs_are_atomic_and_keep_recent_terminal_jobs(tmp_path):
    store = ImportJobStore(tmp_path / "jobs.json")
    job = store.create("job-1", "local:a", "meeting.txt")
    assert job.status is ImportJobStatus.QUEUED
    assert job.stage is ImportJobStage.UPLOADED

    updated = store.update(
        "job-1", status=ImportJobStatus.SUCCEEDED, stage=ImportJobStage.COMPLETED
    )
    assert updated is not None
    assert store.get("job-1") == updated
    assert store.find_by_idem_key("local:a") == updated
    assert store.list_recent()[0].job_id == "job-1"


def test_corrupt_import_job_file_is_isolated(tmp_path: Path) -> None:
    path = tmp_path / "jobs.json"
    path.write_text("{not-json", encoding="utf-8")
    assert ImportJobStore(path).list_recent() == []
    assert not path.exists()
    assert list(tmp_path.glob("jobs.json.corrupt-*"))


def test_running_job_recovery_requeues_archived_work(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "jobs.json"
    store = ImportJobStore(path)
    job = store.create("job-recover", "local:recover", "meeting.txt")
    store.update(
        job.job_id,
        status=ImportJobStatus.RUNNING,
        stage=ImportJobStage.STRUCTURING,
        transcript_path=str(tmp_path / "transcript.md"),
    )
    record_task(
        tmp_path / "vault",
        MeetingTask("local:recover", SourceKind.LOCAL_FILE, ProcessingState.ARCHIVED),
    )
    monkeypatch.setattr("summit_workbench.webapp.meeting_import._jobs_file", lambda _ctx: path)
    ctx = WebContext(tmp_path / "vault", tmp_path, "UTC")
    manager = MeetingImportManager(ctx, object())  # type: ignore[arg-type]
    manager._recover()

    recovered = manager.store.get("job-recover")
    assert recovered is not None
    assert recovered.status is ImportJobStatus.QUEUED
    assert recovered.stage is ImportJobStage.ARCHIVED
    assert manager._queue.get_nowait() == "job-recover"


def test_corrupt_file_rebuilds_jobs_from_meeting_ledger(tmp_path: Path, monkeypatch) -> None:
    vault = tmp_path / "vault"
    path = tmp_path / "jobs.json"
    transcript = archive_transcript(
        vault,
        MeetingArchiveInput(
            date="2026-09-16",
            title="恢复会议",
            transcript_text="张三 00:01:02 已归档",
            source=SourceKind.LOCAL_FILE,
            idem_key="local:rebuild",
        ),
    ).path
    record_task(
        vault,
        MeetingTask("local:rebuild", SourceKind.LOCAL_FILE, ProcessingState.ARCHIVED),
    )
    path.write_text(json.dumps({"jobs": [{"job_id": "bad"}]}), encoding="utf-8")
    monkeypatch.setattr("summit_workbench.webapp.meeting_import._jobs_file", lambda _ctx: path)
    manager = MeetingImportManager(WebContext(vault, tmp_path, "UTC"), object())  # type: ignore[arg-type]
    manager._recover()

    rebuilt = manager.store.list_recent()
    assert len(rebuilt) == 1
    assert rebuilt[0].status is ImportJobStatus.QUEUED
    assert rebuilt[0].stage is ImportJobStage.ARCHIVED
    assert rebuilt[0].transcript_path == str(transcript)
    assert manager._queue.get_nowait() == rebuilt[0].job_id
