"""本地审批面板端到端测试（FastAPI TestClient）。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from summit_workbench.domain.review import (
    ApprovalCandidate,
    CandidateDecision,
    CandidateKind,
    EvidenceRef,
    ReviewEntry,
    RouteTarget,
)
from summit_workbench.repositories.review_page import (
    parse_review_page,
    render_review_page,
    review_path,
)
from summit_workbench.webapp.app import WebContext, create_app


def _entry() -> ReviewEntry:
    candidate = ApprovalCandidate(
        candidate_id="m1#decision-0",
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
        transcript_link="[[t.md]]",
    )


def _client(tmp_path: Path) -> tuple[TestClient, Path]:
    vault = tmp_path / "_vault"
    path = review_path(vault)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_review_page([_entry()]), encoding="utf-8")
    ctx = WebContext(vault_dir=vault, work_root=tmp_path, timezone="Asia/Shanghai")
    return TestClient(create_app(ctx)), vault


def test_root_redirects_to_review(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/review"


def test_review_page_lists_candidate(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    resp = client.get("/review")
    assert resp.status_code == 200
    assert "采用双栏排版" in resp.text
    assert "排版会" in resp.text
    assert "1 条待确认" in resp.text


def test_decide_approves_via_post(tmp_path: Path) -> None:
    client, vault = _client(tmp_path)
    resp = client.post(
        "/review/decide",
        data={"candidate_id": "m1#decision-0", "decision": "approved"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    parsed = parse_review_page(review_path(vault).read_text(encoding="utf-8"))
    assert parsed.entries[0].candidate.decision is CandidateDecision.APPROVED


def test_edit_updates_fields_via_post(tmp_path: Path) -> None:
    client, vault = _client(tmp_path)
    client.post(
        "/review/edit",
        data={
            "candidate_id": "m1#decision-0",
            "description": "改成三栏",
            "target_project": "HIC_Logistics",
            "route": "project-main",
            "due_date": "2026-09-10",
        },
        follow_redirects=False,
    )
    entry = parse_review_page(review_path(vault).read_text(encoding="utf-8")).entries[0]
    assert entry.candidate.description == "改成三栏"
    assert entry.candidate.target_project == "HIC_Logistics"
    assert entry.candidate.due_date == "2026-09-10"


def test_plan_shows_dry_run(tmp_path: Path) -> None:
    client, vault = _client(tmp_path)
    # 先批准，dry-run 计划应显示该条写回项目主笔记
    client.post(
        "/review/decide",
        data={"candidate_id": "m1#decision-0", "decision": "approved"},
    )
    resp = client.get("/review/plan")
    assert resp.status_code == 200
    assert "DRY-RUN" in resp.text
    assert "project-main" in resp.text or "m1#decision-0" in resp.text


def test_bad_candidate_shows_message(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    resp = client.post(
        "/review/decide",
        data={"candidate_id": "ghost", "decision": "approved"},
        follow_redirects=True,
    )
    assert "找不到候选" in resp.text
