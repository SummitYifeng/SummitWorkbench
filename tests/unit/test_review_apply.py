"""M1-4：dry-run 默认、批准/拒绝审计、部分失败和幂等写回。"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from summit_workbench.domain.external_action import ExternalActionKind, ExternalActionState
from summit_workbench.domain.pipeline import MeetingTask, ProcessingState
from summit_workbench.domain.retrieval_contract import (
    is_fact_retrieval_eligible,
    validate_retrieval_readiness,
)
from summit_workbench.domain.review import (
    UNRESOLVED,
    ApprovalCandidate,
    CandidateDecision,
    CandidateKind,
    EvidenceRef,
    ReviewEntry,
    RouteTarget,
)
from summit_workbench.providers.feishu.errors import FeishuAPIError
from summit_workbench.repositories.external_action_outbox import latest_for_candidate
from summit_workbench.repositories.meeting_state import latest_task, record_task
from summit_workbench.repositories.review_audit import completed_ids
from summit_workbench.repositories.review_page import parse_review_page, refresh_review_page
from summit_workbench.repositories.vault import load_note
from summit_workbench.workflows.external_actions import mark_sending, mark_succeeded, prepare_action
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
    assert (vault / "review" / "meetings.md") in report.touched_paths
    assert (vault / "_signals" / "review-actions" / "log.jsonl") in report.touched_paths
    assert (vault / "_signals" / "meeting-state" / "log.jsonl") in report.touched_paths
    assert report.archive_path in report.touched_paths
    assert project in report.touched_paths
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


def test_unresolved_project_global_inbox_route_is_retired(tmp_path):
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
    report = apply_meeting_review(vault, work, apply=True)
    assert report.applied == 0
    assert report.failed == 1
    assert "已退役" in (report.actions[0].reason or "")
    assert not (vault / "inbox.md").exists()


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


def _meeting_entry(start_at: str | None = None, end_at: str | None = None) -> ReviewEntry:
    entry = _entry(
        "m:n#action-item-0",
        decision=CandidateDecision.APPROVED,
        route=RouteTarget.FEISHU_MEETING,
    )
    return replace(entry, candidate=replace(entry.candidate, start_at=start_at, end_at=end_at))


def test_retired_meeting_creation_route_is_blocked_without_external_call(tmp_path):
    vault = tmp_path / "vault"
    work = tmp_path / "work"
    refresh_review_page(vault, [_meeting_entry(start_at="2026-09-10T14:00")])
    report = apply_meeting_review(vault, work, apply=True)
    assert report.actions[0].executable is False
    assert "已退役" in (report.actions[0].reason or "")
    assert report.applied == 0


def test_feishu_timeout_is_unknown_and_second_apply_does_not_post_again(tmp_path):
    vault = tmp_path / "vault"
    work = tmp_path / "work"
    entry = _entry(
        "m:n#action-item-0",
        decision=CandidateDecision.APPROVED,
        route=RouteTarget.FEISHU_TASK,
        due="2026-09-04",
    )
    refresh_review_page(vault, [entry])
    calls = 0

    def timeout_creator(title: str, due: str | None, candidate_id: str) -> str:
        nonlocal calls
        calls += 1
        raise FeishuAPIError("请求超时", result_unknown=True)

    first = apply_meeting_review(vault, work, apply=True, task_creator=timeout_creator)
    second = apply_meeting_review(vault, work, apply=True, task_creator=timeout_creator)
    action = latest_for_candidate(vault, entry.candidate.candidate_id)
    assert first.failed == 1
    assert second.failed == 1
    assert calls == 1
    assert action is not None
    assert action.state is ExternalActionState.UNKNOWN
    assert "核对" in (
        parse_review_page((vault / "review" / "meetings.md").read_text(encoding="utf-8"))
        .entries[0]
        .apply_error
        or ""
    )


def test_one_feishu_error_does_not_block_next_external_action(tmp_path):
    vault = tmp_path / "vault"
    work = tmp_path / "work"
    first = _entry(
        "m:n#action-item-0",
        decision=CandidateDecision.APPROVED,
        route=RouteTarget.FEISHU_TASK,
    )
    second = _entry(
        "m:n#action-item-1",
        decision=CandidateDecision.APPROVED,
        route=RouteTarget.FEISHU_TASK,
    )
    refresh_review_page(vault, [first, second])
    calls: list[str] = []

    def creator(title: str, due: str | None, candidate_id: str) -> str:
        calls.append(candidate_id)
        if candidate_id.endswith("item-0"):
            raise FeishuAPIError("权限不足")
        return "task-2"

    report = apply_meeting_review(vault, work, apply=True, task_creator=creator)
    assert report.failed == 1
    assert report.applied == 1
    assert calls == [first.candidate.candidate_id, second.candidate.candidate_id]


def test_succeeded_outbox_reuses_remote_id_without_creator_call(tmp_path):
    vault = tmp_path / "vault"
    work = tmp_path / "work"
    entry = _entry(
        "m:n#action-item-0",
        decision=CandidateDecision.APPROVED,
        route=RouteTarget.FEISHU_TASK,
    )
    refresh_review_page(vault, [entry])
    prepared = prepare_action(
        vault,
        candidate_id=entry.candidate.candidate_id,
        kind=ExternalActionKind.FEISHU_TASK,
        request={
            "description": entry.candidate.description,
            "target_project": entry.candidate.target_project,
            "due_date": entry.candidate.due_date,
        },
        target_account_ref="feishu:user",
    )
    mark_succeeded(vault, mark_sending(vault, prepared), "already-created")
    calls = 0

    def creator(title: str, due: str | None, candidate_id: str) -> str:
        nonlocal calls
        calls += 1
        return "must-not-be-used"

    report = apply_meeting_review(vault, work, apply=True, task_creator=creator)
    assert report.applied == 1
    assert calls == 0


def test_remote_success_with_local_accounting_failure_is_not_retried(tmp_path, monkeypatch):
    """远端已返回 ID 后，本地记账异常不能把动作标成可重发的 failed。"""
    vault = tmp_path / "vault"
    work = tmp_path / "work"
    entry = _entry(
        "m:n#action-item-0",
        decision=CandidateDecision.APPROVED,
        route=RouteTarget.FEISHU_TASK,
    )
    refresh_review_page(vault, [entry])
    calls = 0

    def creator(title: str, due: str | None, candidate_id: str) -> str:
        nonlocal calls
        calls += 1
        return "created-before-accounting-error"

    import summit_workbench.workflows.review_apply as review_apply_module

    def accounting_failure(*args, **kwargs):
        raise OSError("账本暂时不可写")

    monkeypatch.setattr(review_apply_module, "mark_succeeded", accounting_failure)
    first = apply_meeting_review(vault, work, apply=True, task_creator=creator)
    second = apply_meeting_review(vault, work, apply=True, task_creator=creator)

    action = latest_for_candidate(vault, entry.candidate.candidate_id)
    assert first.failed == 1
    assert second.failed == 1
    assert calls == 1
    assert action is not None
    assert action.state in {ExternalActionState.SENDING, ExternalActionState.UNKNOWN}


# ---- T3：审批后状态收口与事实资格 ----


def _meeting_note_file(vault, project: str = "P1"):
    path = vault / "meetings" / "notes" / "note.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        "date: 2026-08-31\n"
        "type: meeting-note\n"
        "status: pending-review\n"
        "transcript: '[[2026-08-31-评审会-transcript]]'\n"
        f"projects:\n- {project}\n"
        "---\n\n"
        "# 评审会\n\n"
        "## 一分钟摘要\n\nx\n\n## 会议信息\n\nx\n\n## 事实与进展\n\nx\n\n"
        "## 已形成决策\n\nx\n\n## 明确行动项\n\nx\n\n## 未决问题\n\nx\n\n"
        "## AI 建议\n\nx\n\n## 关联项目\n\n"
        f"- {project}\n\n## 证据索引\n\nx\n",
        encoding="utf-8",
    )
    return path


def test_approved_meeting_note_moves_pending_review_to_applied(tmp_path):
    """pending-review 不是事实语料；批准后状态稳定变为 applied、恢复事实资格。"""
    vault = tmp_path / "vault"
    work = tmp_path / "work"
    _project_main(vault)
    note_path = _meeting_note_file(vault)
    refresh_review_page(
        vault,
        [
            _entry(
                "m:n#decision-0",
                decision=CandidateDecision.APPROVED,
                route=RouteTarget.PROJECT_MAIN,
                kind=CandidateKind.DECISION,
            )
        ],
    )
    _pending(vault)
    before = load_note(note_path)
    assert before.meta["status"] == "pending-review"
    assert is_fact_retrieval_eligible(before.meta) is False
    assert validate_retrieval_readiness(before.meta, before.body) == []

    report = apply_meeting_review(
        vault, work, apply=True, now=datetime(2026, 8, 31, 12, tzinfo=UTC)
    )
    assert report.applied == 1
    after = load_note(note_path)
    assert after.meta["status"] == "applied"
    assert is_fact_retrieval_eligible(after.meta) is True
    assert after.body == before.body  # 状态收口只改 frontmatter，正文原样保留


def test_all_rejected_meeting_note_still_becomes_applied(tmp_path):
    """契约 §9.1 没有"全部拒绝"例外：应用后笔记一律 applied，不因全否而踢出检索。

    2026-09-19 修正：此前用「本批历史上有没有 approved」决定**整篇笔记**的 status，
    把 AI 的行动项全否掉会连带摘要与事实一起离开语料。现在「全部被拒」只如实记录在
    review/archive（裁决=rejected）与 _signals/meeting-state/log.jsonl（终态 ignored）。
    """
    vault = tmp_path / "vault"
    work = tmp_path / "work"
    _project_main(vault)
    note_path = _meeting_note_file(vault)
    refresh_review_page(
        vault,
        [
            _entry(
                "m:n#action-item-0",
                decision=CandidateDecision.REJECTED,
                route=RouteTarget.PROJECT_MAIN,
            ),
            _entry(
                "m:n#action-item-1",
                decision=CandidateDecision.REJECTED,
                route=RouteTarget.PROJECT_MAIN,
            ),
        ],
    )
    _pending(vault)

    report = apply_meeting_review(
        vault, work, apply=True, now=datetime(2026, 8, 31, 12, tzinfo=UTC)
    )
    assert report.rejected == 2
    assert report.applied == 0

    # 笔记：applied（重新构成事实语料），正文未被改动。
    after = load_note(note_path)
    assert after.meta["status"] == "applied"
    assert is_fact_retrieval_eligible(after.meta) is True
    # 任务状态：如实记录"全部被拒" → ignored（不再决定笔记去留）。
    task = latest_task(vault, "m:n")
    assert task is not None and task.state is ProcessingState.IGNORED
    # 审计归档：两条 rejected 裁决留痕（"全部被拒"的事实仍可回溯）。
    assert report.archive_path is not None
    audit = report.archive_path.read_text(encoding="utf-8")
    assert audit.count("rejected") >= 2
