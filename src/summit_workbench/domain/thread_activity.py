"""P2-01A thread activity events and deterministic projection primitives.

This slice deliberately models only thread activity.  Inbox rows, meeting
decisions, and project正文 remain on their existing storage paths until a
later migration package explicitly moves them.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_ID_LENGTH = 26
_MAX_TIMESTAMP = (1 << 48) - 1


def _encode(value: int, length: int) -> str:
    if value < 0 or value >= 1 << (5 * length):
        raise ValueError("ULID component out of range")
    chars = ["0"] * length
    for index in range(length - 1, -1, -1):
        chars[index] = _ALPHABET[value & 31]
        value >>= 5
    return "".join(chars)


class MonotonicULIDGenerator:
    """Generate sortable 26-character IDs with per-device monotonic ordering.

    The first 40 entropy bits are a stable device namespace and the remaining
    40 bits are random/counter entropy.  Different offline devices therefore
    do not share an ID namespace, while IDs from one generator remain strictly
    increasing when the wall clock is equal or moves backwards.
    """

    def __init__(
        self,
        device_id: str,
        *,
        clock_ms: Callable[[], int] | None = None,
        random_bits: Callable[[], int] | None = None,
    ) -> None:
        allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-"
        if not device_id or any(char not in allowed for char in device_id):
            raise ValueError("device_id contains unsafe characters")
        self._clock_ms = clock_ms or (lambda: time.time_ns() // 1_000_000)
        self._random_bits = random_bits or (lambda: secrets.randbits(40))
        self._namespace = int.from_bytes(hashlib.sha256(device_id.encode()).digest()[:5], "big")
        self._last_timestamp = -1
        self._last_entropy = -1
        self._lock = Lock()

    def new(self) -> str:
        with self._lock:
            timestamp = max(0, int(self._clock_ms()), self._last_timestamp)
            if timestamp > _MAX_TIMESTAMP:
                raise ValueError("ULID timestamp out of range")
            if timestamp == self._last_timestamp:
                entropy = self._last_entropy + 1
            else:
                entropy = self._random_bits() & ((1 << 40) - 1)
            if entropy >= 1 << 40:
                raise OverflowError("monotonic ULID entropy exhausted")
            self._last_timestamp = timestamp
            self._last_entropy = entropy
            return _encode(timestamp, 10) + _encode((self._namespace << 40) | entropy, 16)


class ThreadActivityEvent(BaseModel):
    """An immutable, append-only business event for one thread aggregate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = Field(default=1, frozen=True)
    event_id: str = Field(min_length=_ID_LENGTH, max_length=_ID_LENGTH, frozen=True)
    workspace_id: str = Field(min_length=1, max_length=128, frozen=True)
    device_id: str = Field(min_length=1, max_length=128, frozen=True)
    occurred_at: datetime = Field(frozen=True)
    kind: str = Field(min_length=1, max_length=128, frozen=True)
    aggregate_id: str = Field(min_length=1, max_length=256, frozen=True)
    payload: dict[str, Any] = Field(default_factory=dict, frozen=True)
    causation_operation_id: str = Field(min_length=1, max_length=256, frozen=True)

    @field_validator("event_id")
    @classmethod
    def _event_id_is_ulid(cls, value: str) -> str:
        if any(char not in _ALPHABET for char in value.upper()) or value != value.upper():
            raise ValueError("event_id 必须是大写 Crockford ULID")
        return value

    @field_validator("occurred_at")
    @classmethod
    def _occurred_at_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("occurred_at 必须包含时区")
        return value.astimezone(UTC)

    @field_validator("kind", "aggregate_id", "causation_operation_id")
    @classmethod
    def _text_is_single_line(cls, value: str) -> str:
        if not value.strip() or "\n" in value or "\r" in value:
            raise ValueError("event text field 无效")
        return value

    @field_validator("payload")
    @classmethod
    def _payload_is_json(cls, value: dict[str, Any]) -> dict[str, Any]:
        import json

        json.dumps(value, ensure_ascii=False, allow_nan=False)
        return value


@dataclass(frozen=True)
class ThreadActivityView:
    aggregate_id: str
    event_ids: tuple[str, ...]
    activity_count: int
    last_occurred_at: datetime
    last_kind: str
    last_payload: Mapping[str, Any]


def project_thread_activity(events: Iterable[ThreadActivityEvent]) -> dict[str, ThreadActivityView]:
    """Build a deterministic, idempotent projection from any event order."""
    unique: dict[str, ThreadActivityEvent] = {}
    for event in events:
        existing = unique.get(event.event_id)
        if existing is not None and existing != event:
            raise ValueError(f"event_id collision with different payload: {event.event_id}")
        unique[event.event_id] = event

    grouped: dict[str, list[ThreadActivityEvent]] = {}
    for event in sorted(unique.values(), key=lambda item: (item.occurred_at, item.event_id)):
        grouped.setdefault(event.aggregate_id, []).append(event)

    return {
        aggregate_id: ThreadActivityView(
            aggregate_id=aggregate_id,
            event_ids=tuple(event.event_id for event in aggregate_events),
            activity_count=len(aggregate_events),
            last_occurred_at=aggregate_events[-1].occurred_at,
            last_kind=aggregate_events[-1].kind,
            last_payload=dict(aggregate_events[-1].payload),
        )
        for aggregate_id, aggregate_events in sorted(grouped.items())
    }


def render_thread_activity_view(projection: Mapping[str, ThreadActivityView]) -> bytes:
    """Render the defined thread activity projection as stable JSON bytes.

    The checksum covers the projection document without its checksum field.  This
    makes a temporary rebuild independently verifiable while keeping output
    stable across event order, mapping order, and repeated runs.
    """
    aggregates = [
        {
            "aggregate_id": view.aggregate_id,
            "event_ids": list(view.event_ids),
            "activity_count": view.activity_count,
            "last_occurred_at": view.last_occurred_at.astimezone(UTC).isoformat(),
            "last_kind": view.last_kind,
            "last_payload": dict(view.last_payload),
        }
        for _, view in sorted(projection.items())
    ]
    document: dict[str, Any] = {
        "schema_version": 1,
        "projection": "thread-activity",
        "aggregates": aggregates,
    }
    canonical = json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    document["checksum"] = hashlib.sha256(canonical).hexdigest()
    return (
        json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


__all__ = [
    "MonotonicULIDGenerator",
    "ThreadActivityEvent",
    "ThreadActivityView",
    "project_thread_activity",
    "render_thread_activity_view",
]
