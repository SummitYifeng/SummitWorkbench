"""Web 面板 JSON API 与 SPA 服务测试（新工作台契约）。

SSR 路径的既有覆盖在 test_webapp.py；本文件覆盖：
- /api/state / /api/review / decide / edit / plan / apply / capture / ask / run
- /api/meetings/import（全自动链路，模型调用以 fake 替身验证编排）
- 构建产物存在时 / 服务 SPA，否则回退 SSR
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from pydantic import SecretStr

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


def _client(tmp_path: Path, *, seed_review: bool = True) -> tuple[TestClient, Path]:
    vault = tmp_path / "_vault"
    if seed_review:
        path = review_path(vault)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_review_page([_entry()]), encoding="utf-8")
    ctx = WebContext(vault_dir=vault, work_root=tmp_path, timezone="Asia/Shanghai")
    return TestClient(create_app(ctx, static_dir=tmp_path / "no-static")), vault


# ---------- /api/state ----------


def test_api_state_returns_day_brief_status_and_inbox(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "none.toml"))
    client, vault = _client(tmp_path)

    from summit_workbench.repositories.daily_note import write_brief

    day = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    write_brief(vault, day, "# 晨间简报\n- 测试行动项")
    (vault / "inbox.md").write_text(
        "---\ndate: 2026-08-27\ntype: inbox\nstatus: active\nproject: global\n---\n"
        "\n# 全局收件箱\n\n## 待处理条目\n\n- [ ] 待办A\n",
        encoding="utf-8",
    )

    resp = client.get("/api/state")
    assert resp.status_code == 200
    data = resp.json()
    assert data["day"] == day
    assert data["brief_generated"] is True
    assert "测试行动项" in data["brief_md"]
    assert data["status"]["pending_review"] == 1
    assert data["inbox_pending"] == 1


# ---------- /api/review ----------


def test_api_review_returns_grouped_json(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    data = client.get("/api/review").json()
    assert data["errors"] == []
    assert len(data["groups"]) == 1
    group = data["groups"][0]
    assert group["meeting_title"] == "排版会"
    entry = group["entries"][0]
    assert entry["candidate_id"] == "m1#decision-0"
    assert entry["kind"] == "decision"
    assert entry["decision"] == "pending"
    assert entry["target_project"] == "HIC_SWB_LaTEX"
    assert entry["route"] == "project-main"
    assert entry["actionable"] is True


def test_api_review_empty_when_no_page(tmp_path: Path) -> None:
    client, _ = _client(tmp_path, seed_review=False)
    data = client.get("/api/review").json()
    assert data["groups"] == []
    assert data["errors"] == []


# ---------- decide / edit ----------


def test_api_decide_approves(tmp_path: Path) -> None:
    client, vault = _client(tmp_path)
    resp = client.post(
        "/api/review/decide",
        json={"candidate_id": "m1#decision-0", "decision": "approved"},
    )
    assert resp.json()["ok"] is True
    parsed = parse_review_page(review_path(vault).read_text(encoding="utf-8"))
    assert parsed.entries[0].candidate.decision is CandidateDecision.APPROVED


def test_api_decide_unknown_candidate(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    resp = client.post(
        "/api/review/decide",
        json={"candidate_id": "ghost", "decision": "approved"},
    )
    data = resp.json()
    assert data["ok"] is False
    assert "找不到候选" in data["message"]


def test_api_batch_decide_rejects(tmp_path: Path) -> None:
    client, vault = _client(tmp_path)
    resp = client.post(
        "/api/review/batch",
        json={"candidate_ids": ["m1#decision-0", "ghost"], "decision": "rejected"},
    )
    data = resp.json()
    assert data["ok"] is True
    assert data["updated"] == 1
    parsed = parse_review_page(review_path(vault).read_text(encoding="utf-8"))
    assert parsed.entries[0].candidate.decision is CandidateDecision.REJECTED


def test_api_batch_decide_invalid_decision(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    resp = client.post(
        "/api/review/batch",
        json={"candidate_ids": ["m1#decision-0"], "decision": "bogus"},
    )
    assert resp.json()["ok"] is False


def test_api_edit_updates_fields(tmp_path: Path) -> None:
    client, vault = _client(tmp_path)
    resp = client.post(
        "/api/review/edit",
        json={
            "candidate_id": "m1#decision-0",
            "description": "改成三栏",
            "target_project": "HIC_Logistics",
            "route": "project-main",
            "due_date": "2026-09-10",
        },
    )
    assert resp.json()["ok"] is True
    entry = parse_review_page(review_path(vault).read_text(encoding="utf-8")).entries[0]
    assert entry.candidate.description == "改成三栏"
    assert entry.candidate.target_project == "HIC_Logistics"
    assert entry.candidate.due_date == "2026-09-10"


def test_api_plan_returns_dry_run(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    client.post(
        "/api/review/decide",
        json={"candidate_id": "m1#decision-0", "decision": "approved"},
    )
    data = client.post("/api/review/plan").json()
    assert data["ok"] is True
    assert data["executed"] is False
    assert "DRY-RUN" in data["plan_text"]


# ---------- capture ----------


def test_api_capture_appends_inbox(tmp_path: Path) -> None:
    client, vault = _client(tmp_path)
    resp = client.post("/api/capture", json={"text": "给老王回邮件 #网课"})
    data = resp.json()
    assert data["ok"] is True
    assert "已记入全局 inbox" in data["message"]
    text = (vault / "inbox.md").read_text(encoding="utf-8")
    assert "- [ ] 给老王回邮件 #网课" in text


def test_api_capture_empty_rejected(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    resp = client.post("/api/capture", json={"text": "   "})
    assert resp.json()["ok"] is False


# ---------- meetings/import ----------


def test_api_import_rejects_bad_extension(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    resp = client.post(
        "/api/meetings/import",
        files={"file": ("notes.pdf", b"%PDF-1.4", "application/pdf")},
    )
    data = resp.json()
    assert data["ok"] is False
    assert "仅支持" in data["message"]


def test_api_import_full_auto_pipeline(tmp_path: Path, monkeypatch) -> None:
    """模型调用以替身替换：验证 扫描 → 预估 → 全自动归档+结构化 → 候选 的编排与响应。"""
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "none.toml"))
    client, vault = _client(tmp_path, seed_review=False)

    class FakePricing:
        currency = "CNY"

        def estimate(self, _in: int, _out: int) -> float:
            return 0.001

    class FakeCfg:
        api_key_ref = "fake-key-ref"
        max_output_tokens = 1024
        pricing = FakePricing()

    from summit_workbench.workflows.meetings.backfill import BackfillRunReport

    fake_report = BackfillRunReport(results=[], processed=1, skipped=0, failed=0, candidates=3)
    monkeypatch.setattr("summit_workbench.providers.llm.load_model_config", lambda _name: FakeCfg())
    monkeypatch.setattr(
        "summit_workbench.config.secrets.resolve_credential", lambda _ref: SecretStr("fake")
    )
    monkeypatch.setattr("summit_workbench.prompts.load_prompt", lambda _name: object())
    monkeypatch.setattr(
        "summit_workbench.workflows.meetings.backfill.run_backfill",
        lambda *_a, **_k: fake_report,
    )

    transcript = "# 产品周会\n\n张三 00:01:02 大家好\n李四 00:02:00 讨论预算\n"
    resp = client.post(
        "/api/meetings/import",
        files={"file": ("2026-09-01-产品周会.txt", transcript.encode("utf-8"), "text/plain")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "导入完成" in data["message"]
    assert "生成候选 3" in data["message"]
    assert data["estimate"]["pending"] == 1
    assert data["estimate"]["currency"] == "CNY"


def test_api_import_empty_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "none.toml"))
    client, _ = _client(tmp_path)
    resp = client.post(
        "/api/meetings/import",
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    data = resp.json()
    assert data["ok"] is False
    assert "文件内容为空" in data["message"]


# ---------- ask ----------


def test_api_ask_without_model_shows_unavailable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "none.toml"))
    client, _ = _client(tmp_path)
    resp = client.post("/api/ask", json={"question": "最近有什么决策"})
    data = resp.json()
    assert data["ok"] is True
    assert "问答不可用" in data["answer_html"]


# ---------- SPA 服务 ----------


def test_spa_served_when_static_built(tmp_path: Path) -> None:
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text(
        "<!doctype html><html><body>SPA SHELL</body></html>", encoding="utf-8"
    )
    vault = tmp_path / "_vault"
    ctx = WebContext(vault_dir=vault, work_root=tmp_path, timezone="Asia/Shanghai")
    client = TestClient(create_app(ctx, static_dir=static))
    resp = client.get("/")
    assert resp.status_code == 200
    assert "SPA SHELL" in resp.text
    # API 与 SPA 共存
    state = client.get("/api/state").json()
    assert "status" in state


# ---------- capture 智能分类 ----------


def test_api_capture_classifies_task(monkeypatch, tmp_path: Path) -> None:
    """模型可用：识别为承诺 + 截止日期 + #项目 关联，分类标记写回 inbox。"""
    from pydantic import SecretStr

    from summit_workbench.domain.capture import CaptureClassification, CaptureKind

    class FakeCfg:
        api_key_ref = "fake"

    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "none.toml"))
    client, vault = _client(tmp_path)
    # 建一个已知项目，让 #排版 能解析
    (vault / "projects").mkdir(parents=True, exist_ok=True)
    (vault / "projects" / "HIC_SWB_LaTEX.md").write_text(
        "---\nproject: HIC_SWB_LaTEX\ndate: 2026-08-27\ntype: project-main\n"
        "status: active\nupdated: 2026-08-27\naliases: [排版]\n---\n\n# HIC_SWB_LaTEX\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("summit_workbench.providers.llm.load_model_config", lambda _name: FakeCfg())
    monkeypatch.setattr(
        "summit_workbench.config.secrets.resolve_credential", lambda _ref: SecretStr("fake")
    )
    monkeypatch.setattr("summit_workbench.prompts.load_prompt", lambda _name: object())
    monkeypatch.setattr(
        "summit_workbench.workflows.capture.classify_capture",
        lambda *_a, **_k: CaptureClassification(
            kind=CaptureKind.TASK, due_date="2026-09-10", involves_others=True
        ),
    )

    resp = client.post("/api/capture", json={"text": "周三前给老王样章 #排版"})
    data = resp.json()
    assert data["ok"] is True
    assert data["kind"] == "task"
    assert data["due_date"] == "2026-09-10"
    assert data["project"] == "HIC_SWB_LaTEX"
    assert "承诺" in data["message"]
    text = (vault / "inbox.md").read_text(encoding="utf-8")
    assert "- [ ] 周三前给老王样章 #排版" in text
    assert "<!-- wb-capture-kind: task -->" in text
    assert "<!-- wb-capture-due: 2026-09-10 -->" in text
    assert "<!-- wb-capture-project: HIC_SWB_LaTEX -->" in text


def test_api_capture_falls_back_when_model_unavailable(tmp_path: Path, monkeypatch) -> None:
    """模型未配置：按想法兜底，录入不失败、不丢数据。"""
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "none.toml"))
    client, vault = _client(tmp_path)
    resp = client.post("/api/capture", json={"text": "想到一个点子"})
    data = resp.json()
    assert data["ok"] is True
    assert data["kind"] == "idea"
    assert data["model_used"] is False
    assert "想法" in data["message"]
    text = (vault / "inbox.md").read_text(encoding="utf-8")
    assert "- [ ] 想到一个点子" in text
    assert "<!-- wb-capture-kind: idea -->" in text


# ---------- /api/state 项目推进 ----------


def test_api_state_includes_projects(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "none.toml"))
    client, vault = _client(tmp_path, seed_review=False)
    work_root = tmp_path
    (work_root / "HIC_Demo" / "input").mkdir(parents=True, exist_ok=True)
    (work_root / "HIC_Demo" / "input" / "inbox.md").write_text(
        "## 待处理条目\n\n- [ ] 待办A\n", encoding="utf-8"
    )
    (vault / "projects").mkdir(parents=True, exist_ok=True)
    (vault / "projects" / "HIC_Demo.md").write_text(
        "---\nproject: HIC_Demo\ndate: 2026-08-27\ntype: project-main\n"
        "status: active\nupdated: 2026-08-27\n---\n\n# HIC_Demo\n\n## 下一步\n\n- 推进样章\n",
        encoding="utf-8",
    )
    data = client.get("/api/state").json()
    assert data["projects"] != []
    proj = next(p for p in data["projects"] if p["name"] == "HIC_Demo")
    assert proj["inbox_pending"] == 1
    assert proj["next_step"] == "推进样章"
    assert proj["dirty"] is False
