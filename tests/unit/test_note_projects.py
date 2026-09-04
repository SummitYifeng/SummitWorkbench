"""改进 2：merge_note_project 把已解析项目并入多项目笔记 frontmatter（幂等 RMW）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from summit_workbench.repositories.note_projects import merge_note_project
from summit_workbench.repositories.vault import load_note


def _meeting_note(path: Path, *, projects: str = "- unresolved") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        "date: 2026-09-02\n"
        "type: meeting-note\n"
        "status: pending-review\n"
        "idem_key: 'm:n'\n"
        "projects:\n"
        f"{projects}\n"
        "---\n\n"
        "# M\n\n"
        "## 关联项目\n",
        encoding="utf-8",
    )


def test_merge_resolves_unresolved_placeholder(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    note = vault / "meetings" / "notes" / "m.md"
    _meeting_note(note)
    assert merge_note_project(vault, note, "FinanceOps") is True
    assert load_note(note).meta["projects"] == ["FinanceOps"]


def test_merge_appends_alongside_existing_resolved(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    note = vault / "meetings" / "notes" / "m.md"
    _meeting_note(note, projects="- CoachFinance\n- unresolved")
    assert merge_note_project(vault, note, "FinanceOps") is True
    assert load_note(note).meta["projects"] == ["CoachFinance", "FinanceOps"]


def test_merge_is_idempotent_when_project_already_present(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    note = vault / "meetings" / "notes" / "m.md"
    _meeting_note(note, projects="- FinanceOps")
    assert merge_note_project(vault, note, "FinanceOps") is False
    assert load_note(note).meta["projects"] == ["FinanceOps"]


def test_merge_skips_missing_single_scope_and_invalid_project(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    # 单项目笔记（thread-doc）没有 projects 数组 → 无事可做。
    single = vault / "artifacts" / "A-001.md"
    single.parent.mkdir(parents=True)
    single.write_text(
        "---\ndate: 2026-09-03\ntype: thread-doc\nstatus: generated\nproject: A\n---\n\n# A\n",
        encoding="utf-8",
    )
    assert merge_note_project(vault, single, "A") is False
    # 文件不存在 → False。
    assert merge_note_project(vault, vault / "missing.md", "A") is False
    # 非法 project（unresolved / 空）→ False。
    _meeting_note(vault / "meetings" / "notes" / "m.md")
    assert merge_note_project(vault, vault / "meetings" / "notes" / "m.md", "unresolved") is False
    assert merge_note_project(vault, vault / "meetings" / "notes" / "m.md", "") is False


def test_merge_raises_on_unparseable_frontmatter(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    note = vault / "meetings" / "notes" / "bad.md"
    note.parent.mkdir(parents=True)
    note.write_text("---\nprojects: [unclosed\n---\n# B\n", encoding="utf-8")
    with pytest.raises(ValueError, match="无法更新无效笔记"):
        merge_note_project(vault, note, "A")
