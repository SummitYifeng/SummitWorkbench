"""M1-4：dry-run 默认、批准/拒绝审计、部分失败和幂等写回。"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from summit_workbench.domain.pipeline import MeetingTask, ProcessingState
from summit_workbench.domain.review import (
    UNRESOLVED,
    ApprovalCandidate,
    CandidateDecision,
    CandidateKind,
    EvidenceRef,
    ReviewEntry,
    RouteTarget,
)
from summit_workbench.repositories.meeting_state import latest_task, record_task
from summit_workbench.repositories.review_audit import completed_ids
from summit_workbench.repositories.review_page import parse_review_page, refresh_review_page
from summit_workbench.workflows.review_apply import apply_meeting_review


def _entry(
    stable_id: str,
    *,
    decision: CandidateDecision,
    route: RouteTarget,
    project: str = "P1",
    kind: CandidateKind = CandidateKind.ACTION_ITEM,
    due: str | None = None,
) -> ReviewEntry:
    candidate = ApprovalCandidate(
        candidate_id=stable_id,
        kind=kind,
        description=f"final-{stable_id}",
        target_project=project,
        route=route,
        evidence=EvidenceRef(anchor="张三 00:03"),
        due_date=due,
        is_next_step=True,
        decision=decision,
    )
    return ReviewEntry(
        candidate,
        f"original-{stable_id}",
        "2026-08-31",
        "评审会",
        "[[meetings/notes/note]]",
        "[[transcript]]",
    )


def _project_main(vault, project: str = "P1"):
    path = vault / "projects" / f"{project}.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        f"---\nproject: {project}\ndate: 2026-08-31\ntype: project-main\nstatus: active\n"
        "---\n\n# P\n\n## 当前状态\n\n## 下一步\n\n## 阻塞\n\n## 决策记录\n",
        encoding="utf-8",
    )
    return path


def _pending(vault, key: str = "m:n"):
    task = MeetingTask.for_remote("m", "n", state=ProcessingState.PROCESSED).advanced_to(
        ProcessingState.PENDING_REVIEW
    )
    assert task.idem_key == key
    record_task(vault, task)


def test_dry_run_has_zero_writes(tmp_path):
    vault = tmp_path / "vault"
    work = tmp_path / "work"
    project = _project_main(vault)
    refresh_review_page(
        vault,
        [
            _entry(
                "m:n#action-item-0",
                decision=CandidateDecision.APPROVED,
                route=RouteTarget.PROJECT_MAIN,
            )
        ],
    )
    before = project.read_text(encoding="utf-8")
    report = apply_meeting_review(vault, work)
    assert report.dry_run is True
    assert report.actions[0].executable is True
    assert project.read_text(encoding="utf-8") == before
    assert completed_ids(vault) == set()


def test_apply_local_and_reject_archives_audit_and_advances_state(tmp_path):
    vault = tmp_path / "vault"
    work = tmp_path / "work"
    project = _project_main(vault)
    approved = _entry(
        "m:n#decision-0",
        decision=CandidateDecision.APPROVED,
        route=RouteTarget.PROJECT_MAIN,
        kind=CandidateKind.DECISION,
    )
    rejected = _entry(
        "m:n#action-item-0",
        decision=CandidateDecision.REJECTED,
        route=RouteTarget.PROJECT_MAIN,
    )
    refresh_review_page(vault, [approved, rejected])
    _pending(vault)
    now = datetime(2026, 8, 31, 12, tzinfo=UTC)
    report = apply_meeting_review(vault, work, apply=True, now=now)
    assert report.applied == 1
    assert report.rejected == 1
    assert report.failed == 0
    assert "final-m:n#decision-0" in project.read_text(encoding="utf-8")
    assert report.archive_path is not None
    audit = report.archive_path.read_text(encoding="utf-8")
    assert "original-m:n#decision-0" in audit
    assert "final-m:n#decision-0" in audit
    assert completed_ids(vault) == {"m:n#decision-0", "m:n#action-item-0"}
    assert latest_task(vault, "m:n").state == ProcessingState.APPLIED  # type: ignore[union-attr]
    active = parse_review_page((vault / "review" / "meetings.md").read_text(encoding="utf-8"))
    assert active.entries == []


def test_feishu_creator_and_partial_failure_keep_failed_item(tmp_path):
    vault = tmp_path / "vault"
    work = tmp_path / "work"
    _project_main(vault)
    good = _entry(
        "m:n#action-item-0",
        decision=CandidateDecision.APPROVED,
        route=RouteTarget.FEISHU_TASK,
        due="2026-09-04",
    )
    bad = _entry(
        "m:n#action-item-1",
        decision=CandidateDecision.APPROVED,
        route=RouteTarget.PROJECT_MAIN,
        project="missing",
    )
    refresh_review_page(vault, [good, bad])
    created: list[tuple[str, str | None, str]] = []

    def create(title: str, due: str | None, stable_id: str) -> str:
        created.append((title, due, stable_id))
        return "task-123"

    report = apply_meeting_review(vault, work, apply=True, task_creator=create)
    assert report.applied == 1
    assert report.failed == 1
    assert created[0][1] == "2026-09-04"
    parsed = parse_review_page((vault / "review" / "meetings.md").read_text(encoding="utf-8"))
    assert [entry.candidate.candidate_id for entry in parsed.entries] == ["m:n#action-item-1"]
    assert parsed.entries[0].apply_error is not None
    assert "不存在" in parsed.entries[0].apply_error


def _project_with_alias(vault, project: str, alias: str):
    path = vault / "projects" / f"{project}.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        f"---\nproject: {project}\ndate: 2026-08-31\ntype: project-main\nstatus: active\n"
        f"aliases: [{alias}]\n---\n\n# P\n\n## 当前状态\n\n## 下一步\n\n## 阻塞\n\n## 决策记录\n",
        encoding="utf-8",
    )
    return path


def test_apply_resolves_natural_language_project_alias_to_canonical(tmp_path):
    vault = tmp_path / "vault"
    work = tmp_path / "work"
    project = _project_with_alias(vault, "HIC_WebClass_Chinese_Final", "网课系统")
    # 审批页里目标写成自然语言别名（模拟人工在审批页填写）
    entry = _entry(
        "m:n#decision-0",
        decision=CandidateDecision.APPROVED,
        route=RouteTarget.PROJECT_MAIN,
        kind=CandidateKind.DECISION,
        project="网课系统",
    )
    refresh_review_page(vault, [entry])
    _pending(vault)
    report = apply_meeting_review(vault, work, apply=True)
    assert report.applied == 1
    assert report.failed == 0
    assert "final-m:n#decision-0" in project.read_text(encoding="utf-8")


def test_unresolved_project_applies_to_autocreated_global_inbox(tmp_path):
    vault = tmp_path / "vault"
    work = tmp_path / "work"
    # 未匹配项目：目标 unresolved、route 全局 inbox，vault 尚无 inbox.md。
    entry = _entry(
        "m:n#action-item-0",
        decision=CandidateDecision.APPROVED,
        route=RouteTarget.GLOBAL_INBOX,
        project=UNRESOLVED,
    )
    refresh_review_page(vault, [entry])
    _pending(vault)
    report = apply_meeting_review(vault, work, apply=True)
    assert report.applied == 1
    assert report.failed == 0
    inbox = vault / "inbox.md"
    assert inbox.is_file()  # 兜底落点按需自建
    assert "final-m:n#action-item-0" in inbox.read_text(encoding="utf-8")


def test_missing_project_target_stays_with_actionable_hint(tmp_path):
    vault = tmp_path / "vault"
    work = tmp_path / "work"
    entry = _entry(
        "m:n#action-item-0",
        decision=CandidateDecision.APPROVED,
        route=RouteTarget.PROJECT_MAIN,
        project="HIC_NotCreatedYet",
    )
    refresh_review_page(vault, [entry])
    report = apply_meeting_review(vault, work)  # dry-run
    assert report.actions[0].executable is False
    assert "wb project new" in (report.actions[0].reason or "")


def test_completed_ledger_makes_reintroduced_candidate_idempotent(tmp_path):
    vault = tmp_path / "vault"
    work = tmp_path / "work"
    project = _project_main(vault)
    entry = _entry(
        "m:n#action-item-0",
        decision=CandidateDecision.APPROVED,
        route=RouteTarget.PROJECT_MAIN,
    )
    refresh_review_page(vault, [entry])
    apply_meeting_review(vault, work, apply=True)
    first = project.read_text(encoding="utf-8")
    refresh_review_page(vault, [replace(entry)])
    second = apply_meeting_review(vault, work, apply=True)
    assert second.applied == 0
    assert project.read_text(encoding="utf-8") == first
