"""M1-4：只从明确决策/行动项生成稳定候选，普通事实不升级。"""

from __future__ import annotations

from summit_workbench.domain.meeting import (
    ActionItem,
    Decision,
    MeetingExtraction,
    SourcedStatement,
)
from summit_workbench.domain.pipeline import SourceKind
from summit_workbench.domain.review import CandidateKind, RouteTarget
from summit_workbench.repositories.meeting_note import MeetingNoteInput, archive_meeting_note
from summit_workbench.workflows.meetings.review_candidates import candidates_from_note


def _note(tmp_path):
    extraction = MeetingExtraction(
        one_minute_summary="摘要",
        facts=[SourcedStatement(text="事实不能升级", evidence="张三 00:01")],
        decisions=[Decision(description="采用 A", target_project="P1", evidence="李四 00:02")],
        action_items=[
            ActionItem(description="内部推进", target_project="P1", evidence="王五 00:03"),
            ActionItem(
                description="周五交付",
                target_project="P2",
                due_date="2026-09-04",
                evidence="赵六 00:04",
            ),
            ActionItem(description="待定归属", evidence="段落 5"),
        ],
    )
    return archive_meeting_note(
        tmp_path,
        MeetingNoteInput(
            date="2026-08-31",
            title="评审会",
            idem_key="m:n",
            extraction=extraction,
            source=SourceKind.FEISHU_NOTE,
            transcript_stem="2026-08-31-评审会-transcript",
            model_id="m",
            prompt_version="p@v2",
        ),
    ).path


def test_generates_decisions_and_actions_only_with_stable_routes(tmp_path):
    entries = candidates_from_note(_note(tmp_path), tmp_path)
    assert len(entries) == 4
    assert [entry.candidate.kind for entry in entries] == [
        CandidateKind.DECISION,
        CandidateKind.ACTION_ITEM,
        CandidateKind.ACTION_ITEM,
        CandidateKind.ACTION_ITEM,
    ]
    assert entries[0].candidate.candidate_id == "m:n#decision-0"
    assert entries[0].candidate.route == RouteTarget.PROJECT_MAIN
    assert entries[1].candidate.route == RouteTarget.PROJECT_MAIN
    assert entries[2].candidate.route == RouteTarget.FEISHU_TASK
    assert entries[3].candidate.route == RouteTarget.GLOBAL_INBOX
    assert entries[3].candidate.is_actionable() is False


def test_existing_note_without_embedded_extraction_uses_body_fallback(tmp_path):
    path = _note(tmp_path)
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = lines.index("extraction:")
    end = start + 1
    while end < len(lines) and (lines[end].startswith("  ") or not lines[end].strip()):
        end += 1
    path.write_text("\n".join([*lines[:start], *lines[end:]]) + "\n", encoding="utf-8")
    entries = candidates_from_note(path, tmp_path)
    assert len(entries) == 4
    assert entries[2].candidate.due_date == "2026-09-04"
