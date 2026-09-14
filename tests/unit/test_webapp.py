"""本地审批面板端到端测试（FastAPI TestClient）。"""

from __future__ import annotations

import re
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
    assert (
        '<blockquote><p>引用 <span class="wikilink" title="note.md">note.md</span></p></blockquote>'
        in html
    )


def test_md_to_html_handles_archive_block_shapes() -> None:
    """项目档案区块的真实形状：多行段落、有序列表 + 缩进续行、表格、wikilink 标签。

    与前端 `web/src/md.ts::mdToHtml` 同规则（`web/scripts/test-md-render.mjs` 是同一批断言）。
    """
    from summit_workbench.webapp.views import md_to_html

    html = md_to_html(
        "三条口径已定：**登记主体统一为 HII**、\n"
        "**「活满」与「和夫曼之旅」分开管理**。\n"
        "\n"
        "1. **9 月**：P0 权限清退收口；\n"
        "   相关方培训。\n"
        "2. **10 月**：启动 AI 知识库。\n"
        "- [ ] 待办一\n"
        "- [x] 已办二\n"
        "| 主线 | 状态 |\n"
        "|---|---|\n"
        "| 报名与课程生命周期 | 🟢 正式生产运行 |\n"
        "| 门户 / CMS / 权限 | 🟢 已投入业务使用 |\n"
        "- [[20260623-hii-registration-entity|决定：登记主体统一为 HII]] —— 一律登记在 HII 名下。"
    )
    # 硬换行拆开的段落并成一个 <p>，且中文之间不缝空格
    assert "<strong>登记主体统一为 HII</strong>、<strong>「活满」" in html, "行内标记处不该缝空格"
    expected_para = (
        "<p>三条口径已定：<strong>登记主体统一为 HII</strong>、"
        "<strong>「活满」与「和夫曼之旅」分开管理</strong>。</p>"
    )
    assert expected_para in html
    # 有序列表：一个 <ol>、两项，第二项的缩进续行并进同一项
    assert html.count("<ol>") == 1 and html.count("</ol>") == 1
    assert "<li><strong>9 月</strong>：P0 权限清退收口；相关方培训。</li>" in html
    # 任务清单
    assert '<li><span class="task">☐</span> 待办一</li>' in html
    assert '<li><span class="task done">☑</span> 已办二</li>' in html
    # 表格
    assert "<table><thead><tr><th>主线</th><th>状态</th></tr></thead>" in html
    assert "<td>报名与课程生命周期</td><td>🟢 正式生产运行</td>" in html
    # 表格后面紧跟的列表项不能被当成表格行吞掉（[[目标|显示名]] 里也有 `|`）
    assert html.count("<tr>") == 3, "表头 + 两行数据，wikilink 那行必须在表格外"
    assert re.search(r'</tbody></table>\s*<ul><li><span class="wikilink"', html)
    # wikilink：只显示标签，目标进 title
    expected_link = (
        '<span class="wikilink" title="20260623-hii-registration-entity">'
        "决定：登记主体统一为 HII</span>"
    )
    assert expected_link in html
    assert "[[" not in html


def test_md_to_html_never_injects_html() -> None:
    """vault 与模型文本都不可信：转义之后再套模式，任何路径都不许漏出可执行标签。"""
    from summit_workbench.webapp.views import md_to_html

    html = md_to_html("<script>alert(1)</script>\n**<img src=x onerror=alert(1)>**")
    assert "<script" not in html and "<img" not in html
    assert "&lt;script&gt;" in html
    assert "<strong>&lt;img src=x onerror=alert(1)&gt;</strong>" in html


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
