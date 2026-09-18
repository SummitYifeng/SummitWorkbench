"""Web 面板 JSON API 与 SPA 服务测试（新工作台契约）。

SSR 路径的既有覆盖在 test_webapp.py；本文件覆盖：
- /api/state / /api/review / decide / edit / plan / apply / capture / ask / run
- /api/meetings/import（全自动链路，模型调用以 fake 替身验证编排）
- 构建产物存在时 / 服务 SPA，否则回退 SSR
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from pydantic import SecretStr

from summit_workbench.domain.external_action import ExternalActionKind, ExternalActionState
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
from summit_workbench.repositories.vault import load_note
from summit_workbench.webapp.app import WebContext, create_app
from summit_workbench.workflows.external_actions import mark_sending, mark_unknown, prepare_action

_STATIC_DIR = Path(__file__).resolve().parents[2] / "src" / "summit_workbench" / "webapp" / "static"


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


def _spa_client(tmp_path: Path) -> TestClient:
    static_dir = tmp_path / "static"
    shutil.copytree(_STATIC_DIR, static_dir)
    ctx = WebContext(vault_dir=tmp_path / "_vault", work_root=tmp_path, timezone="Asia/Shanghai")
    return TestClient(create_app(ctx, static_dir=static_dir))


def test_api_version_returns_actual_static_build(tmp_path: Path) -> None:
    client = _spa_client(tmp_path)
    expected = json.loads((_STATIC_DIR / "build-meta.json").read_text(encoding="utf-8"))[
        "frontend_build"
    ]
    response = client.get("/api/version")
    assert response.status_code == 200
    data = response.json()
    assert data["product_id"] == "com.summitworkbench.panel"
    assert data["api_protocol"] == 3
    assert data["frontend_build"] == expected
    assert data["server_instance"]
    assert data["server_version"]


def test_api_version_has_no_store_headers(tmp_path: Path) -> None:
    response = _spa_client(tmp_path).get("/api/version")
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert response.headers["pragma"] == "no-cache"


def test_external_action_query_and_manual_reconcile(tmp_path: Path) -> None:
    client, vault = _client(tmp_path, seed_review=False)
    action = prepare_action(
        vault,
        candidate_id="m#task-0",
        kind=ExternalActionKind.FEISHU_TASK,
        request={"description": "任务"},
        target_account_ref="feishu:user",
    )
    action = mark_unknown(vault, mark_sending(vault, action), "请求超时")

    listed = client.get("/api/external-actions")
    assert listed.status_code == 200
    assert listed.json()["actions"][0]["state"] == ExternalActionState.UNKNOWN.value

    confirmed = client.post(
        f"/api/external-actions/{action.operation_id}/reconcile",
        json={"decision": "succeeded", "remote_id": "task-remote"},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["action"]["state"] == "reconciled-succeeded"


def test_api_version_changes_server_instance_per_app_instance(tmp_path: Path) -> None:
    static_dir = tmp_path / "static"
    shutil.copytree(_STATIC_DIR, static_dir)
    ctx = WebContext(vault_dir=tmp_path / "_vault", work_root=tmp_path, timezone="Asia/Shanghai")
    first = TestClient(create_app(ctx, static_dir=static_dir)).get("/api/version").json()
    second = TestClient(create_app(ctx, static_dir=static_dir)).get("/api/version").json()
    assert first["server_instance"] != second["server_instance"]


def test_api_version_returns_503_for_invalid_manifest(tmp_path: Path) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    ctx = WebContext(vault_dir=tmp_path / "_vault", work_root=tmp_path, timezone="Asia/Shanghai")
    response = TestClient(create_app(ctx, static_dir=static_dir)).get("/api/version")
    assert response.status_code == 503
    assert response.json()["code"] == "invalid_build_manifest"
    assert response.json()["operation_id"]


def test_spa_home_uses_no_store(tmp_path: Path) -> None:
    response = _spa_client(tmp_path).get("/")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, max-age=0, must-revalidate"


def test_hashed_assets_are_immutable(tmp_path: Path) -> None:
    client = _spa_client(tmp_path)
    meta = json.loads((_STATIC_DIR / "build-meta.json").read_text(encoding="utf-8"))
    for name in meta["assets"]:
        response = client.get("/static/" + name)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_api_state_includes_runtime_build_identity(tmp_path: Path) -> None:
    response = _spa_client(tmp_path).get("/api/state")
    assert response.status_code == 200
    runtime = response.json()["runtime"]
    assert runtime["frontend_build"]
    assert runtime["server_version"]
    assert runtime["server_instance"]


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


def test_api_state_brief_null_without_detail_snapshot(tmp_path: Path, monkeypatch) -> None:
    """旧格式快照（仅计数、无 *_list 明细）→ brief=None，前端回退 Markdown 视图。"""
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "none.toml"))
    client, vault = _client(tmp_path)

    from summit_workbench.repositories.daily_note import write_brief
    from summit_workbench.repositories.signal_snapshot import write_snapshot

    day = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    write_brief(vault, day, "# 晨间简报\n- 测试行动项")
    write_snapshot(
        vault,
        day,
        {"date": day, "health": "ok", "meetings": 1, "tasks": 1, "actions": [], "proposals": []},
    )
    data = client.get("/api/state").json()
    assert data["brief"] is None
    assert "测试行动项" in data["brief_md"]


def test_api_state_brief_structured_when_snapshot_has_detail(tmp_path: Path, monkeypatch) -> None:
    """含 *_list 明细的快照 → /api/state.brief 提供组件化渲染所需字段。"""
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "none.toml"))
    client, vault = _client(tmp_path)

    from summit_workbench.repositories.signal_snapshot import write_snapshot

    day = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    write_snapshot(
        vault,
        day,
        {
            "date": day,
            "health": "degraded",
            "health_reasons": ["采集源失败：飞书日历"],
            "meetings": 1,
            "tasks": 1,
            "actions": [
                {
                    "signal_id": "task-guid-1",
                    "title": "门户验收",
                    "category": "commitment",
                    "evidence": "E2",
                    "source_ref": "feishu-task:guid-1",
                    "project": None,
                    "due_date": day,
                    "detail": "",
                }
            ],
            "proposals": [],
            "completions": 1,
            "pending_review": 2,
            "ranking_model": "test-model",
            "meeting_list": [{"title": "钻石三角双周例会", "start_time": "10:00"}],
            "task_list": [{"summary": "门户验收", "due_date": day, "task_id": "guid-1"}],
            "proposal_list": [],
            "completion_list": [{"text": "HIC_Tool_Kit", "source_ref": "feishu-task:x"}],
        },
    )
    data = client.get("/api/state").json()
    brief = data["brief"]
    assert brief is not None
    assert brief["date"] == day
    assert brief["health"]["level"] == "degraded"
    assert brief["health"]["label"] == "降级"
    assert brief["health"]["reasons"] == ["采集源失败：飞书日历"]
    assert brief["meetings"] == [
        {
            "title": "钻石三角双周例会",
            "start_time": "10:00",
            "event_id": None,
            "start_ts": None,
            "end_ts": None,
        }
    ]
    assert brief["tasks"] == [{"summary": "门户验收", "due_date": day, "task_id": "guid-1"}]
    action = brief["actions"][0]
    assert action["rank"] == 1
    assert action["category_key"] == "commitment"
    assert action["category"] == "近期承诺"
    assert action["title"] == "门户验收"
    assert brief["completions"] == [{"text": "HIC_Tool_Kit", "source_ref": "feishu-task:x"}]
    assert brief["pending_review"] == 2


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


def test_api_review_source_is_read_only_and_vault_scoped(tmp_path: Path) -> None:
    client, vault = _client(tmp_path, seed_review=False)
    source = vault / "meetings" / "notes" / "source.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# 来源\n\n原文证据。", encoding="utf-8")

    response = client.get("/api/review/source", params={"path": "meetings/notes/source.md"})
    assert response.status_code == 200
    assert response.text == "# 来源\n\n原文证据。"
    assert client.get("/api/review/source", params={"path": "../outside.md"}).status_code == 400
    assert not (vault / "outside.md").exists()
    # vault 内但非知识目录的 Markdown 也必须拒绝（与 /api/sources/read 同一份白名单）。
    stray = vault / "notes" / "stray.md"
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_text("# stray", encoding="utf-8")
    hidden = vault / "_signals" / "hidden.md"
    hidden.parent.mkdir(parents=True, exist_ok=True)
    hidden.write_text("# hidden", encoding="utf-8")
    assert client.get("/api/review/source", params={"path": "notes/stray.md"}).status_code == 400
    assert (
        client.get("/api/review/source", params={"path": "_signals/hidden.md"}).status_code == 400
    )
    # inbox.md 是允许的知识来源。
    (vault / "inbox.md").write_text("# inbox\n\n记录。", encoding="utf-8")
    inbox = client.get("/api/review/source", params={"path": "inbox.md"})
    assert inbox.status_code == 200
    assert inbox.text == "# inbox\n\n记录。"


def test_api_sources_read_accepts_work_knowledge_roots(tmp_path: Path) -> None:
    """方案 A（工作线主线）的新根必须能作为知识来源打开。

    否则 `路径#区块` 引用在来源面板点开会 400/404——引用可点开是本轮验收的硬要求。
    负例护栏：未加入白名单的顶层目录（`notes/`）仍必须被拒（白名单不得被顺手放宽）。
    """
    client, vault = _client(tmp_path, seed_review=False)
    for root in ("hii", "it", "community", "hr", "decisions", "index"):
        target = vault / root / "sample.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            f"---\ndate: 2026-09-13\ntype: note\nstatus: active\n---\n\n# {root}\n\n正文。",
            encoding="utf-8",
        )
        response = client.get("/api/sources/read", params={"source_id": f"{root}/sample"})
        assert response.status_code == 200, (root, response.status_code)

    stray = vault / "notes" / "stray.md"
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_text("# stray", encoding="utf-8")
    assert client.get("/api/sources/read", params={"source_id": "notes/stray"}).status_code == 400


def test_api_sources_read_marks_truncated_body(tmp_path: Path) -> None:
    from summit_workbench.webapp.legacy_app import SOURCE_BODY_DISPLAY_CHARS

    client, vault = _client(tmp_path, seed_review=False)
    body = "x" * (SOURCE_BODY_DISPLAY_CHARS + 500)
    source = vault / "logs" / "long.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(f"---\ntitle: 长日志\ndate: 2026-09-01\n---\n\n{body}", encoding="utf-8")

    response = client.get("/api/sources/read", params={"source_id": "logs/long"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["truncated"] is True
    assert payload["body"] == body[:SOURCE_BODY_DISPLAY_CHARS]
    assert len(payload["body"]) == SOURCE_BODY_DISPLAY_CHARS


def test_api_sources_read_still_rejects_oversized_file(tmp_path: Path) -> None:
    client, vault = _client(tmp_path, seed_review=False)
    source = vault / "logs" / "huge.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("x" * (256 * 1024 + 1), encoding="utf-8")

    response = client.get("/api/sources/read", params={"source_id": "logs/huge"})
    assert response.status_code == 413
    assert response.json()["ok"] is False


def test_api_sources_read_returns_structured_source_and_rejects_disallowed_paths(
    tmp_path: Path,
) -> None:
    client, vault = _client(tmp_path, seed_review=False)
    source = vault / "projects" / "P1.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        "---\ntitle: 项目一\ndate: 2026-09-01\ntype: project-main\n---\n\n# 项目一\n\n正文。",
        encoding="utf-8",
    )

    response = client.get("/api/sources/read", params={"source_id": "projects/P1"})
    assert response.status_code == 200
    # 2026-09-13 新增 `anchor` / `heading` 两个字段（问答引用升级为「路径#区块」）：
    # 整篇引用时 anchor 就是 source_id，heading 为空。
    assert response.json() == {
        "ok": True,
        "source_id": "projects/P1",
        "title": "项目一",
        "date": "2026-09-01",
        "body": "# 项目一\n\n正文。",
        "truncated": False,
        "anchor": "projects/P1",
        "heading": "",
    }
    assert (
        client.get("/api/sources/read", params={"source_id": "../projects/P1"}).status_code == 400
    )
    assert (
        client.get("/api/sources/read", params={"source_id": "settings/secrets"}).status_code == 400
    )


def test_api_sources_read_returns_the_requested_block(tmp_path: Path) -> None:
    """`路径#区块` 引用必须只返回那一块，并回报区块标题；不存在的区块要 404。"""
    client, vault = _client(tmp_path, seed_review=False)
    source = vault / "hii" / "notes" / "consensus.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        "---\ntitle: 商标共识规范\ndate: 2026-09-12\ntype: note\n---\n\n"
        "# 商标共识规范\n\n## 登记主体\n\n登记在 HII 名下。\n\n"
        "## 逐项商标归属与状态\n\n活满归 HIC。\n",
        encoding="utf-8",
    )

    response = client.get(
        "/api/sources/read", params={"source_id": "hii/notes/consensus#逐项商标归属与状态"}
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["heading"] == "逐项商标归属与状态"
    assert payload["anchor"] == "hii/notes/consensus#逐项商标归属与状态"
    assert "活满归 HIC" in payload["body"]
    assert "登记在 HII 名下" not in payload["body"]

    missing = client.get("/api/sources/read", params={"source_id": "hii/notes/consensus#不存在"})
    assert missing.status_code == 404


def test_api_sources_read_rejects_empty_and_block_only_ids_instead_of_internal_error(
    tmp_path: Path,
) -> None:
    """空引用与「只有 #区块、没有路径」的引用必须是 400，不能 500。

    根因是 `Path("").with_suffix(".md")` 会抛 `ValueError: PosixPath('.') has an empty name`，
    而它排在 400 守卫**之前**——前端传一个畸形参数就只能看到兜底的「服务内部错误」。
    2026-09-14 在已装 build 41 上实测两种都是 500（`OPEN-VERIFICATION-ITEMS.md` §U.5
    当时只记了空值这一种，实际「只有区块」走的是同一条路径）。
    """
    client, _vault = _client(tmp_path, seed_review=False)

    empty = client.get("/api/sources/read", params={"source_id": ""})
    assert empty.status_code == 400
    assert empty.json()["ok"] is False

    # 只有区块：前端拼「路径#区块」时路径部分丢了，属同一根因。
    block_only = client.get("/api/sources/read", params={"source_id": "#关键结论"})
    assert block_only.status_code == 400
    assert block_only.json()["ok"] is False

    # 纯空白与空引用等价。
    blank = client.get("/api/sources/read", params={"source_id": "   "})
    assert blank.status_code == 400


def test_api_sources_read_rejects_non_utf8_file_instead_of_internal_error(tmp_path: Path) -> None:
    """误放进 vault 的二进制文件必须以 415 明确拒绝，不能 500。

    500 会让前端把响应解析失败，最终显示兜底的「服务内部错误 [internal_error]」，
    用户看不到真正原因（2026-09-11 真实浏览器 D2 矩阵发现）。
    """
    client, vault = _client(tmp_path, seed_review=False)
    binary = vault / "projects" / "probe.md"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x01\x02\xff\xfe binary payload")

    response = client.get("/api/sources/read", params={"source_id": "projects/probe"})
    assert response.status_code == 415
    assert response.json()["ok"] is False

    # 同一份文件经只读来源端点打开时，也要给出明确错误而不是抛异常。
    plain = client.get("/api/review/source", params={"path": "projects/probe.md"})
    assert plain.status_code == 415


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


def test_api_edit_rejects_invalid_due_date_visibly(tmp_path: Path) -> None:
    client, vault = _client(tmp_path)
    resp = client.post(
        "/api/review/edit",
        json={
            "candidate_id": "m1#decision-0",
            "due_date": "09/10/2026",
        },
    )
    data = resp.json()
    assert data["ok"] is False
    assert "保存失败" in data["message"]
    parsed = parse_review_page(review_path(vault).read_text(encoding="utf-8"))
    assert parsed.errors == []
    assert parsed.entries[0].candidate.due_date is None


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
    assert data["operation_id"]
    assert data["commit"]["status"] == "not-git"
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
    """上传接口只返回可恢复任务，不等待模型链路。"""
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "none.toml"))
    from summit_workbench.webapp.meeting_import import MeetingImportManager

    monkeypatch.setattr(MeetingImportManager, "_process", lambda self, _job_id: None)
    client, vault = _client(tmp_path, seed_review=False)

    transcript = "# 产品周会\n\n张三 00:01:02 大家好\n李四 00:02:00 讨论预算\n"
    resp = client.post(
        "/api/meetings/import",
        files={"file": ("2026-09-01-产品周会.txt", transcript.encode("utf-8"), "text/plain")},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["ok"] is True
    assert data["status"] in {"queued", "running", "succeeded"}
    assert data["stage"] in {"archived", "structuring", "completed"}
    assert list((vault / "meetings" / "transcripts").glob("*.md"))


def test_api_import_partial_pipeline_is_not_reported_as_success(
    tmp_path: Path, monkeypatch
) -> None:
    """后台任务的中间状态不会被上传请求伪装成同步成功。"""
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "none.toml"))
    from summit_workbench.webapp.meeting_import import MeetingImportManager

    monkeypatch.setattr(MeetingImportManager, "_process", lambda self, _job_id: None)
    client, _ = _client(tmp_path, seed_review=False)

    resp = client.post(
        "/api/meetings/import",
        files={
            "file": (
                "2026-09-02-部分失败.txt",
                "张三 00:01:02 需要复核".encode(),
                "text/plain",
            )
        },
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["ok"] is True
    assert data["status"] in {"queued", "running", "succeeded"}
    assert data["stage"] in {"archived", "structuring", "completed"}


def test_api_import_done_item_is_idempotent_without_model_config(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "none.toml"))
    client, _ = _client(tmp_path, seed_review=False)
    from summit_workbench.workflows.meetings.backfill import BackfillItem

    done_item = BackfillItem(
        path=tmp_path / "already-done.txt",
        title="已处理会议",
        date="2026-09-03",
        idem_key="meeting:2026-09-03:already-done",
        input_tokens=12,
        done=True,
    )
    monkeypatch.setattr(
        "summit_workbench.workflows.meetings.backfill.scan_for_import",
        lambda *_a, **_k: [done_item],
    )
    resp = client.post(
        "/api/meetings/import",
        files={"file": ("2026-09-03-已处理会议.txt", "重复导入".encode(), "text/plain")},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["ok"] is True
    assert data["status"] == "succeeded"
    assert data["stage"] == "completed"
    assert "幂等" in data["result"]["message"]


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


def test_api_import_archives_and_returns_resumable_job(tmp_path: Path, monkeypatch) -> None:
    """上传请求只负责归档，模型链路不阻塞 HTTP 响应。"""
    from summit_workbench.webapp.meeting_import import MeetingImportManager

    monkeypatch.setattr(MeetingImportManager, "_process", lambda self, _job_id: None)
    client, vault = _client(tmp_path, seed_review=False)
    response = client.post(
        "/api/meetings/import",
        files={"file": ("2026-09-10-异步会.txt", "张三 00:01:02 先归档".encode(), "text/plain")},
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["ok"] is True
    assert payload["job_id"]
    assert payload["status"] == "queued"
    assert payload["stage"] == "archived"
    assert list((vault / "meetings" / "transcripts").glob("*.md"))
    listed = client.get("/api/meetings/imports").json()
    assert listed["jobs"][0]["job_id"] == payload["job_id"]
    assert client.get("/api/meetings/imports/" + payload["job_id"]).json()["ok"] is True


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
    # ADR 0023：/api/state 暴露建档状态
    assert proj["registered"] is True
    assert proj["status"] == "active"


# ---------- /api/projects 工作台精选（ADR 0023） ----------


def _mk_project_dir(work_root: Path, name: str) -> Path:
    path = work_root / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_api_project_activate_creates_registration(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "none.toml"))
    client, vault = _client(tmp_path, seed_review=False)
    _mk_project_dir(tmp_path, "BrandNew")
    resp = client.post("/api/projects/activate", json={"name": "BrandNew"})
    assert resp.json()["ok"] is True
    note = load_note(vault / "projects" / "BrandNew.md")
    assert note.meta["status"] == "active"
    # 幂等：重复激活仍是 ok
    assert client.post("/api/projects/activate", json={"name": "BrandNew"}).json()["ok"] is True
    # 归档后再激活 = 恢复
    assert client.post("/api/projects/archive", json={"name": "BrandNew"}).json()["ok"] is True
    assert load_note(vault / "projects" / "BrandNew.md").meta["status"] == "archived"
    assert client.post("/api/projects/activate", json={"name": "BrandNew"}).json()["ok"] is True
    assert load_note(vault / "projects" / "BrandNew.md").meta["status"] == "active"


def test_api_project_archive_unregistered_creates_archived(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "none.toml"))
    client, vault = _client(tmp_path, seed_review=False)
    _mk_project_dir(tmp_path, "FreshFolder")
    resp = client.post("/api/projects/archive", json={"name": "FreshFolder"})
    assert resp.json()["ok"] is True
    note = load_note(vault / "projects" / "FreshFolder.md")
    assert note.meta["status"] == "archived"
    # 幂等
    assert client.post("/api/projects/archive", json={"name": "FreshFolder"}).json()["ok"] is True


def test_api_projects_reject_invalid_targets(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "none.toml"))
    client, _vault = _client(tmp_path, seed_review=False)
    for endpoint in ("/api/projects/activate", "/api/projects/archive"):
        for name in ("不存在", "../outside", "a/b", "", "_vault"):
            data = client.post(endpoint, json={"name": name}).json()
            assert data["ok"] is False, f"{endpoint} name={name!r} 应被拒绝"


# ---------- /api/tasks/complete（工作台一键完成飞书任务） ----------


def _patch_feishu_task_api(monkeypatch, fake_complete) -> None:
    """把 /api/tasks/complete 内部的飞书调用替换为离线替身（真源写回点不动）。"""

    class _FakeSession:
        def __init__(self, cfg: object, lock_root: Path | None = None) -> None:
            self.cfg = cfg

        def access_token(self) -> SecretStr:
            return SecretStr("tok")

    class _FakeFeishuClient:
        def __init__(self, cfg: object, token: SecretStr) -> None:
            pass

    monkeypatch.setattr("summit_workbench.providers.feishu.FeishuClient", _FakeFeishuClient)
    monkeypatch.setattr("summit_workbench.providers.feishu.FeishuSession", _FakeSession)
    monkeypatch.setattr("summit_workbench.providers.feishu.load_feishu_config", lambda: object())
    monkeypatch.setattr("summit_workbench.providers.feishu.complete_task", fake_complete)


def _task_snapshot_payload(day: str) -> dict[str, object]:
    return {
        "date": day,
        "health": "ok",
        "tasks": 2,
        "meetings": 0,
        "actions": [
            {
                "signal_id": "task-guid-1",
                "title": "提交样章",
                "category": "commitment",
                "evidence": "E2",
                "source_ref": "feishu-task:guid-1",
                "project": None,
                "due_date": day,
                "detail": "",
            }
        ],
        "proposals": [],
        "completions": 0,
        "pending_review": 0,
        "meeting_list": [],
        "task_list": [
            {"summary": "提交样章", "due_date": day, "task_id": "guid-1"},
            {"summary": "回邮件", "due_date": None, "task_id": "guid-2"},
        ],
        "completion_list": [],
        "proposal_list": [],
    }


def test_api_task_complete_marks_feishu_and_mirrors_snapshot(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "none.toml"))
    client, vault = _client(tmp_path, seed_review=False)
    from summit_workbench.repositories.signal_snapshot import read_snapshot, write_snapshot

    day = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    write_snapshot(vault, day, _task_snapshot_payload(day))

    seen: dict[str, object] = {}

    def fake_complete(_client_obj: object, task_guid: str) -> None:
        seen["guid"] = task_guid

    _patch_feishu_task_api(monkeypatch, fake_complete)

    resp = client.post("/api/tasks/complete", json={"task_id": "GUID-1"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["task_id"] == "GUID-1"
    assert "提交样章" in data["message"]  # 镜像成功时消息带任务名
    assert seen["guid"] == "GUID-1"

    # 当日渲染快照被镜像：待办移除 + 关联行动移除 + 计入「最近完成」
    snap = read_snapshot(vault, day)
    assert snap is not None
    task_list = snap["task_list"]
    assert isinstance(task_list, list)
    assert [t.get("task_id") for t in task_list] == ["guid-2"]
    assert snap["tasks"] == 1
    assert snap["actions"] == []
    completions = snap["completion_list"]
    assert isinstance(completions, list)
    assert completions == [{"text": "提交样章", "source_ref": "feishu-task:GUID-1"}]
    assert snap["completions"] == 1
    # /api/state 随即反映：任务从待办消失
    state = client.get("/api/state").json()
    assert state["brief"]["tasks"] == [{"summary": "回邮件", "due_date": None, "task_id": "guid-2"}]


def test_api_task_complete_reports_error_without_touching_snapshot(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "none.toml"))
    client, vault = _client(tmp_path, seed_review=False)
    from summit_workbench.repositories.signal_snapshot import read_snapshot, write_snapshot

    day = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    write_snapshot(vault, day, _task_snapshot_payload(day))

    def fake_complete(_client_obj: object, task_guid: str) -> None:
        raise RuntimeError("飞书授权过期，请重新登录")

    _patch_feishu_task_api(monkeypatch, fake_complete)

    resp = client.post("/api/tasks/complete", json={"task_id": "guid-1"})
    data = resp.json()
    assert data["ok"] is False
    assert "飞书授权过期" in data["message"]
    # 快照不动：任务仍在待办、未计入完成
    snap = read_snapshot(vault, day)
    assert snap is not None
    task_list = snap["task_list"]
    assert isinstance(task_list, list)
    assert [t.get("task_id") for t in task_list] == ["guid-1", "guid-2"]
    assert snap["completion_list"] == []


def test_api_task_complete_ok_even_without_snapshot_entry(tmp_path: Path, monkeypatch) -> None:
    """飞书是真源：即便当日快照没有该任务（尚无简报/晚建任务），完成照常成功。"""
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "none.toml"))
    client, _vault = _client(tmp_path, seed_review=False)
    seen: dict[str, object] = {}

    def fake_complete(_client_obj: object, task_guid: str) -> None:
        seen["guid"] = task_guid

    _patch_feishu_task_api(monkeypatch, fake_complete)
    resp = client.post("/api/tasks/complete", json={"task_id": "outside-snapshot"})
    data = resp.json()
    assert data["ok"] is True
    assert data["message"] == "任务已完成"
    assert seen["guid"] == "outside-snapshot"


def test_api_task_complete_rejects_empty_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "none.toml"))
    client, _vault = _client(tmp_path, seed_review=False)
    called: list[str] = []

    def fake_complete(_client_obj: object, task_guid: str) -> None:
        called.append(task_guid)

    _patch_feishu_task_api(monkeypatch, fake_complete)
    resp = client.post("/api/tasks/complete", json={"task_id": "   "})
    data = resp.json()
    assert data["ok"] is False
    assert "缺少任务 id" in data["message"]
    assert called == []  # 不触发任何飞书写回


# ---------- /api/tasks/update · /api/meetings/update（行内编辑写回） ----------


def _task_snapshot_with_row(day: str) -> dict[str, object]:
    payload = _task_snapshot_payload(day)
    payload["meeting_list"] = [
        {
            "title": "排版会",
            "start_time": "14:00",
            "event_id": "ev-1",
            "start_ts": "1789000000",
            "end_ts": "1789003600",
        }
    ]
    return payload


def _stub_feishu_writes(monkeypatch) -> None:
    """把 /api/tasks|meetings/update 的飞书调用替换为离线替身（写回点不动）。"""

    class _FakeSession:
        def __init__(self, cfg: object, lock_root: Path | None = None) -> None:
            self.cfg = cfg

        def access_token(self) -> SecretStr:
            return SecretStr("tok")

    monkeypatch.setattr(
        "summit_workbench.providers.feishu.FeishuClient", lambda _cfg, _tok: object()
    )
    monkeypatch.setattr("summit_workbench.providers.feishu.FeishuSession", _FakeSession)
    monkeypatch.setattr("summit_workbench.providers.feishu.load_feishu_config", lambda: object())


def test_api_task_update_writes_feishu_and_mirrors_snapshot(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "none.toml"))
    client, vault = _client(tmp_path, seed_review=False)
    from summit_workbench.repositories.signal_snapshot import read_snapshot, write_snapshot

    day = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    write_snapshot(vault, day, _task_snapshot_with_row(day))
    seen: dict[str, object] = {}

    def fake_update(_c: object, guid: str, **kw: object) -> None:
        seen["guid"] = guid
        seen["kw"] = kw

    _stub_feishu_writes(monkeypatch)
    monkeypatch.setattr("summit_workbench.providers.feishu.update_task", fake_update)

    resp = client.post(
        "/api/tasks/update",
        json={"task_id": "guid-1", "summary": "新标题", "due_date": "2026-09-20"},
    )
    data = resp.json()
    assert data["ok"] is True
    assert seen["guid"] == "guid-1"
    kw = seen["kw"]
    assert isinstance(kw, dict)
    assert kw["summary"] == "新标题"
    assert kw["due_date"] == "2026-09-20"
    assert kw["clear_due"] is False
    snap = read_snapshot(vault, day)
    assert snap is not None
    task_list = snap["task_list"]
    assert isinstance(task_list, list)
    assert task_list[0]["summary"] == "新标题"
    assert task_list[0]["due_date"] == "2026-09-20"
    # 清除截止 → 快照里 due_date 清空
    resp = client.post(
        "/api/tasks/update", json={"task_id": "guid-1", "summary": "新标题", "due_date": ""}
    )
    assert resp.json()["ok"] is True
    snap = read_snapshot(vault, day)
    assert snap is not None
    task_list = snap["task_list"]
    assert isinstance(task_list, list)
    assert task_list[0]["due_date"] is None


def test_api_task_update_errors_surface_without_snapshot_change(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "none.toml"))
    client, vault = _client(tmp_path, seed_review=False)
    from summit_workbench.repositories.signal_snapshot import read_snapshot, write_snapshot

    day = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    write_snapshot(vault, day, _task_snapshot_with_row(day))

    def fake_update(_c: object, guid: str, **kw: object) -> None:
        raise RuntimeError("任务不存在")

    _stub_feishu_writes(monkeypatch)
    monkeypatch.setattr("summit_workbench.providers.feishu.update_task", fake_update)
    data = client.post("/api/tasks/update", json={"task_id": "guid-1", "summary": "x"}).json()
    assert data["ok"] is False
    assert "任务不存在" in data["message"]
    snap = read_snapshot(vault, day)
    assert snap is not None
    task_list = snap["task_list"]
    assert isinstance(task_list, list)
    assert task_list[0]["summary"] == "提交样章"  # 快照未动
    # 空标题拒绝（不发飞书写回）
    data = client.post("/api/tasks/update", json={"task_id": "guid-1", "summary": "   "}).json()
    assert data["ok"] is False


def test_api_meeting_update_writes_feishu_and_mirrors_snapshot(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "none.toml"))
    client, vault = _client(tmp_path, seed_review=False)
    from summit_workbench.repositories.signal_snapshot import read_snapshot, write_snapshot

    day = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    write_snapshot(vault, day, _task_snapshot_with_row(day))
    seen: dict[str, object] = {}

    def fake_primary(_c: object) -> str:
        return "cal_main"

    def fake_update(_c: object, calendar_id: str, event_id: str, **kw: object) -> None:
        seen["calendar_id"] = calendar_id
        seen["event_id"] = event_id
        seen["kw"] = kw

    _stub_feishu_writes(monkeypatch)
    monkeypatch.setattr("summit_workbench.providers.feishu.update_event", fake_update)
    monkeypatch.setattr(
        "summit_workbench.providers.feishu.calendar.primary_calendar_id", fake_primary
    )

    resp = client.post(
        "/api/meetings/update",
        json={
            "event_id": "ev-1",
            "summary": "改会名",
            "start_at": "2026-09-10T15:30",
            "end_at": "2026-09-10T16:30",
        },
    )
    data = resp.json()
    assert data["ok"] is True
    assert seen["event_id"] == "ev-1"
    assert seen["calendar_id"] == "cal_main"
    kw = seen["kw"]
    assert isinstance(kw, dict)
    assert kw["summary"] == "改会名"
    assert kw["start_iso"] == "2026-09-10T15:30"
    assert kw["end_iso"] == "2026-09-10T16:30"
    snap = read_snapshot(vault, day)
    assert snap is not None
    meeting_list = snap["meeting_list"]
    assert isinstance(meeting_list, list)
    row = meeting_list[0]
    assert row["title"] == "改会名"
    assert row["start_time"] == "15:30"
    assert row["start_ts"] == "1789025400"
    assert row["end_ts"] == "1789029000"


def test_api_meeting_update_requires_fields(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "none.toml"))
    client, _vault = _client(tmp_path, seed_review=False)
    _stub_feishu_writes(monkeypatch)
    # 只改结束时间不改开始 → 拒绝
    data = client.post(
        "/api/meetings/update",
        json={"event_id": "ev-1", "summary": "会", "end_at": "2026-09-10T16:30"},
    ).json()
    assert data["ok"] is False
    # 无任何字段 → 拒绝
    data = client.post("/api/meetings/update", json={"event_id": "ev-1"}).json()
    assert data["ok"] is False
    assert "没有需要更新" in data["message"]


def test_api_review_edit_saves_meeting_time_fields(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "none.toml"))
    client, vault = _client(tmp_path)
    data = client.get("/api/review").json()
    candidate_id = data["groups"][0]["entries"][0]["candidate_id"]
    resp = client.post(
        "/api/review/edit",
        json={
            "candidate_id": candidate_id,
            "route": "feishu-meeting",
            "start_at": "2026-09-10T14:00",
            "end_at": "2026-09-10T15:00",
        },
    )
    assert resp.json()["ok"] is True
    parsed = parse_review_page((vault / "review" / "meetings.md").read_text(encoding="utf-8"))
    assert parsed.errors == []
    entry = next(e for e in parsed.entries if e.candidate.candidate_id == candidate_id)
    assert entry.candidate.route is not None
    assert entry.candidate.route.value == "feishu-meeting"
    assert entry.candidate.start_at == "2026-09-10T14:00"
    assert entry.candidate.end_at == "2026-09-10T15:00"
