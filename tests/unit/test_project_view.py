"""P2：线视图聚合（project_view）与日志/产物写入后档案 updated 自动刷新。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from fastapi.testclient import TestClient

from summit_workbench.repositories.project_view import build_project_view
from summit_workbench.repositories.thread_notes import append_work_log, save_thread_artifact
from summit_workbench.repositories.vault import load_note
from summit_workbench.webapp.app import WebContext, create_app


def _archive(vault: Path, project: str = "FinanceOps", *, aliases: list[str] | None = None) -> None:
    path = vault / "projects" / f"{project}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    alias_line = f"aliases: [{', '.join(aliases)}]\n" if aliases else ""
    path.write_text(
        f"---\nproject: {project}\ndate: 2026-09-01\ntype: project-main\nstatus: active\n"
        f"updated: '2026-09-02'\n{alias_line}---\n\n"
        f"# {project}\n\n## 当前状态\n木子在试任 Finance Ops\n\n## 下一步\n- 月底前出 V1.1\n\n"
        "## 阻塞\n无\n\n## 决策记录\n- Coach 单次 1500 确认\n\n"
        "## 跟进事项\n- [ ] 木子月底前出 Coach V1.1\n- [x] 冯老师确认收费规则\n",
        encoding="utf-8",
    )


def _meeting_note(vault: Path, project: str, day: str = "2026-09-02") -> None:
    path = vault / "meetings" / "notes" / f"{day}-测试会议.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\ndate: 2026-09-02\ntype: meeting-note\nstatus: generated\n"
        f"projects: [{project}]\n---\n\n# 测试会议\n\n## 一分钟摘要\n定了 Coach 规则。\n",
        encoding="utf-8",
    )


def test_build_project_view_blocks_and_counts(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _archive(vault)
    # 时间线数据：日志两条 + 产物一条 + 会议一条
    append_work_log(
        vault,
        projects=["FinanceOps"],
        text="和木子对齐结算。",
        summary="对齐了老师结算口径。",
        now=datetime(2026, 9, 1, 9, tzinfo=UTC),
    )
    append_work_log(
        vault,
        projects=["FinanceOps"],
        text="冯老师确认 1500。",
        summary="确认单次收费 1500。",
        now=datetime(2026, 9, 3, 10, tzinfo=UTC),
    )
    save_thread_artifact(
        vault,
        project="FinanceOps",
        text="# 背景包\n\n内容",
        title="背景包 V1",
        summary="新对话背景包。",
        now=datetime(2026, 9, 3, 11, tzinfo=UTC),
    )
    _meeting_note(vault, "FinanceOps")
    inbox = vault / "inboxes" / "FinanceOps.md"
    inbox.parent.mkdir(parents=True, exist_ok=True)
    inbox.write_text(
        "---\ndate: 2026-09-03\ntype: project-inbox\nstatus: active\nproject: FinanceOps\n---\n\n"
        "## 待处理条目\n- [ ] 一个想法\n",
        encoding="utf-8",
    )

    view = build_project_view(vault, "FinanceOps")
    blocks = cast(dict[str, list[str]], view["blocks"])
    assert blocks["下一步"] == ["- 月底前出 V1.1"]
    assert blocks["决策记录"] == ["- Coach 单次 1500 确认"]
    assert view["followup_pending"] == 1  # 只有未勾选那条
    assert view["inbox_pending"] == 1
    timeline = cast(list[dict[str, str]], view["timeline"])
    kinds = [item["kind"] for item in timeline]
    assert kinds == ["thread-doc", "work-log", "meeting-note", "work-log"]  # 按日期倒序
    # 时间线命中正确且带摘要
    by_kind = {item["kind"]: item for item in timeline}
    assert by_kind["thread-doc"]["snippet"] == "新对话背景包。"
    assert by_kind["meeting-note"]["snippet"] == "定了 Coach 规则。"
    # 未建档报错
    import pytest

    with pytest.raises(ValueError, match="未建档"):
        build_project_view(vault, "Ghost")


def test_log_artifact_write_refreshes_activity_not_updated(tmp_path: Path) -> None:
    """S1：只写日志/产物 → 档案 updated 不变（实质更新语义），activity_at 刷新（活动痕迹）。"""
    vault = tmp_path / "vault"
    _archive(vault)  # updated: '2026-09-02'
    append_work_log(
        vault,
        projects=["FinanceOps"],
        text="新进展。",
        summary="今天有推进。",
        now=datetime(2026, 9, 5, 12, tzinfo=UTC),
    )
    note = load_note(vault / "projects" / "FinanceOps.md")
    assert note.meta["updated"] == "2026-09-02"  # 实质更新不被机器活动刷新
    assert note.meta["activity_at"] == "2026-09-05"
    assert "## 决策记录" in note.body  # 正文未被触碰
    save_thread_artifact(
        vault,
        project="FinanceOps",
        text="x",
        now=datetime(2026, 9, 6, 12, tzinfo=UTC),
    )
    note2 = load_note(vault / "projects" / "FinanceOps.md")
    assert note2.meta["updated"] == "2026-09-02"
    assert note2.meta["activity_at"] == "2026-09-06"
    # 线视图载荷同时带 updated 与 activity_at（读侧归一）
    view = build_project_view(vault, "FinanceOps")
    assert view["updated"] == "2026-09-02"
    assert view["activity_at"] == "2026-09-06"


def test_view_endpoint_resolves_alias(tmp_path: Path) -> None:
    vault = tmp_path / "Work" / "_vault"
    _archive(vault, aliases=["财务运营"])
    ctx = WebContext(vault_dir=vault, work_root=vault.parent, timezone="Asia/Shanghai")
    c = TestClient(create_app(ctx))
    r = c.get("/api/projects/view", params={"name": "财务运营"})
    body = r.json()
    assert r.status_code == 200 and body["ok"] is True
    assert body["name"] == "FinanceOps"
    assert body["followup_pending"] == 1


def test_build_project_view_unquoted_updated_is_normalized(tmp_path: Path) -> None:
    """frontmatter 的 updated 未加引号（YAML 解析成 date 对象）也应读出 YYYY-MM-DD。"""
    vault = tmp_path / "vault"
    path = vault / "projects" / "FinanceOps.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\nproject: FinanceOps\ndate: 2026-09-01\ntype: project-main\nstatus: active\n"
        "updated: 2026-09-02\n---\n\n# FinanceOps\n\n## 当前状态\n\n## 下一步\n\n"
        "## 阻塞\n无\n\n## 决策记录\n\n## 跟进事项\n",
        encoding="utf-8",
    )
    view = build_project_view(vault, "FinanceOps")
    assert view["updated"] == "2026-09-02"
    assert view["status"] == "active"
