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
from summit_workbench.webapp import app_factory, legacy_app
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
    # 显式指向不存在的 static 目录：这些测试验证 SSR 回退路径（构建产物存在时 / 是 SPA）
    return TestClient(create_app(ctx, static_dir=tmp_path / "no-static")), vault


def test_web_context_compatibility_exports_share_class() -> None:
    assert WebContext is app_factory.WebContext
    assert WebContext is legacy_app.WebContext


def test_home_renders_dashboard(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "none.toml"))
    client, vault = _client(tmp_path)
    # 放一份当日简报进 daily 笔记，看板应渲染其内容
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from summit_workbench.repositories.daily_note import write_brief

    day = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    write_brief(vault, day, "# 晨间简报\n## 需要行动（1/5）\n- 测试行动项")
    resp = client.get("/")
    assert resp.status_code == 200
    assert "SummitWorkbench" in resp.text
    assert "今日简报" in resp.text
    assert "测试行动项" in resp.text  # markdown 渲染
    assert "问第二大脑" in resp.text  # ask 表单
    assert "待确认候选" in resp.text  # 状态 tile


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


def test_run_weekly_creates_note(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "none.toml"))
    client, vault = _client(tmp_path)
    resp = client.post("/run/weekly", follow_redirects=False)
    assert resp.status_code == 303
    weekly_dir = vault / "reviews" / "weekly"
    assert weekly_dir.is_dir() and any(weekly_dir.glob("*.md"))


def test_ask_without_model_shows_unavailable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "none.toml"))
    client, _ = _client(tmp_path)
    resp = client.post("/ask", data={"question": "最近有什么决策"}, follow_redirects=False)
    assert resp.status_code == 200
    assert "问答不可用" in resp.text
    assert "最近有什么决策" in resp.text  # 问题回填


def test_md_to_html_renders_subset() -> None:
    from summit_workbench.webapp.views import md_to_html

    html = md_to_html("## 标题\n- 项目 **粗** `代码`\n> 引用 [[note.md]]")
    assert "<h3>标题</h3>" in html
    assert "<li>项目 <strong>粗</strong> <code>代码</code></li>" in html
    assert '<blockquote>引用 <span class="wikilink">note.md</span></blockquote>' in html


def test_bad_candidate_shows_message(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    resp = client.post(
        "/review/decide",
        data={"candidate_id": "ghost", "decision": "approved"},
        follow_redirects=True,
    )
    assert "找不到候选" in resp.text


def test_shutdown_requires_header(tmp_path: Path) -> None:
    """缺自定义头时拒绝关闭——防止任意本地网页把面板关掉。"""
    client, _ = _client(tmp_path)
    resp = client.post("/api/shutdown")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert "缺少关闭令牌" in body["message"]


def test_shutdown_with_header_exits(tmp_path: Path, monkeypatch) -> None:
    """带 X-WB-Shutdown 头时返回 ok，并在后台线程触发进程退出（此处打桩）。"""
    import time as _time

    client, _ = _client(tmp_path)
    exited: list[int] = []
    monkeypatch.setattr("summit_workbench.webapp.app.os._exit", lambda code: exited.append(code))

    resp = client.post("/api/shutdown", headers={"X-WB-Shutdown": "1"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    deadline = _time.monotonic() + 2.0
    while not exited and _time.monotonic() < deadline:
        _time.sleep(0.01)
    assert exited == [0]
