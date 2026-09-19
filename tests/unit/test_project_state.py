"""P3：主档案「当前状态」草案写回（set_project_status）与端点。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from summit_workbench.domain.vault import validate_note
from summit_workbench.repositories.vault import load_note
from summit_workbench.repositories.writeback import set_project_status
from summit_workbench.webapp.app import WebContext, create_app


def _archive(vault: Path, project: str = "FinanceOps", *, aliases: list[str] | None = None) -> Path:
    path = vault / "projects" / f"{project}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    alias_line = f"aliases: [{', '.join(aliases)}]\n" if aliases else ""
    path.write_text(
        f"---\nproject: {project}\ndate: 2026-09-01\ntype: project-main\nstatus: active\n"
        f"updated: '2026-09-02'\n{alias_line}---\n\n# {project}\n\n"
        "## 当前状态\n旧状态第一行\n旧状态第二行\n\n"
        "## 下一步\n- 月底前出 V1.1\n\n## 阻塞\n无\n\n## 决策记录\n\n## 跟进事项\n",
        encoding="utf-8",
    )
    return path


def test_set_project_status_replaces_only_status_block(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    path = _archive(vault)
    set_project_status(vault, "FinanceOps", "木子试任 Finance Ops，Coach V1.1 进行中。")
    note = load_note(path)
    assert note.parse_error is None
    assert validate_note(note.meta, note.body) == []
    # 只动「当前状态」区块
    assert (
        "木子试任 Finance Ops，Coach V1.1 进行中。"
        in note.body.split("## 当前状态")[1].split("## 下一步")[0]
    )
    assert "- 月底前出 V1.1" in note.body  # 下一步原样保留
    assert note.meta["updated"] == "2026-09-02"  # helper 不碰 frontmatter


def test_set_project_status_keeps_a_single_blank_before_the_next_block(tmp_path: Path) -> None:
    """回归守卫：「文本 + 空行」接入下一个区块时不得留下区块尾随空行（双空行）。

    与 `writeback._append_under_heading` 同一形状的缺陷：把尾随空行留在 `lines[end:]` 里
    就会和调用方补的空行叠成两个（2026-09-19 收件箱提升真机实测同源）。
    """
    vault = tmp_path / "vault"
    path = _archive(vault)
    set_project_status(vault, "FinanceOps", "木子试任 Finance Ops。")
    text = path.read_text(encoding="utf-8")
    assert "\n\n\n" not in text
    assert "木子试任 Finance Ops。\n\n## 下一步" in text


def test_set_project_status_requires_archive(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    import pytest

    with pytest.raises(ValueError, match="写回目标不存在"):
        set_project_status(vault, "Ghost", "x")


def test_state_endpoint_resolves_alias_and_updates_updated(tmp_path: Path) -> None:
    vault = tmp_path / "Work" / "_vault"
    _archive(vault, aliases=["财务运营"])
    ctx = WebContext(vault_dir=vault, work_root=vault.parent, timezone="Asia/Shanghai")
    c = TestClient(create_app(ctx))
    r = c.post(
        "/api/threads/state",
        json={"project": "财务运营", "text": "草案：木子 Finance Ops 试任中。"},
    )
    body = r.json()
    assert r.status_code == 200 and body["ok"] is True
    note = load_note(vault / "projects" / "FinanceOps.md")
    status_block = note.body.split("## 当前状态")[1].split("## 下一步")[0]
    assert "草案：木子 Finance Ops 试任中。" in status_block
    assert note.meta["updated"]  # 端点刷新 updated（今天是有效日期即可）
    # 未建档拒绝
    r2 = c.post("/api/threads/state", json={"project": "Ghost", "text": "x"})
    assert r2.json()["ok"] is False
    # 空文本拒绝
    r3 = c.post("/api/threads/state", json={"project": "FinanceOps", "text": "  "})
    assert r3.json()["ok"] is False


def test_rename_endpoint_sets_title_and_state_exposes_it(tmp_path: Path) -> None:
    vault = tmp_path / "Work" / "_vault"
    _archive(vault, aliases=["财务运营"])
    ctx = WebContext(vault_dir=vault, work_root=vault.parent, timezone="Asia/Shanghai")
    c = TestClient(create_app(ctx))
    r = c.post(
        "/api/projects/rename",
        json={"name": "财务运营", "title": "财务运营体系建设"},
    )
    body = r.json()
    assert r.status_code == 200 and body["ok"] is True
    note = load_note(vault / "projects" / "FinanceOps.md")
    assert note.meta["title"] == "财务运营体系建设"
    assert note.meta["updated"]  # 改名也刷新更新时间
    # /api/state 的项目列表带 title（前端展示显示名）
    st = c.get("/api/state").json()
    entry = next(p for p in st["projects"] if p["name"] == "FinanceOps")
    assert entry["title"] == "财务运营体系建设"
    # 空显示名拒绝
    r2 = c.post("/api/projects/rename", json={"name": "FinanceOps", "title": "  "})
    assert r2.json()["ok"] is False


def test_state_payload_carries_activity_at(tmp_path: Path) -> None:
    """/api/state 项目载荷带 activity_at（P1 读侧）；日志活动只刷新活动痕迹。"""
    vault = tmp_path / "Work" / "_vault"
    _archive(vault)
    from summit_workbench.repositories.note_status import update_note_status

    update_note_status(
        vault,
        vault / "projects" / "FinanceOps.md",
        "active",
        extra={"activity_at": "2026-09-05"},  # 模拟一次推进日志入库的 touch
    )
    ctx = WebContext(vault_dir=vault, work_root=vault.parent, timezone="Asia/Shanghai")
    r = TestClient(create_app(ctx)).get("/api/state")
    assert r.status_code == 200
    proj = next(p for p in r.json()["projects"] if p["name"] == "FinanceOps")
    assert proj["activity_at"] == "2026-09-05"
    assert proj["updated"] == "2026-09-02"  # updated 未被日志 touch 刷新
