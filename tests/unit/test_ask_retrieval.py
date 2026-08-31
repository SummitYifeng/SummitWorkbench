"""M1-6：本地召回打分、类型排除与项目过滤。"""

from __future__ import annotations

from pathlib import Path

from summit_workbench.workflows.ask.retrieval import retrieve_candidates


def _note(vault: Path, rel: str, *, note_type: str, project: str, body: str) -> None:
    path = vault / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    scope = f"project: {project}\n" if project != "global" else "project: global\n"
    path.write_text(
        f"---\ndate: 2026-08-31\ntype: {note_type}\nstatus: active\n{scope}---\n\n{body}\n",
        encoding="utf-8",
    )


def _vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    _note(
        vault,
        "projects/HIC_WebClass_Chinese_Final.md",
        note_type="project-main",
        project="HIC_WebClass_Chinese_Final",
        body="# 网课\n\n老师账户由后台代为注册并分配角色。",
    )
    _note(
        vault,
        "projects/HIC_Logistics.md",
        note_type="project-main",
        project="HIC_Logistics",
        body="# 后勤\n\n后勤手册排版进度。",
    )
    # 派生洞察：默认应被排除
    _note(
        vault,
        "insights/old.md",
        note_type="qa-insight",
        project="global",
        body="# 旧洞察\n\n老师账户老师账户老师账户。",
    )
    # 原始逐字稿：默认应被排除
    _note(
        vault,
        "meetings/transcripts/t.md",
        note_type="meeting-transcript",
        project="HIC_WebClass_Chinese_Final",
        body="# 逐字稿\n\n老师账户老师账户老师账户老师账户。",
    )
    return vault


def test_scores_and_excludes_derived_and_transcript(tmp_path):
    results = retrieve_candidates(_vault(tmp_path), "老师账户")
    ids = [c.source_id for c in results]
    assert "projects/HIC_WebClass_Chinese_Final" in ids
    assert "insights/old" not in ids  # qa-insight 排除
    assert "meetings/transcripts/t" not in ids  # 逐字稿排除


def test_project_filter_limits_scope(tmp_path):
    results = retrieve_candidates(_vault(tmp_path), "后勤 账户", project="HIC_Logistics")
    assert [c.source_id for c in results] == ["projects/HIC_Logistics"]


def test_no_match_or_empty_query_returns_empty(tmp_path):
    assert retrieve_candidates(_vault(tmp_path), "完全不相关的词xyz") == []
    assert retrieve_candidates(_vault(tmp_path), "   ") == []


def test_limit_caps_results(tmp_path):
    vault = _vault(tmp_path)
    results = retrieve_candidates(vault, "进度 账户 后勤 网课", limit=1)
    assert len(results) == 1
