from __future__ import annotations

import pytest

from summit_workbench.domain.sync import SyncState
from summit_workbench.domain.sync_conflict import (
    ConflictAction,
    ConflictKind,
    classify_conflict_path,
    explain_conflict,
)


def test_conflict_categories_have_safe_actions() -> None:
    event = classify_conflict_path("_events/device-a/2026/09/event.json")
    view = classify_conflict_path("_views/thread-a.json")
    markdown = classify_conflict_path("logs/2026-09-07-001.md")
    binary = classify_conflict_path("assets/archive.zip")

    assert (event.kind, event.action, event.automatic) == (
        ConflictKind.APPEND_ONLY_EVENT,
        ConflictAction.AUTO_COLLECT,
        True,
    )
    assert (view.kind, view.action, view.automatic) == (
        ConflictKind.GENERATED_VIEW,
        ConflictAction.REBUILD,
        True,
    )
    assert markdown.kind is ConflictKind.MANUAL_MARKDOWN
    assert binary.action is ConflictAction.PRESERVE_BOTH


def test_explanation_is_sorted_and_requires_manual_for_mixed_paths() -> None:
    explanation = explain_conflict(
        SyncState.DIVERGED_PROTECTED,
        ["z.md", "_events/device-a/2026/09/event.json", "a.bin"],
    )

    assert [item.path for item in explanation.items] == [
        "_events/device-a/2026/09/event.json",
        "a.bin",
        "z.md",
    ]
    assert explanation.auto_mergeable is False
    assert explanation.manual_required is True
    assert explanation.as_dict()["state"] == "diverged-protected"


@pytest.mark.parametrize("path", ["/tmp/x.md", "../x.md", "_events/../x.json", "x\x00.md"])
def test_conflict_paths_cannot_escape_vault(path: str) -> None:
    with pytest.raises(ValueError):
        classify_conflict_path(path)
