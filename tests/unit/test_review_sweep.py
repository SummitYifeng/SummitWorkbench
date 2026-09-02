"""``wb review sweep``：一键退役测试/旧会议（笔记置 ignored + 候选批量拒绝）。"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from summit_workbench.domain.meeting import (
    ActionItem,
    Decision,
    MeetingExtraction,
    SourcedStatement,
)
from summit_workbench.domain.pipeline import MeetingTask, ProcessingState, SourceKind
from summit_workbench.repositories.meeting_note import MeetingNoteInput, archive_meeting_note
from summit_workbench.repositories.meeting_state import latest_task, record_task
from summit_workbench.repositories.review_page import (
    parse_review_page,
    refresh_review_page,
    review_path,
)
from summit_workbench.workflows.meetings.review_candidates import candidates_from_note
from summit_workbench.workflows.review_sweep import sweep_meeting_review


def _note(vault, day: str, idem_key: str, title: str = "测试会") -> Path:
    extraction = MeetingExtraction(
        one_minute_summary="摘要",
        facts=[SourcedStatement(text="事实甲", evidence="张三 00:01")],
        decisions=[Decision(description="采用方案 A", target_project=None, evidence="李四 00:02")],
        action_items=[
            ActionItem(description="内部推进", target_project=None, evidence="王五 00:03"),
        ],
    )
    return archive_meeting_note(
        vault,
        MeetingNoteInput(
            date=day,
            title=title,
            idem_key=idem_key,
            extraction=extraction,
            source=SourceKind.FEISHU_NOTE,
            transcript_stem=f"{day}-{title}-transcript",
            model_id="m",
            prompt_version="p@v3",
        ),
    ).path


def _seed_page(vault) -> None:
    entries = []
    for path in sorted((vault / "meetings" / "notes").glob("*.md")):
        entries.extend(candidates_from_note(path, vault))
    refresh_review_page(vault, entries)


def _pending_task(vault, meeting_id: str, note_id: str) -> None:
    task = MeetingTask.for_remote(meeting_id, note_id, state=ProcessingState.PROCESSED).advanced_to(
        ProcessingState.PENDING_REVIEW
    )
    record_task(vault, task)


def _note_status(vault, path) -> str:
    from summit_workbench.repositories.vault import load_note

    return str(load_note(path).meta.get("status"))


def test_sweep_dry_run_zero_writes(tmp_path) -> None:
    vault = tmp_path / "vault"
    note_a = _note(vault, "2026-07-01", "m1:n1", "七月测试")
    note_b = _note(vault, "2026-08-20", "m2:n2", "八月测试")
    _seed_page(vault)
    page_before = review_path(vault).read_text(encoding="utf-8")

    report = sweep_meeting_review(vault)
    assert report.dry_run is True
    assert sorted(p.name for p in report.notes) == sorted([note_a.name, note_b.name])
    assert report.candidates == 4

    # 零写入：页面与笔记状态都未动
    assert review_path(vault).read_text(encoding="utf-8") == page_before
    assert _note_status(vault, note_a) == "pending-review"
    assert _note_status(vault, note_b) == "pending-review"


def test_sweep_apply_retires_notes_and_rejects_candidates(tmp_path) -> None:
    vault = tmp_path / "vault"
    note_a = _note(vault, "2026-07-01", "m1:n1", "七月测试")
    _pending_task(vault, "m1", "n1")
    _seed_page(vault)
    body_before = note_a.read_text(encoding="utf-8").split("---\n\n", 1)[1]

    report = sweep_meeting_review(vault, apply=True, now=datetime.now(UTC))
    assert report.dry_run is False
    assert len(report.notes) == 1
    assert report.candidates == 2

    # 笔记状态置 ignored、正文保留（只动 frontmatter status）
    assert _note_status(vault, note_a) == "ignored"
    assert "采用方案 A" in note_a.read_text(encoding="utf-8")
    assert note_a.read_text(encoding="utf-8").split("---\n\n", 1)[1] == body_before

    # 审批页候选全部置为拒绝
    parsed = parse_review_page(review_path(vault).read_text(encoding="utf-8"))
    assert len(parsed.entries) == 2
    assert all(e.candidate.decision.value == "rejected" for e in parsed.entries)

    # 任务状态收口为 ignored
    task = latest_task(vault, "m1:n1")
    assert task is not None
    assert task.state is ProcessingState.IGNORED


def test_sweep_before_filters_old_notes_only(tmp_path) -> None:
    vault = tmp_path / "vault"
    _note(vault, "2026-07-01", "m1:n1", "七月测试")
    _note(vault, "2026-08-20", "m2:n2", "八月测试")
    _seed_page(vault)

    report = sweep_meeting_review(vault, before=date(2026, 8, 1))
    assert [p.name for p in report.notes] == ["2026-07-01-七月测试.md"]
    assert report.candidates == 2


def test_sweep_apply_with_empty_page_still_retires_notes(tmp_path) -> None:
    vault = tmp_path / "vault"
    note = _note(vault, "2026-07-01", "m1:n1", "七月测试")

    report = sweep_meeting_review(vault, apply=True)
    assert report.candidates == 0
    assert _note_status(vault, note) == "ignored"
