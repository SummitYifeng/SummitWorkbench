"""改进 2：审批应用成功后把来源会议笔记的 unresolved 解析为实际写回项目。

效果：会议笔记从此进入对应项目的线视图时间线，Obsidian 图谱里连上项目主档案。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from summit_workbench.domain.review import (
    UNRESOLVED,
    ApprovalCandidate,
    CandidateDecision,
    CandidateKind,
    EvidenceRef,
    ReviewEntry,
    RouteTarget,
)
from summit_workbench.repositories.review_audit import append_execution, make_execution_record
from summit_workbench.repositories.review_page import refresh_review_page
from summit_workbench.repositories.vault import load_note
from summit_workbench.workflows.review_apply import apply_meeting_review

_NOTE_REL = "meetings/notes/2026-09-02-沟通对齐会"


def _meeting_note(vault: Path) -> None:
    path = vault / f"{_NOTE_REL}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        "date: 2026-09-02\n"
        "type: meeting-note\n"
        "status: pending-review\n"
        "idem_key: 'm:n'\n"
        "transcript: '[[2026-09-02-沟通对齐会-transcript]]'\n"
        "projects:\n"
        "- unresolved\n"
        "---\n\n"
        "# 沟通对齐会\n\n"
        "## 一分钟摘要\n\n摘\n\n"
        "## 会议信息\n\n- 原文：[[2026-09-02-沟通对齐会-transcript]]\n\n"
        "## 事实与进展\n\n"
        "## 已形成决策\n\n"
        "## 明确行动项\n\n"
        "## 未决问题\n\n"
        "## AI 建议\n\n"
        "## 关联项目\n\n- unresolved\n\n"
        "## 证据索引\n\n- [[2026-09-02-沟通对齐会-transcript]] · 木子 00:01\n",
        encoding="utf-8",
    )


def _thread_main(vault: Path, project: str) -> None:
    path = vault / "projects" / f"{project}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nproject: {project}\ndate: 2026-09-01\ntype: project-main\nstatus: active\n"
        "---\n\n# T\n\n## 当前状态\n\n## 下一步\n\n## 阻塞\n\n## 决策记录\n",
        encoding="utf-8",
    )


def _entry(
    stable_id: str,
    *,
    decision: CandidateDecision,
    route: RouteTarget,
    project: str | None = "T1",
) -> ReviewEntry:
    candidate = ApprovalCandidate(
        candidate_id=stable_id,
        kind=CandidateKind.ACTION_ITEM,
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
        f"[[{_NOTE_REL}]]",
        "[[2026-09-02-沟通对齐会-transcript]]",
    )


def _meeting_meta(vault: Path) -> dict[str, object]:
    return load_note(vault / f"{_NOTE_REL}.md").meta


def test_apply_resolves_meeting_note_to_target_projects(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    work = tmp_path / "work"
    _meeting_note(vault)
    _thread_main(vault, "T1")
    _thread_main(vault, "T2")
    refresh_review_page(
        vault,
        [
            _entry(
                "m:n#action-item-0",
                decision=CandidateDecision.APPROVED,
                route=RouteTarget.PROJECT_FOLLOWUP,
                project="T1",
            ),
            _entry(
                "m:n#action-item-1",
                decision=CandidateDecision.APPROVED,
                route=RouteTarget.PROJECT_MAIN,
                project="T2",
            ),
            _entry(
                "m:n#action-item-2",
                decision=CandidateDecision.REJECTED,
                route=RouteTarget.PROJECT_FOLLOWUP,
                project="T1",
            ),
            _entry(
                "m:n#action-item-3",
                decision=CandidateDecision.APPROVED,
                route=RouteTarget.GLOBAL_INBOX,
                project=UNRESOLVED,
            ),
        ],
    )
    report = apply_meeting_review(vault, work, apply=True, now=datetime(2026, 9, 2, tzinfo=UTC))
    assert report.applied == 1  # 只有更新 T2 主笔记仍是允许的去处
    assert report.failed == 2  # 跟进和全局 inbox 已退役
    assert "final-m:n#action-item-0" not in (vault / "projects" / "T1.md").read_text()
    assert not (vault / "inbox.md").exists()


def test_apply_backfills_resolution_for_already_completed(tmp_path: Path) -> None:
    """旧版本已应用的候选（幂等账本里 result=applied）也补做会议回链解析。"""
    vault = tmp_path / "vault"
    work = tmp_path / "work"
    _meeting_note(vault)
    _thread_main(vault, "T1")
    entry = _entry(
        "m:n#action-item-0",
        decision=CandidateDecision.APPROVED,
        route=RouteTarget.PROJECT_FOLLOWUP,
        project="T1",
    )
    record = make_execution_record(
        entry, destination=str(vault / "projects" / "T1.md"), result="applied"
    )
    append_execution(vault, record)  # 模拟旧版本已应用（当时未做会议回链解析）
    refresh_review_page(vault, [entry])
    report = apply_meeting_review(vault, work, apply=True)
    assert report.applied == 0  # already-completed 不重复执行
    assert report.failed == 0
    assert _meeting_meta(vault)["projects"] == ["T1"]
