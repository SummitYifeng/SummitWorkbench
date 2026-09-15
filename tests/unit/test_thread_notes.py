"""P1：推进日志（work-log）与 AI 产物（thread-doc）的落盘与 Web 端点。

覆盖：多线程关联、原文必存（AI 不可用兜底）、vault schema 自检、端点回退路径。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from summit_workbench.domain.threaddoc import ArtifactKind, LogTag
from summit_workbench.domain.vault import iter_headings, validate_note
from summit_workbench.repositories.thread_notes import append_work_log, save_thread_artifact
from summit_workbench.repositories.vault import load_note
from summit_workbench.webapp.app import WebContext, create_app


def _mk_project(vault: Path, project: str, aliases: list[str] | None = None) -> None:
    path = vault / "projects" / f"{project}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    alias_line = f"aliases: [{', '.join(aliases)}]\n" if aliases else ""
    path.write_text(
        f"---\nproject: {project}\ndate: 2026-09-01\ntype: project-main\nstatus: active\n"
        f"{alias_line}---\n\n# P\n\n## 当前状态\n\n## 下一步\n\n## 阻塞\n\n## 决策记录\n"
        "\n## 跟进事项\n",
        encoding="utf-8",
    )


def test_append_work_log_multi_project_and_schema(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _mk_project(vault, "FinanceOps")
    _mk_project(vault, "CoachFinance")
    path = append_work_log(
        vault,
        projects=["FinanceOps", "CoachFinance"],
        text="和木子对齐 Coach 结算，冯老师确认 1500/次，月底前出 V1.1。",
        summary="木子推进 Coach 财务，冯老师确认收费规则，V1.1 月底前交付。",
        involved=["木子", "冯老师"],
        tags=[LogTag.DECISION, LogTag.ACTION],
        next_step="月底前出 Coach Finance Flow V1.1",
        decision="Coach 单次收费 1500 确认",
        now=datetime(2026, 9, 3, 12, tzinfo=UTC),
    )
    assert path.name == "2026-09-03-001.md"
    assert path.parent == vault / "logs"
    note = load_note(path)
    assert note.parse_error is None
    assert validate_note(note.meta, note.body) == []
    assert note.meta["type"] == "work-log"
    assert note.meta["projects"] == ["FinanceOps", "CoachFinance"]
    assert note.meta["status"] == "generated"
    assert "和木子对齐 Coach 结算" in note.body  # 原文必存
    # 改进 1：日志正文带 [[projects/<id>]] 实体回链（Obsidian 图谱边）
    assert "## 关联项目" in note.body
    assert "- [[projects/FinanceOps]]" in note.body
    assert "- [[projects/CoachFinance]]" in note.body
    # 同一天第二条递增序号
    path2 = append_work_log(
        vault, projects=["FinanceOps"], text="第二条", now=datetime(2026, 9, 3, 13, tzinfo=UTC)
    )
    assert path2.name == "2026-09-03-002.md"
    assert note.meta["involved"] == ["木子", "冯老师"]


def test_append_work_log_requires_text_and_project(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _mk_project(vault, "P1")
    with pytest.raises(ValueError, match="至少"):
        append_work_log(vault, projects=[], text="x")
    with pytest.raises(ValueError, match="不能为空"):
        append_work_log(vault, projects=["P1"], text="   ")


def test_save_thread_artifact_single_project_schema(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _mk_project(vault, "FinanceOps")
    path = save_thread_artifact(
        vault,
        project="FinanceOps",
        text="# 阶段性总结\n\n（很长）…",
        title="Finance Ops 阶段总结 V2",
        summary="木子 Finance Ops 试任期总结，Coach 试点结论。",
        kind=ArtifactKind.SUMMARY,
        now=datetime(2026, 9, 3, 12, tzinfo=UTC),
    )
    assert path.parent == vault / "artifacts"
    note = load_note(path)
    assert note.parse_error is None
    assert validate_note(note.meta, note.body) == []
    assert note.meta["type"] == "thread-doc"
    assert note.meta["project"] == "FinanceOps"
    assert note.meta["title"] == "Finance Ops 阶段总结 V2"
    assert note.meta["kind"] == "summary"
    # 改进 1：产物正文带 [[projects/<id>]] 实体回链
    assert "## 关联项目" in note.body
    assert "- [[projects/FinanceOps]]" in note.body


def _client_with_offline_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """模型不可用时（load_model_config 抛错）端点应回退为「只存原文」。"""
    from summit_workbench.providers.llm import LLMError

    def boom(*_args, **_kwargs):
        raise LLMError("model offline")

    monkeypatch.setattr("summit_workbench.providers.llm.load_model_config", boom)
    work = tmp_path / "Work"
    vault = work / "_vault"
    _mk_project(vault, "FinanceOps", aliases=["财务运营"])
    ctx = WebContext(vault_dir=vault, work_root=work, timezone="Asia/Shanghai")
    return TestClient(create_app(ctx))


def test_log_endpoint_falls_back_to_raw_when_model_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = _client_with_offline_model(tmp_path, monkeypatch)
    r = c.post(
        "/api/threads/logs",
        json={"projects": ["FinanceOps"], "text": "今天和木子确认了 Coach 时间表。"},
    )
    body = r.json()
    assert r.status_code == 200 and body["ok"] is True
    assert body["enriched"] is False
    assert body["summary"] == ""
    assert "仅存原文" in body["message"]
    note_path = Path(body["path"])
    note = load_note(note_path)
    assert validate_note(note.meta, note.body) == []
    assert note.meta["status"] == "draft"


def test_artifact_endpoint_resolves_alias_and_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = _client_with_offline_model(tmp_path, monkeypatch)
    r = c.post(
        "/api/threads/artifacts",
        json={"project": "财务运营", "title": "我的标题", "text": "# 背景包\n\n内容…"},
    )
    body = r.json()
    assert r.status_code == 200 and body["ok"] is True
    assert body["title"] == "我的标题"  # 无模型时沿用用户标题
    note = load_note(Path(body["path"]))
    assert note.meta["project"] == "FinanceOps"
    assert validate_note(note.meta, note.body) == []


def test_artifact_endpoint_rejects_unregistered_project(tmp_path: Path) -> None:
    work = tmp_path / "Work"
    vault = work / "_vault"
    vault.mkdir(parents=True)
    ctx = WebContext(vault_dir=vault, work_root=work, timezone="Asia/Shanghai")
    c = TestClient(create_app(ctx))
    r = c.post("/api/threads/artifacts", json={"project": "Ghost", "text": "x"})
    assert r.json()["ok"] is False
    assert "未建档" in r.json()["message"]


# ---- T2：自动产物的确定性结构规范化 ----


def test_append_work_log_keeps_verbatim_text_and_single_related_block(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _mk_project(vault, "FinanceOps")
    text = "第一行含 # 不是标题\n\n第二行含 [[双链]] 与 `code`：1500/次。"
    path = append_work_log(
        vault,
        projects=["FinanceOps"],
        text=text,
        now=datetime(2026, 9, 3, 12, tzinfo=UTC),
    )
    note = load_note(path)
    assert validate_note(note.meta, note.body) == []
    assert text in note.body  # 原文字符逐字保留
    assert "## 原文" in note.body  # 既有读者（project_view 兜底片段）依赖该区块
    assert note.body.count("## 关联项目") == 1  # 不重复生成关联区块


def test_append_work_log_rejects_duplicate_heading_without_writing(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _mk_project(vault, "FinanceOps")
    with pytest.raises(ValueError, match="规范化"):
        append_work_log(
            vault,
            projects=["FinanceOps"],
            text="## 原文\n\n用户自己又写了一个同名区块。\n",
            now=datetime(2026, 9, 3, 12, tzinfo=UTC),
        )
    assert not (vault / "logs").exists()  # 不落半成品


def test_save_thread_artifact_preserves_existing_h2_and_single_h1(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _mk_project(vault, "FinanceOps")
    path = save_thread_artifact(
        vault,
        project="FinanceOps",
        text="# 背景包\n\n## 背景\n\n原文一段。\n\n### 细节\n\n原文二段。\n",
        title="背景包 V2",
        summary="摘要",
        kind=ArtifactKind.SUMMARY,
        now=datetime(2026, 9, 3, 12, tzinfo=UTC),
    )
    note = load_note(path)
    assert validate_note(note.meta, note.body) == []
    assert [text for level, text in iter_headings(note.body) if level == 1] == ["背景包 V2"]
    assert "## 背景" in note.body  # 已有 H2 不被展平
    assert "### 细节" in note.body  # H3 不被提升
    assert note.body.count("## 关联项目") == 1
    assert "原文一段。" in note.body


def test_save_thread_artifact_rejects_duplicate_heading_without_writing(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _mk_project(vault, "FinanceOps")
    with pytest.raises(ValueError, match="规范化"):
        save_thread_artifact(
            vault,
            project="FinanceOps",
            text="## 关键结论\n\na\n\n## 关键结论\n\nb\n",
            now=datetime(2026, 9, 3, 12, tzinfo=UTC),
        )
    assert not (vault / "artifacts").exists()  # 不落半成品
