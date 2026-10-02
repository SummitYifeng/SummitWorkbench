from __future__ import annotations

from pathlib import Path

import pytest

from summit_workbench.repositories.operation_receipts import (
    OperationConflict,
    OperationReceiptStore,
    _digest,
)


def test_receipt_replays_completed_response_without_running_action(tmp_path: Path) -> None:
    store = OperationReceiptStore("workspace-a", home=tmp_path)
    calls = 0

    def action() -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {"ok": True, "path": "logs/2026-10-02-001.md"}

    first = store.run("request-1", {"text": "note"}, action)
    second = store.run("request-1", {"text": "note"}, action)

    assert first.response == second.response
    assert first.replayed is False
    assert second.replayed is True
    assert calls == 1
    assert store.get("request-1")["status"] == "completed"  # type: ignore[index]


def test_request_id_cannot_be_reused_for_different_content(tmp_path: Path) -> None:
    store = OperationReceiptStore("workspace-a", home=tmp_path)
    store.run("request-1", {"text": "first"}, lambda: {"ok": True})

    with pytest.raises(OperationConflict):
        store.run("request-1", {"text": "second"}, lambda: {"ok": True})


def test_interrupted_operation_is_unknown_and_never_reexecuted(tmp_path: Path) -> None:
    store = OperationReceiptStore("workspace-a", home=tmp_path)
    key = store._key("request-1")
    with store._locked(key) as path:
        store._write(
            path,
            {
                "schema_version": 1,
                "request_id": "request-1",
                "request_digest": _digest({"text": "note"}),
                "status": "processing",
                "stage": "registered",
                "started_at": "2026-10-02T00:00:00+00:00",
                "updated_at": "2026-10-02T00:00:00+00:00",
            },
        )
    calls = 0

    def action() -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {"ok": True}

    result = store.run("request-1", {"text": "note"}, action)

    assert result.response["status"] == "unknown"
    assert result.response["ok"] is False
    assert calls == 0


def test_receipts_are_workspace_isolated_and_private(tmp_path: Path) -> None:
    first = OperationReceiptStore("workspace-a", home=tmp_path)
    second = OperationReceiptStore("workspace-b", home=tmp_path)
    first.run("same-id", {}, lambda: {"ok": True})

    assert second.get("same-id") is None
    receipt_dir = tmp_path / "Library/Application Support/SummitWorkbench"
    receipt_dir /= "profiles/workspace-a/runtime/operations"
    receipt = next(receipt_dir.glob("*.json"))
    assert receipt.stat().st_mode & 0o777 == 0o600
