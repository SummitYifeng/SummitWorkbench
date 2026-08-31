"""集中审批页刷新编排。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from summit_workbench.domain.review import ReviewEntry
from summit_workbench.repositories.meeting_archive import notes_dir
from summit_workbench.repositories.review_page import RefreshOutcome, refresh_review_page
from summit_workbench.repositories.vault import load_note
from summit_workbench.workflows.meetings.review_candidates import candidates_from_note


@dataclass(frozen=True)
class ReviewRefreshReport:
    outcome: RefreshOutcome
    notes_scanned: int
    candidates_found: int


def collect_pending_candidates(vault_dir: Path) -> tuple[list[ReviewEntry], int]:
    entries: list[ReviewEntry] = []
    scanned = 0
    for path in sorted(notes_dir(vault_dir).glob("*.md")):
        note = load_note(path)
        if note.parse_error is not None or note.meta.get("status") != "pending-review":
            continue
        scanned += 1
        entries.extend(candidates_from_note(path, vault_dir))
    return entries, scanned


def refresh_meeting_review(vault_dir: Path) -> ReviewRefreshReport:
    entries, scanned = collect_pending_candidates(vault_dir)
    outcome = refresh_review_page(vault_dir, entries)
    return ReviewRefreshReport(outcome, scanned, len(entries))
