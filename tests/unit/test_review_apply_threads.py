"""审批写回的知识线程落点（P0）：跟进事项 + 线程 inbox（无 Work 文件夹）。

需求再梳理 R4：他人行动项 → 主档案「跟进事项」责任记录（不进本人待办）；
未成熟想法 → 线程 inbox（vault 自建，仓库项目仍写文件夹 inbox）。
"""

from __future__ import annotations

from datetime import UTC, datetime

from summit_workbench.domain.review import (
    ApprovalCandidate,
    CandidateDecision,
    CandidateKind,
    EvidenceRef,
    ReviewEntry,
    RouteTarget,
)
from summit_workbench.repositories.review_page import parse_review_page, refresh_review_page
from summit_workbench.workflows.review_apply import apply_meeting_review


def _entry(
    stable_id: str,
    *,
    decision: CandidateDecision,
    route: RouteTarget,
    project: str = "T1",
    kind: CandidateKind = CandidateKind.ACTION_ITEM,
) -> ReviewEntry:
    candidate = ApprovalCandidate(
        candidate_id=stable_id,
        kind=kind,
        description=f"final-{stable_id}",
        target_project=project,
        route=route,
        evidence=EvidenceRef(anchor="木子 00:03"),
        is_next_step=True,
        decision=decision,
    )
    return ReviewEntry(
        candidate,
        f"original-{stable_id}",
        "2026-09-02",
        "沟通对齐会",
        "[[meetings/notes/note]]",
        "[[transcript]]",
    )


def _thread_main(vault, project: str = "T1", *, with_followup: bool = False) -> None:
    """知识线程档案：只建 vault 档案，不建任何 Work 文件夹（区别于仓库项目）。"""
    path = vault / "projects" / f"{project}.md"
    path.parent.mkdir(parents=True)
    followup = "\n\n## 跟进事项" if with_followup else ""
    path.write_text(
        f"---\nproject: {project}\ndate: 2026-09-01\ntype: project-main\nstatus: active\n"
        "---\n\n# T\n\n## 当前状态\n\n## 下一步\n\n## 阻塞\n\n## 决策记录"
        f"{followup}\n",
        encoding="utf-8",
    )


def _folder_project(work_root, project: str = "P1") -> None:
    """仓库项目：文件夹 + input/inbox.md（沿用既有约定）。"""
    path = work_root / project / "input" / "inbox.md"
    path.parent.mkdir(parents=True)
    path.write_text("# inbox\n\n## 待处理条目\n", encoding="utf-8")


def test_retired_followup_route_does_not_write_to_thread(tmp_path) -> None:
    vault = tmp_path / "vault"
    work = tmp_path / "work"
    _thread_main(vault)
    refresh_review_page(
        vault,
        [
            _entry(
                "m:n#action-item-0",
                decision=CandidateDecision.APPROVED,
                route=RouteTarget.PROJECT_FOLLOWUP,
            )
        ],
    )
    report = apply_meeting_review(vault, work, apply=True, now=datetime(2026, 9, 2, tzinfo=UTC))
    assert report.applied == 0
    assert report.failed == 1
    assert "已退役" in (report.actions[0].reason or "")
    body = (vault / "projects" / "T1.md").read_text(encoding="utf-8")
    assert "## 跟进事项" not in body
    assert "final-m:n#action-item-0" not in body


def test_retired_followup_route_does_not_change_old_archive(tmp_path) -> None:
    vault = tmp_path / "vault"
    work = tmp_path / "work"
    _thread_main(vault, with_followup=False)
    refresh_review_page(
        vault,
        [
            _entry(
                "m:n#action-item-1",
                decision=CandidateDecision.APPROVED,
                route=RouteTarget.PROJECT_FOLLOWUP,
            )
        ],
    )
    report = apply_meeting_review(vault, work, apply=True)
    assert report.applied == 0
    assert report.failed == 1
    assert "已退役" in (report.actions[0].reason or "")
    body = (vault / "projects" / "T1.md").read_text(encoding="utf-8")
    assert "## 跟进事项" not in body
    assert "final-m:n#action-item-1" not in body


def test_retired_thread_inbox_route_does_not_write(tmp_path) -> None:
    vault = tmp_path / "vault"
    work = tmp_path / "work"
    _thread_main(vault)
    refresh_review_page(
        vault,
        [
            _entry(
                "m:n#action-item-2",
                decision=CandidateDecision.APPROVED,
                route=RouteTarget.PROJECT_INBOX,
            )
        ],
    )
    report = apply_meeting_review(vault, work, apply=True)
    assert report.applied == 0
    assert report.failed == 1
    assert "已退役" in (report.actions[0].reason or "")
    assert not (vault / "inboxes" / "T1.md").exists()


def test_retired_folder_project_inbox_route_does_not_write(tmp_path) -> None:
    vault = tmp_path / "vault"
    work = tmp_path / "work"
    _thread_main(vault, project="P1")  # 档案存在（有文件夹时按文件夹走）
    _folder_project(work, "P1")
    folder_inbox = work / "P1" / "input" / "inbox.md"
    before = folder_inbox.read_bytes()
    refresh_review_page(
        vault,
        [
            _entry(
                "m:n#action-item-3",
                decision=CandidateDecision.APPROVED,
                route=RouteTarget.PROJECT_INBOX,
                project="P1",
            )
        ],
    )
    report = apply_meeting_review(vault, work, apply=True)
    assert report.applied == 0
    assert report.failed == 1
    assert "已退役" in (report.actions[0].reason or "")
    assert folder_inbox.read_bytes() == before
    assert not (vault / "inboxes" / "P1.md").exists()


def test_thread_inbox_requires_registered_archive(tmp_path) -> None:
    """线程 inbox 写回前要求线程已建档（不臆造项目）。"""
    vault = tmp_path / "vault"
    work = tmp_path / "work"
    refresh_review_page(
        vault,
        [
            _entry(
                "m:n#action-item-4",
                decision=CandidateDecision.APPROVED,
                route=RouteTarget.PROJECT_INBOX,
                project="Ghost",
            )
        ],
    )
    report = apply_meeting_review(vault, work, apply=True)
    assert report.applied == 0
    assert report.failed == 1
    assert "已退役" in (report.actions[0].reason or "")
    assert not (vault / "inboxes" / "Ghost.md").exists()


def test_thread_page_roundtrip_parses_new_route(tmp_path) -> None:
    """审批页往返（渲染→解析）对 project-followup route 稳定。"""
    vault = tmp_path / "vault"
    refresh_review_page(
        vault,
        [
            _entry(
                "m:n#action-item-5",
                decision=CandidateDecision.PENDING,
                route=RouteTarget.PROJECT_FOLLOWUP,
            )
        ],
    )
    parsed = parse_review_page((vault / "review" / "meetings.md").read_text(encoding="utf-8"))
    assert parsed.errors == []
    assert parsed.entries[0].candidate.route is RouteTarget.PROJECT_FOLLOWUP
