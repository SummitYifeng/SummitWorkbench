"""会议导入任务的本机持久化队列。"""

from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from summit_workbench.repositories._atomic import atomic_write_text


class ImportJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class ImportJobStage(StrEnum):
    UPLOADED = "uploaded"
    ARCHIVED = "archived"
    STRUCTURING = "structuring"
    CANDIDATES = "candidates"
    COMPLETED = "completed"


class ImportJob(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: int = 1
    job_id: str
    idem_key: str
    file_name: str
    bytes: int = 0
    transcript_path: str | None = None
    status: ImportJobStatus = ImportJobStatus.QUEUED
    stage: ImportJobStage = ImportJobStage.UPLOADED
    created_at: datetime
    updated_at: datetime
    error: str | None = None
    retryable: bool = False
    operation_ids: list[str] = Field(default_factory=list)
    result: dict[str, object] | None = None


class ImportJobStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        self.corrupt_backup: Path | None = None

    def _read(self) -> list[ImportJob]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("jobs", []), list):
                raise ValueError("invalid meeting import jobs envelope")
            return [ImportJob.model_validate(item) for item in data["jobs"]]
        except (FileNotFoundError, OSError, ValueError, TypeError):
            self._isolate_corrupt_file()
            return []

    def _isolate_corrupt_file(self) -> None:
        """把损坏的本机队列移开；vault 状态账本仍是恢复依据。"""
        if not self.path.exists():
            return
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        target = self.path.with_name(self.path.name + f".corrupt-{stamp}")
        try:
            os.replace(self.path, target)
            self.corrupt_backup = target
        except OSError:
            pass

    def _write(self, jobs: list[ImportJob]) -> None:
        atomic_write_text(
            self.path,
            json.dumps(
                {"schema_version": 1, "jobs": [job.model_dump(mode="json") for job in jobs]},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            ensure_parents=True,
            new_mode=0o600,
        )

    def list_recent(self) -> list[ImportJob]:
        with self._lock:
            return list(reversed(self._read()))

    def get(self, job_id: str) -> ImportJob | None:
        with self._lock:
            return next((job for job in self._read() if job.job_id == job_id), None)

    def find_by_idem_key(self, idem_key: str) -> ImportJob | None:
        with self._lock:
            return next((job for job in reversed(self._read()) if job.idem_key == idem_key), None)

    def create(
        self, job_id: str | None, idem_key: str, file_name: str, bytes: int = 0
    ) -> ImportJob:
        with self._lock:
            now = datetime.now(UTC)
            job = ImportJob(
                job_id=job_id or uuid4().hex,
                idem_key=idem_key,
                file_name=file_name,
                bytes=bytes,
                created_at=now,
                updated_at=now,
            )
            jobs = self._read()
            jobs.append(job)
            self._write(jobs)
            return job

    def update(self, job_id: str, **changes: object) -> ImportJob | None:
        with self._lock:
            jobs = self._read()
            for index, job in enumerate(jobs):
                if job.job_id != job_id:
                    continue
                updated = job.model_copy(update={**changes, "updated_at": datetime.now(UTC)})
                jobs[index] = updated
                terminal = {
                    ImportJobStatus.SUCCEEDED,
                    ImportJobStatus.PARTIAL,
                    ImportJobStatus.FAILED,
                }
                if updated.status in terminal:
                    terminal_jobs = [item for item in jobs if item.status in terminal]
                    active_jobs = [item for item in jobs if item.status not in terminal]
                    jobs = active_jobs + terminal_jobs[-100:]
                self._write(jobs)
                return updated
            return None


__all__ = ["ImportJob", "ImportJobStage", "ImportJobStatus", "ImportJobStore"]
