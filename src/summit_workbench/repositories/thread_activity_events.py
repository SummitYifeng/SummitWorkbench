"""Immutable filesystem store for P2-01A thread activity events only."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from summit_workbench.domain.thread_activity import (
    MonotonicULIDGenerator,
    ThreadActivityEvent,
    ThreadActivityView,
    project_thread_activity,
)

EVENTS_DIRNAME = "_events"


class ThreadActivityStoreError(RuntimeError):
    """Event storage is corrupt, colliding, or cannot be written safely."""


def _canonical_json(event: ThreadActivityEvent) -> bytes:
    return (
        json.dumps(
            event.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


class ThreadActivityEventStore:
    """Append-only store; it exposes no update or delete operation."""

    def __init__(self, vault_dir: Path, *, workspace_id: str, device_id: str) -> None:
        self.vault_dir = vault_dir
        self.workspace_id = workspace_id
        self.device_id = device_id
        self._generator = MonotonicULIDGenerator(device_id)

    @property
    def root(self) -> Path:
        return self.vault_dir / EVENTS_DIRNAME / self.device_id

    def new_event(
        self,
        *,
        kind: str,
        aggregate_id: str,
        payload: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
        causation_operation_id: str,
    ) -> ThreadActivityEvent:
        return ThreadActivityEvent(
            event_id=self._generator.new(),
            workspace_id=self.workspace_id,
            device_id=self.device_id,
            occurred_at=occurred_at or datetime.now(UTC),
            kind=kind,
            aggregate_id=aggregate_id,
            payload=payload or {},
            causation_operation_id=causation_operation_id,
        )

    def append(self, event: ThreadActivityEvent) -> Path:
        if event.workspace_id != self.workspace_id or event.device_id != self.device_id:
            raise ThreadActivityStoreError("event workspace/device 与 store 不匹配")
        path = (
            self.root
            / event.occurred_at.strftime("%Y")
            / event.occurred_at.strftime("%m")
            / f"{event.event_id}.json"
        )
        data = _canonical_json(event)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            try:
                if path.read_bytes() == data:
                    return path
            except OSError as exc:
                raise ThreadActivityStoreError(f"无法读取 event collision：{path}") from exc
            raise ThreadActivityStoreError(f"event_id collision：{event.event_id}") from None
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                directory_fd = os.open(path.parent, os.O_RDONLY)
            except OSError:
                directory_fd = -1
            if directory_fd >= 0:
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        except BaseException as exc:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            raise ThreadActivityStoreError(f"event append failed：{path}") from exc
        return path

    def read_events(self) -> list[ThreadActivityEvent]:
        if not self.root.is_dir():
            return []
        events: list[ThreadActivityEvent] = []
        for path in sorted(self.root.rglob("*.json")):
            try:
                event = ThreadActivityEvent.model_validate_json(path.read_bytes())
            except Exception as exc:  # noqa: BLE001 - corruption is surfaced with path context
                raise ThreadActivityStoreError(f"thread activity event 损坏：{path}") from exc
            if event.workspace_id != self.workspace_id or event.device_id != self.device_id:
                raise ThreadActivityStoreError(f"thread activity event scope 错误：{path}")
            if path.stem != event.event_id:
                raise ThreadActivityStoreError(f"thread activity event id/path 不一致：{path}")
            events.append(event)
        return events

    def project(self) -> dict[str, ThreadActivityView]:
        return project_thread_activity(self.read_events())


__all__ = ["ThreadActivityEventStore", "ThreadActivityStoreError"]
