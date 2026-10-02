"""日常写入入口：`POST /api/journal/log` 与 `POST /api/journal/thought`。

契约 §1.1/§3/§4.10/§9.1（2026-09-19 起）：
- 日志可**不绑项目**（`project: global`）、`status: active`；
- 思考是 `long-form-thought`（三段必填 + 会被检索）⇒ 落盘前过 schema + 检索就绪，
  不合格拒绝落盘。
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from summit_workbench.domain.retrieval_contract import (
    is_derived_low_authority,
    is_fact_retrieval_eligible,
    validate_retrieval_readiness,
)
from summit_workbench.domain.vault import validate_note
from summit_workbench.repositories.vault import load_note
from summit_workbench.webapp.app import WebContext, create_app


def _mk_project(vault: Path, project: str, aliases: list[str] | None = None) -> Path:
    path = vault / "projects" / f"{project}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    alias_line = f"aliases: [{', '.join(aliases)}]\n" if aliases else ""
    path.write_text(
        f"---\nproject: {project}\ndate: 2026-09-01\ntype: project-main\nstatus: active\n"
        f"{alias_line}---\n\n# P\n\n## 当前状态\n\n## 下一步\n\n## 阻塞\n\n## 决策记录\n"
        "\n## 跟进事项\n",
        encoding="utf-8",
    )
    return path


def _client(tmp_path: Path) -> tuple[TestClient, Path]:
    work = tmp_path / "Work"
    vault = work / "_vault"
    vault.mkdir(parents=True)
    _mk_project(vault, "FinanceOps", aliases=["财务运营"])
    ctx = WebContext(vault_dir=vault, work_root=work, timezone="Asia/Shanghai")
    return TestClient(create_app(ctx)), vault


# ───────────────────────── 日志 ─────────────────────────


def test_log_with_only_did_lands_as_five_block_journal(tmp_path: Path) -> None:
    """只填「今天做了什么」也能落盘：五区块形态 + 无项目 → `project: global`。"""
    client, vault = _client(tmp_path)
    r = client.post("/api/journal/log", json={"did": "今天处理了三件事，明天继续。"})
    body = r.json()
    assert r.status_code == 200 and body["ok"] is True
    assert body["projects"] == []
    assert "不绑项目" in body["message"]
    path = Path(body["path"])
    assert path.parent == vault / "logs"
    note = load_note(path)
    assert note.parse_error is None
    assert validate_note(note.meta, note.body) == []
    assert note.meta["type"] == "work-log"
    assert note.meta["status"] == "active"
    assert note.meta["project"] == "global"
    assert "projects" not in note.meta
    assert is_fact_retrieval_eligible(note.meta) is True
    assert is_derived_low_authority(note.meta) is False
    # 「日常手记」形态：只有填了的那段 + 恒在的 ## 关联；**没有** ## 原文
    assert "## 今天 / 本周做了什么" in note.body
    assert "## 关联" in note.body
    assert "- （无）" in note.body  # 无关联项目时的占位
    assert "今天处理了三件事" in note.body
    assert "## 原文" not in note.body
    # 空段不生成空区块
    assert "## 下一步" not in note.body
    assert "## 进展与变化" not in note.body
    assert "## 卡点与需要谁" not in note.body


def test_log_request_receipt_prevents_duplicate_and_is_queryable(tmp_path: Path) -> None:
    client, vault = _client(tmp_path)
    headers = {"X-WB-Request-Id": "journal-once-001"}
    payload = {"did": "只应保存一次的记录。"}

    first = client.post("/api/journal/log", json=payload, headers=headers)
    second = client.post("/api/journal/log", json=payload, headers=headers)

    assert first.status_code == second.status_code == 200
    assert first.json()["path"] == second.json()["path"]
    assert len(list((vault / "logs").glob("*.md"))) == 1
    receipt = client.get("/api/operations/journal-once-001")
    assert receipt.status_code == 200
    assert receipt.json()["status"] == "completed"
    assert receipt.json()["business_write"] == "succeeded"
    assert receipt.json()["commit_status"] is None
    assert receipt.json()["push_status"] is None
    assert receipt.json()["response"]["path"] == first.json()["path"]


def test_log_request_receipt_rejects_reused_identifier_for_changed_input(tmp_path: Path) -> None:
    client, _vault = _client(tmp_path)
    headers = {"X-WB-Request-Id": "journal-once-002"}
    first = client.post("/api/journal/log", json={"did": "记录 A"}, headers=headers)
    second = client.post("/api/journal/log", json={"did": "记录 B"}, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 409
    assert "不同内容" in second.json()["message"]


def test_log_with_all_four_sections_generates_five_blocks(tmp_path: Path) -> None:
    """四段齐全 ⇒ 五个区块（四段 + `## 关联`），顺序与契约一致。"""
    client, vault = _client(tmp_path)
    r = client.post(
        "/api/journal/log",
        json={
            "did": "今天做了 A。",
            "remaining": "B 还没做。",
            "reflection": "感悟：C。",
            "blockers": "卡在 D。",
            "projects": ["财务运营"],
        },
    )
    body = r.json()
    assert body["ok"] is True
    note = load_note(Path(body["path"]))
    assert validate_note(note.meta, note.body) == []
    assert note.meta["projects"] == ["FinanceOps"]
    assert "project" not in note.meta
    positions = [
        note.body.index("## 今天 / 本周做了什么"),
        note.body.index("## 进展与变化"),
        note.body.index("## 卡点与需要谁"),
        note.body.index("## 下一步"),
        note.body.index("## 关联"),
    ]
    assert positions == sorted(positions)
    assert "- [[projects/FinanceOps]]" in note.body
    assert "- （无）" not in note.body  # 有项目就不写占位


def test_log_without_project_does_not_touch_any_project_activity(tmp_path: Path) -> None:
    """不绑项目时不得刷新任何项目档案的 `activity_at`。"""
    client, vault = _client(tmp_path)
    archive = vault / "projects" / "FinanceOps.md"
    before = archive.read_text(encoding="utf-8")
    r = client.post("/api/journal/log", json={"did": "不属于任何项目的一天。"})
    assert r.json()["ok"] is True
    assert archive.read_text(encoding="utf-8") == before


def test_log_rejects_when_every_section_is_empty(tmp_path: Path) -> None:
    """四段全空 ⇒ 拒绝并点名四段（不落盘）。"""
    client, vault = _client(tmp_path)
    r = client.post("/api/journal/log", json={"did": " ", "remaining": "", "blockers": "\n"})
    body = r.json()
    assert body["ok"] is False
    assert "至少填一段" in body["message"]
    assert "今天做了什么" in body["message"]
    assert not (vault / "logs").exists()


def test_log_rejects_oversized_single_block(tmp_path: Path) -> None:
    """单块超 ~1500 字符 ⇒ 拒绝（超长块会被切成共享同一锚点的子块）。"""
    client, vault = _client(tmp_path)
    r = client.post("/api/journal/log", json={"did": "字" * 1600})
    body = r.json()
    assert body["ok"] is False
    assert "1500" in body["message"] and "写工作思考" in body["message"]
    assert not (vault / "logs").exists()


def test_log_resolves_aliases_and_binds_projects(tmp_path: Path) -> None:
    client, vault = _client(tmp_path)
    r = client.post("/api/journal/log", json={"projects": ["财务运营"], "did": "对齐结算口径。"})
    body = r.json()
    assert body["ok"] is True and body["projects"] == ["FinanceOps"]
    note = load_note(Path(body["path"]))
    assert note.meta["projects"] == ["FinanceOps"]
    assert "project" not in note.meta
    assert note.meta["status"] == "active"


def test_log_rejects_unknown_project(tmp_path: Path) -> None:
    client, _vault = _client(tmp_path)
    r = client.post("/api/journal/log", json={"projects": ["Ghost"], "did": "x"})
    body = r.json()
    assert body["ok"] is False and "未建档" in body["message"]


# ───────────────────────── 工作思考 ─────────────────────────


def _thought_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "problem": "手写日志该不该算低权威内容？",
        "thinking": "日志是使用者的原始记录，不是模型派生内容。",
        "conclusion": "手写日志按 active 处理；只有纯机器生成的才用 generated。",
    }
    payload.update(overrides)
    return payload


def test_thought_rejects_when_a_section_is_missing(tmp_path: Path) -> None:
    """三段缺一即拒绝，且**不落盘**（先校验后写）。"""
    client, vault = _client(tmp_path)
    r = client.post(
        "/api/journal/thought",
        json={"problem": "只有一段", "thinking": "", "conclusion": "结论"},
    )
    body = r.json()
    assert body["ok"] is False
    assert "## 思考展开" in body["message"]
    assert not (vault / "thinking").exists()


def test_thought_passes_schema_and_is_retrieval_ready(tmp_path: Path) -> None:
    client, vault = _client(tmp_path)
    r = client.post("/api/journal/thought", json=_thought_payload())
    body = r.json()
    assert r.status_code == 200 and body["ok"] is True
    path = Path(body["path"])
    assert path.parent == vault / "thinking"
    assert path.name.endswith(".md")
    note = load_note(path)
    assert note.parse_error is None
    assert validate_note(note.meta, note.body) == []
    assert validate_retrieval_readiness(note.meta, note.body) == []
    assert note.meta["type"] == "long-form-thought"
    assert note.meta["status"] == "active"
    assert note.meta["project"] == "global"
    # §2.1 本库叠加必填（非机器写入页）
    for field in ("id", "title", "area", "workstream", "created", "updated", "summary"):
        assert note.meta.get(field) not in (None, ""), field
    assert note.meta["area"] == "work"
    assert note.meta["workstream"] == "cross"
    # 三段固定区块都在
    for block in ("## 问题缘起", "## 思考展开", "## 当前结论"):
        assert block in note.body
    # 目录按需创建，不放 .gitkeep 占位（契约 §1 的空目录例外只给两类）
    assert not (vault / "thinking" / ".gitkeep").exists()


def test_thought_derives_title_and_summary_and_honours_overrides(tmp_path: Path) -> None:
    client, _vault = _client(tmp_path)
    r = client.post(
        "/api/journal/thought",
        json=_thought_payload(projects=["财务运营"], title="Coach 财务口径", workstream="company"),
    )
    assert r.json()["ok"] is True
    note = load_note(Path(r.json()["path"]))
    assert note.meta["title"] == "Coach 财务口径"
    assert note.meta["workstream"] == "company"
    assert note.meta["projects"] == ["FinanceOps"]
    assert "project" not in note.meta
    # 摘要缺省时由「当前结论」首句派生
    summary = note.meta["summary"]
    assert isinstance(summary, str) and summary.startswith("手写日志按 active 处理")


def test_thought_rejects_invalid_workstream(tmp_path: Path) -> None:
    client, _vault = _client(tmp_path)
    r = client.post("/api/journal/thought", json=_thought_payload(workstream="hr"))
    body = r.json()
    assert body["ok"] is False and "不在词表" in body["message"]


def test_thought_rejects_duplicate_citable_heading(tmp_path: Path) -> None:
    """检索就绪校验在落盘前生效：正文里重复 `##` 可引用标题 ⇒ 拒绝，不写文件。"""
    client, vault = _client(tmp_path)
    r = client.post(
        "/api/journal/thought",
        json=_thought_payload(
            thinking="## 问题缘起\n\n用户自己又写了一个同名区块。\n",
        ),
    )
    body = r.json()
    assert body["ok"] is False
    assert "重复" in body["message"] or "检索就绪" in body["message"]
    assert not (vault / "thinking").exists()
