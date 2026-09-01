"""审批页单条变更单测：裁决切换 / 字段修改 / 错误处理。"""

from __future__ import annotations

from pathlib import Path

import pytest

from summit_workbench.domain.review import (
    ApprovalCandidate,
    CandidateDecision,
    CandidateKind,
    EvidenceRef,
    ReviewEntry,
    RouteTarget,
)
from summit_workbench.repositories.review_edit import (
    ReviewEditError,
    set_decision,
    update_fields,
)
from summit_workbench.repositories.review_page import (
    parse_review_page,
    render_review_page,
    review_path,
)


def _entry(cid: str = "m1#decision-0") -> ReviewEntry:
    candidate = ApprovalCandidate(
        candidate_id=cid,
        kind=CandidateKind.DECISION,
        description="采用双栏排版",
        target_project="HIC_SWB_LaTEX",
        route=RouteTarget.PROJECT_MAIN,
        evidence=EvidenceRef(anchor="00:12:30"),
        is_next_step=True,
    )
    return ReviewEntry(
        candidate=candidate,
        ai_original="采用双栏排版",
        meeting_date="2026-08-27",
        meeting_title="排版会",
        note_link="[[meetings/notes/2026-08-27-排版会.md]]",
        transcript_link="[[meetings/transcripts/2026-08-27-排版会-transcript.md]]",
    )


def _seed_page(vault: Path, entries: list[ReviewEntry]) -> Path:
    path = review_path(vault)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_review_page(entries), encoding="utf-8")
    return path


def test_set_decision_approves(tmp_path: Path) -> None:
    _seed_page(tmp_path, [_entry()])
    set_decision(tmp_path, "m1#decision-0", CandidateDecision.APPROVED)
    parsed = parse_review_page(review_path(tmp_path).read_text(encoding="utf-8"))
    assert parsed.entries[0].candidate.decision is CandidateDecision.APPROVED


def test_set_decision_reject_then_pending(tmp_path: Path) -> None:
    _seed_page(tmp_path, [_entry()])
    set_decision(tmp_path, "m1#decision-0", CandidateDecision.REJECTED)
    assert "#ignore" in review_path(tmp_path).read_text(encoding="utf-8")
    set_decision(tmp_path, "m1#decision-0", CandidateDecision.PENDING)
    parsed = parse_review_page(review_path(tmp_path).read_text(encoding="utf-8"))
    assert parsed.entries[0].candidate.decision is CandidateDecision.PENDING


def test_update_fields_changes_target_and_due(tmp_path: Path) -> None:
    _seed_page(tmp_path, [_entry()])
    update_fields(
        tmp_path,
        "m1#decision-0",
        target_project="HIC_Logistics",
        due_date="2026-09-10",
    )
    entry = parse_review_page(review_path(tmp_path).read_text(encoding="utf-8")).entries[0]
    assert entry.candidate.target_project == "HIC_Logistics"
    assert entry.candidate.due_date == "2026-09-10"
    # 未指定的字段保持不变
    assert entry.candidate.description == "采用双栏排版"


def test_edit_preserves_ai_original(tmp_path: Path) -> None:
    _seed_page(tmp_path, [_entry()])
    update_fields(tmp_path, "m1#decision-0", description="改成三栏")
    entry = parse_review_page(review_path(tmp_path).read_text(encoding="utf-8")).entries[0]
    assert entry.candidate.description == "改成三栏"
    assert entry.ai_original == "采用双栏排版"  # AI 原值不被用户修改覆盖


def test_missing_candidate_raises(tmp_path: Path) -> None:
    _seed_page(tmp_path, [_entry()])
    with pytest.raises(ReviewEditError, match="找不到候选"):
        set_decision(tmp_path, "nonexistent", CandidateDecision.APPROVED)


def test_missing_page_raises(tmp_path: Path) -> None:
    with pytest.raises(ReviewEditError, match="不存在"):
        set_decision(tmp_path, "m1#decision-0", CandidateDecision.APPROVED)
