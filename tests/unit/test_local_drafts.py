from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from summit_workbench.repositories.local_drafts import DraftValidationError, LocalDraftStore


def test_local_draft_is_workspace_scoped_and_private(tmp_path: Path) -> None:
    first = LocalDraftStore("workspace-a", home=tmp_path)
    second = LocalDraftStore("workspace-b", home=tmp_path)
    saved = first.save("journal-log", "today", {"did": "keep going", "projects": []})

    assert first.get("journal-log", "today") == saved
    assert second.get("journal-log", "today") is None
    stored = next(first.directory.glob("*.json"))
    assert stored.stat().st_mode & 0o777 == 0o600
    assert first.directory.stat().st_mode & 0o777 == 0o700


def test_draft_expires_seven_days_after_edit_without_read_renewal(tmp_path: Path) -> None:
    store = LocalDraftStore("workspace-a", home=tmp_path)
    edited = datetime(2026, 10, 1, tzinfo=UTC)
    store.save("journal-thought", "entry-1", {"problem": "why"}, now=edited)

    assert store.get("journal-thought", "entry-1", now=edited + timedelta(days=6)) is not None
    assert store.get("journal-thought", "entry-1", now=edited + timedelta(days=8)) is None
    assert store.list(now=edited + timedelta(days=8)) == []


@pytest.mark.parametrize(
    "value",
    [
        {"problem": "why", "api_key": "secret"},
        {"problem": "why", "file": "upload payload"},
        {"problem": 3},
    ],
)
def test_draft_rejects_non_whitelisted_or_invalid_fields(tmp_path: Path, value: object) -> None:
    store = LocalDraftStore("workspace-a", home=tmp_path)
    with pytest.raises(DraftValidationError):
        store.save("journal-thought", "entry-1", value)


def test_draft_rejects_unknown_types_and_unsafe_ids(tmp_path: Path) -> None:
    store = LocalDraftStore("workspace-a", home=tmp_path)
    with pytest.raises(DraftValidationError):
        store.save("credentials", "entry-1", {})
    with pytest.raises(DraftValidationError):
        store.save("journal-log", "../elsewhere", {"did": "x"})
