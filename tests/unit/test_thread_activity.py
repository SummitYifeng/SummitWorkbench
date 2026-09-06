from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from summit_workbench.domain.thread_activity import (
    MonotonicULIDGenerator,
    ThreadActivityEvent,
    project_thread_activity,
)
from summit_workbench.repositories.thread_activity_events import (
    ThreadActivityEventStore,
    ThreadActivityStoreError,
)


def _event(
    index: int, aggregate_id: str, offset: int, kind: str = "thread.note.added"
) -> ThreadActivityEvent:
    return ThreadActivityEvent(
        event_id=MonotonicULIDGenerator(f"device-{index}", clock_ms=lambda: index).new(),
        workspace_id="workspace-1",
        device_id="device-1",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=offset),
        kind=kind,
        aggregate_id=aggregate_id,
        payload={"index": index, "offset": offset},
        causation_operation_id=f"operation-{index}",
    )


@given(st.lists(st.integers(min_value=0, max_value=100), min_size=1, max_size=80))
def test_monotonic_ids_are_sorted_even_when_clock_moves_backwards(clock_values: list[int]) -> None:
    values = iter(clock_values)
    generator = MonotonicULIDGenerator("device-1", clock_ms=lambda: next(values))
    ids = [generator.new() for _ in clock_values]
    assert ids == sorted(ids)
    assert len(ids) == len(set(ids))


def test_offline_devices_have_distinct_id_namespaces_with_same_clock_and_entropy() -> None:
    first = MonotonicULIDGenerator("device-a", clock_ms=lambda: 1, random_bits=lambda: 7)
    second = MonotonicULIDGenerator("device-b", clock_ms=lambda: 1, random_bits=lambda: 7)
    assert first.new() != second.new()


@given(
    st.lists(
        st.tuples(
            st.sampled_from(["thread-a", "thread-b", "thread-c"]),
            st.integers(min_value=0, max_value=8),
            st.sampled_from(["thread.note.added", "thread.status.changed"]),
        ),
        min_size=0,
        max_size=10,
    )
)
def test_projection_is_deterministic_for_reordered_and_duplicated_events(
    values: list[tuple[str, int, str]],
) -> None:
    events = [
        _event(index, aggregate, offset, kind)
        for index, (aggregate, offset, kind) in enumerate(values)
    ]
    expected = project_thread_activity(events)
    assert project_thread_activity(list(reversed(events))) == expected
    assert project_thread_activity([*events, *events]) == expected


def test_event_model_is_frozen_and_store_is_idempotent_but_not_overwritable(
    tmp_path: Path,
) -> None:
    store = ThreadActivityEventStore(
        tmp_path / "vault", workspace_id="workspace-1", device_id="device-1"
    )
    event = store.new_event(
        kind="thread.note.added",
        aggregate_id="thread-a",
        payload={"text": "kept"},
        causation_operation_id="operation-1",
    )
    path = store.append(event)
    expected_parent = (
        store.root / event.occurred_at.strftime("%Y") / event.occurred_at.strftime("%m")
    )
    assert path.parent == expected_parent
    assert store.append(event) == path
    assert store.read_events() == [event]
    assert store.project()["thread-a"].event_ids == (event.event_id,)
    with pytest.raises((TypeError, ValidationError)):
        event.kind = "thread.changed"

    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ThreadActivityStoreError):
        store.read_events()


def test_store_rejects_scope_mismatch_and_projection_preserves_last_event(tmp_path: Path) -> None:
    store = ThreadActivityEventStore(
        tmp_path / "vault", workspace_id="workspace-1", device_id="device-1"
    )
    other = ThreadActivityEvent(
        event_id=MonotonicULIDGenerator("device-2", clock_ms=lambda: 2).new(),
        workspace_id="workspace-1",
        device_id="device-2",
        occurred_at=datetime(2026, 1, 1, 0, 0, 2, tzinfo=UTC),
        kind="thread.status.changed",
        aggregate_id="thread-a",
        payload={"status": "active"},
        causation_operation_id="operation-2",
    )
    with pytest.raises(ThreadActivityStoreError):
        store.append(other)

    first = _event(1, "thread-a", 1)
    last = _event(2, "thread-a", 2, "thread.status.changed")
    view = project_thread_activity([last, first])["thread-a"]
    assert view.activity_count == 2
    assert view.last_kind == "thread.status.changed"
    assert view.last_payload["index"] == 2
