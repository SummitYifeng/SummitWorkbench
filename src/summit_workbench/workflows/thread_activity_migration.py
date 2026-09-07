"""P2-01B migration seam for the existing thread activity slice.

The legacy Markdown files remain the source of truth in this phase.  The
event slice mirrors only work logs and thread-doc artifacts; inbox, meeting
decisions, and project正文 are intentionally outside this module.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path

from summit_workbench.domain.thread_activity import ThreadActivityView, project_thread_activity
from summit_workbench.repositories.thread_activity_events import (
    ThreadActivityEventStore,
    ThreadActivityStoreError,
)
from summit_workbench.repositories.vault import load_note, meta_date_iso

WORK_LOG_ACTIVITY_KIND = "thread.activity.work-log.created"
THREAD_DOC_ACTIVITY_KIND = "thread.activity.thread-doc.created"
_MODE_ENV_NAMES = ("WB_THREAD_ACTIVITY_MODE", "WB_THREAD_ACTIVITY_MIGRATION_MODE")


class ThreadActivityMigrationMode(StrEnum):
    LEGACY = "legacy"
    SHADOW_READ = "shadow-read"
    DUAL_WRITE = "dual-write"


class ThreadActivityProjectionError(RuntimeError):
    """The old or new activity projection cannot be compared safely."""


@dataclass(frozen=True)
class ThreadActivityDifference:
    aggregate_id: str
    field: str
    legacy_value: object
    event_value: object

    def as_dict(self) -> dict[str, object]:
        return {
            "aggregate_id": self.aggregate_id,
            "field": self.field,
            "legacy_value": self.legacy_value,
            "event_value": self.event_value,
        }


@dataclass(frozen=True)
class ThreadActivityConsistencyReport:
    mode: ThreadActivityMigrationMode
    status: str
    legacy_aggregate_count: int = 0
    event_aggregate_count: int = 0
    matching_aggregate_count: int = 0
    differences: tuple[ThreadActivityDifference, ...] = ()
    error_code: str | None = None
    diagnostic: str | None = None

    @property
    def ok(self) -> bool:
        return self.status in {"disabled", "match"}

    def as_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode.value,
            "status": self.status,
            "ok": self.ok,
            "legacy_aggregate_count": self.legacy_aggregate_count,
            "event_aggregate_count": self.event_aggregate_count,
            "matching_aggregate_count": self.matching_aggregate_count,
            "difference_count": len(self.differences),
            "differences": [difference.as_dict() for difference in self.differences],
            "error_code": self.error_code,
            "diagnostic": self.diagnostic,
        }


@dataclass(frozen=True)
class ThreadActivityWriteResult:
    event_ids: tuple[str, ...]
    report: ThreadActivityConsistencyReport
    changed_paths: tuple[Path, ...] = ()


@dataclass(frozen=True)
class _LegacyActivity:
    aggregate_id: str
    activity_date: str
    source_path: str
    kind: str
    source_type: str
    order_ns: int

    @property
    def payload(self) -> dict[str, str]:
        return {
            "activity_date": self.activity_date,
            "source_path": self.source_path,
            "source_type": self.source_type,
        }


def thread_activity_mode_from_environment(value: str | None = None) -> ThreadActivityMigrationMode:
    """Resolve the migration mode; unknown values fail closed to legacy mode."""
    raw = value
    if raw is None:
        raw = next((os.environ.get(name) for name in _MODE_ENV_NAMES if os.environ.get(name)), None)
    try:
        return ThreadActivityMigrationMode(raw or ThreadActivityMigrationMode.LEGACY)
    except ValueError:
        return ThreadActivityMigrationMode.LEGACY


def _as_date(value: object, *, source: Path) -> str:
    normalized = meta_date_iso(value)
    if normalized is None:
        raise ThreadActivityProjectionError(f"thread activity date 无效：{source.name}")
    return normalized


def _projects(meta: Mapping[str, object], *, source: Path) -> tuple[str, ...]:
    raw = meta.get("projects")
    if not isinstance(raw, list):
        raise ThreadActivityProjectionError(f"work-log projects 无效：{source.name}")
    projects = tuple(str(value).strip() for value in raw if str(value).strip())
    if not projects:
        raise ThreadActivityProjectionError(f"work-log projects 为空：{source.name}")
    return projects


def _legacy_activities(vault_dir: Path) -> list[_LegacyActivity]:
    activities: list[_LegacyActivity] = []
    logs_dir = vault_dir / "logs"
    if logs_dir.is_dir():
        for path in sorted(logs_dir.glob("*.md")):
            note = load_note(path)
            if note.parse_error is not None or note.meta.get("type") != "work-log":
                raise ThreadActivityProjectionError(f"work-log 无法投影：{path.name}")
            day = _as_date(note.meta.get("date"), source=path)
            for project in _projects(note.meta, source=path):
                activities.append(
                    _LegacyActivity(
                        project,
                        day,
                        str(path.relative_to(vault_dir)),
                        WORK_LOG_ACTIVITY_KIND,
                        "work-log",
                        path.stat().st_mtime_ns,
                    )
                )

    artifacts_dir = vault_dir / "artifacts"
    if artifacts_dir.is_dir():
        for path in sorted(artifacts_dir.glob("*.md")):
            note = load_note(path)
            if note.parse_error is not None or note.meta.get("type") != "thread-doc":
                raise ThreadActivityProjectionError(f"thread-doc 无法投影：{path.name}")
            day = _as_date(note.meta.get("date"), source=path)
            artifact_project = note.meta.get("project")
            if not isinstance(artifact_project, str) or not artifact_project.strip():
                raise ThreadActivityProjectionError(f"thread-doc project 无效：{path.name}")
            activities.append(
                _LegacyActivity(
                    artifact_project.strip(),
                    day,
                    str(path.relative_to(vault_dir)),
                    THREAD_DOC_ACTIVITY_KIND,
                    "thread-doc",
                    path.stat().st_mtime_ns,
                )
            )
    return activities


def legacy_thread_activity_projection(vault_dir: Path) -> dict[str, ThreadActivityView]:
    """Project only logs and thread-doc artifacts without reading their bodies."""
    grouped: dict[str, list[_LegacyActivity]] = {}
    for activity in _legacy_activities(vault_dir):
        grouped.setdefault(activity.aggregate_id, []).append(activity)
    result: dict[str, ThreadActivityView] = {}
    for aggregate_id, values in sorted(grouped.items()):
        ordered = sorted(
            values,
            key=lambda value: (value.activity_date, value.order_ns, value.source_path, value.kind),
        )
        last = ordered[-1]
        result[aggregate_id] = ThreadActivityView(
            aggregate_id=aggregate_id,
            event_ids=tuple(value.source_path for value in ordered),
            activity_count=len(ordered),
            last_occurred_at=datetime.combine(
                date.fromisoformat(last.activity_date), datetime.min.time(), tzinfo=UTC
            ),
            last_kind=last.kind,
            last_payload=last.payload,
        )
    return result


def _event_projection(store: ThreadActivityEventStore) -> dict[str, ThreadActivityView]:
    events = [
        event
        for event in store.read_workspace_events()
        if event.kind in {WORK_LOG_ACTIVITY_KIND, THREAD_DOC_ACTIVITY_KIND}
    ]
    return project_thread_activity(events)


def compare_thread_activity_projections(
    legacy: Mapping[str, ThreadActivityView],
    events: Mapping[str, ThreadActivityView],
    *,
    mode: ThreadActivityMigrationMode,
) -> ThreadActivityConsistencyReport:
    differences: list[ThreadActivityDifference] = []
    matching = 0
    for aggregate_id in sorted(set(legacy) | set(events)):
        old = legacy.get(aggregate_id)
        new = events.get(aggregate_id)
        if old is None or new is None:
            differences.append(
                ThreadActivityDifference(
                    aggregate_id,
                    "presence",
                    old is not None,
                    new is not None,
                )
            )
            continue
        fields = (
            ("activity_count", old.activity_count, new.activity_count),
            (
                "last_date",
                old.last_occurred_at.date().isoformat(),
                new.last_occurred_at.date().isoformat(),
            ),
            ("last_kind", old.last_kind, new.last_kind),
            ("last_payload", dict(old.last_payload), dict(new.last_payload)),
        )
        aggregate_differences = 0
        for field, old_value, new_value in fields:
            if old_value != new_value:
                aggregate_differences += 1
                differences.append(
                    ThreadActivityDifference(aggregate_id, field, old_value, new_value)
                )
        if aggregate_differences == 0:
            matching += 1
    return ThreadActivityConsistencyReport(
        mode=mode,
        status="match" if not differences else "mismatch",
        legacy_aggregate_count=len(legacy),
        event_aggregate_count=len(events),
        matching_aggregate_count=matching,
        differences=tuple(differences),
    )


class ThreadActivityMigration:
    """Coordinate shadow-read and dual-write while keeping legacy writes primary."""

    def __init__(
        self,
        vault_dir: Path,
        *,
        workspace_id: str,
        device_id: str,
        mode: ThreadActivityMigrationMode | str = ThreadActivityMigrationMode.LEGACY,
    ) -> None:
        self.vault_dir = vault_dir
        self.mode = thread_activity_mode_from_environment(str(mode))
        self.store = ThreadActivityEventStore(
            vault_dir, workspace_id=workspace_id, device_id=device_id
        )
        self.last_write_paths: tuple[Path, ...] = ()
        self.last_report = ThreadActivityConsistencyReport(mode=self.mode, status="disabled")

    @classmethod
    def from_environment(
        cls,
        vault_dir: Path,
        *,
        workspace_id: str,
        device_id: str,
    ) -> ThreadActivityMigration:
        return cls(
            vault_dir,
            workspace_id=workspace_id,
            device_id=device_id,
            mode=thread_activity_mode_from_environment(),
        )

    def inspect(self) -> ThreadActivityConsistencyReport:
        if self.mode is ThreadActivityMigrationMode.LEGACY:
            self.last_report = ThreadActivityConsistencyReport(self.mode, "disabled")
            return self.last_report
        try:
            report = compare_thread_activity_projections(
                legacy_thread_activity_projection(self.vault_dir),
                _event_projection(self.store),
                mode=self.mode,
            )
        except Exception as exc:  # noqa: BLE001 - report projection failure without breaking legacy reads
            report = ThreadActivityConsistencyReport(
                mode=self.mode,
                status="projection-failed",
                error_code="thread_activity_projection_failed",
                diagnostic=type(exc).__name__,
            )
        self.last_report = report
        return report

    def record(
        self,
        *,
        aggregate_ids: Iterable[str],
        kind: str,
        source_path: Path,
        activity_date: str,
        causation_operation_id: str,
        occurred_at: datetime,
    ) -> ThreadActivityWriteResult:
        self.last_write_paths = ()
        if self.mode is not ThreadActivityMigrationMode.DUAL_WRITE:
            return ThreadActivityWriteResult((), self.inspect(), ())
        source_type = "work-log" if kind == WORK_LOG_ACTIVITY_KIND else "thread-doc"
        payload = {
            "activity_date": activity_date,
            "source_path": str(source_path.relative_to(self.vault_dir)),
            "source_type": source_type,
        }
        event_ids: list[str] = []
        changed_paths: list[Path] = []
        try:
            existing = self.store.read_workspace_events()
            for aggregate_id in dict.fromkeys(aggregate_ids):
                matching = next(
                    (
                        event
                        for event in existing
                        if event.aggregate_id == aggregate_id
                        and event.kind == kind
                        and event.causation_operation_id == causation_operation_id
                    ),
                    None,
                )
                if matching is not None:
                    if matching.payload != payload:
                        raise ThreadActivityStoreError("causation operation payload collision")
                    event_ids.append(matching.event_id)
                    continue
                event = self.store.new_event(
                    kind=kind,
                    aggregate_id=aggregate_id,
                    payload=payload,
                    occurred_at=occurred_at,
                    causation_operation_id=causation_operation_id,
                )
                self.store.append(event)
                event_ids.append(event.event_id)
                changed_paths.append(
                    self.store.root
                    / event.occurred_at.strftime("%Y")
                    / event.occurred_at.strftime("%m")
                    / f"{event.event_id}.json"
                )
                existing.append(event)
        except (ThreadActivityStoreError, ValueError, OSError) as exc:
            report = ThreadActivityConsistencyReport(
                mode=self.mode,
                status="projection-failed",
                error_code="thread_activity_dual_write_failed",
                diagnostic=type(exc).__name__,
            )
            self.last_report = report
            self.last_write_paths = tuple(changed_paths)
            return ThreadActivityWriteResult(tuple(event_ids), report, tuple(changed_paths))
        self.last_write_paths = tuple(changed_paths)
        return ThreadActivityWriteResult(tuple(event_ids), self.inspect(), tuple(changed_paths))

    def record_work_log(
        self,
        path: Path,
        *,
        projects: Sequence[str],
        activity_date: str,
        causation_operation_id: str,
        occurred_at: datetime,
    ) -> ThreadActivityWriteResult:
        return self.record(
            aggregate_ids=projects,
            kind=WORK_LOG_ACTIVITY_KIND,
            source_path=path,
            activity_date=activity_date,
            causation_operation_id=causation_operation_id,
            occurred_at=occurred_at,
        )

    def record_thread_doc(
        self,
        path: Path,
        *,
        project: str,
        activity_date: str,
        causation_operation_id: str,
        occurred_at: datetime,
    ) -> ThreadActivityWriteResult:
        return self.record(
            aggregate_ids=(project,),
            kind=THREAD_DOC_ACTIVITY_KIND,
            source_path=path,
            activity_date=activity_date,
            causation_operation_id=causation_operation_id,
            occurred_at=occurred_at,
        )


__all__ = [
    "THREAD_DOC_ACTIVITY_KIND",
    "WORK_LOG_ACTIVITY_KIND",
    "ThreadActivityConsistencyReport",
    "ThreadActivityDifference",
    "ThreadActivityMigration",
    "ThreadActivityMigrationMode",
    "ThreadActivityProjectionError",
    "ThreadActivityWriteResult",
    "compare_thread_activity_projections",
    "legacy_thread_activity_projection",
    "thread_activity_mode_from_environment",
]
