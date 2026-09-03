"""M1-4：项目名/别名 → 规范 ID 的解析器；ADR 0023：工作台精选的建档状态助手。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from summit_workbench.domain.vault import validate_note
from summit_workbench.repositories.project_registry import (
    archive_project,
    create_project_note,
    ensure_project_active,
    load_project_registry,
    read_project_registration,
)
from summit_workbench.repositories.vault import load_note


def _project(vault: Path, project: str, *, aliases: list[str] | None = None) -> None:
    path = vault / "projects" / f"{project}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    alias_line = f"aliases: [{', '.join(aliases)}]\n" if aliases else ""
    path.write_text(
        f"---\nproject: {project}\ndate: 2026-08-31\ntype: project-main\nstatus: active\n"
        f"{alias_line}---\n\n# {project}\n\n## 当前状态\n\n## 下一步\n\n## 阻塞\n\n## 决策记录\n",
        encoding="utf-8",
    )


def test_resolves_canonical_id_and_filename(tmp_path):
    _project(tmp_path, "HIC_WebClass_Chinese_Final")
    registry = load_project_registry(tmp_path)
    assert registry.resolve("HIC_WebClass_Chinese_Final") == "HIC_WebClass_Chinese_Final"
    # 大小写与多余空白不敏感
    assert registry.resolve("  hic_webclass_chinese_final ") == "HIC_WebClass_Chinese_Final"


def test_resolves_natural_language_alias(tmp_path):
    _project(tmp_path, "HIC_WebClass_Chinese_Final", aliases=["网课系统", "网课"])
    registry = load_project_registry(tmp_path)
    assert registry.resolve("网课系统") == "HIC_WebClass_Chinese_Final"
    assert registry.resolve("网课") == "HIC_WebClass_Chinese_Final"


def test_unknown_placeholder_and_empty_return_none(tmp_path):
    _project(tmp_path, "P1")
    registry = load_project_registry(tmp_path)
    assert registry.resolve("从未见过的项目") is None
    assert registry.resolve("unresolved") is None
    assert registry.resolve("") is None
    assert registry.resolve(None) is None


def test_missing_projects_dir_yields_empty_registry(tmp_path):
    registry = load_project_registry(tmp_path)
    assert registry.canonical == frozenset()
    assert registry.resolve("任何名字") is None


def test_global_and_non_project_notes_are_ignored(tmp_path):
    _project(tmp_path, "P1")
    # 系统级笔记不进注册表
    inbox = tmp_path / "projects" / "system.md"
    inbox.write_text(
        "---\nproject: global\ndate: 2026-08-31\ntype: inbox\nstatus: active\n---\n\n# x\n",
        encoding="utf-8",
    )
    registry = load_project_registry(tmp_path)
    assert registry.canonical == frozenset({"P1"})
    assert registry.resolve("global") is None


def test_create_project_note_is_schema_valid_and_resolvable(tmp_path):
    path = create_project_note(tmp_path, "HIC_NewThing", aliases=["新东西", "new thing"])
    note = load_note(path)
    assert note.parse_error is None
    assert validate_note(note.meta, note.body) == []  # 符合 vault schema
    registry = load_project_registry(tmp_path)
    assert registry.resolve("新东西") == "HIC_NewThing"
    assert registry.aliases_by_project["HIC_NewThing"] == ["新东西", "new thing"]


def test_create_project_note_rejects_bad_id_and_duplicates(tmp_path):
    with pytest.raises(ValueError):
        create_project_note(tmp_path, "有空格 的名字")
    create_project_note(tmp_path, "P1")
    with pytest.raises(FileExistsError):
        create_project_note(tmp_path, "P1")


def test_first_project_wins_on_alias_conflict(tmp_path):
    _project(tmp_path, "AProject", aliases=["共享别名"])
    _project(tmp_path, "BProject", aliases=["共享别名"])
    registry = load_project_registry(tmp_path)
    # 按文件名排序，AProject 先出现，结果稳定
    assert registry.resolve("共享别名") == "AProject"


# —— ADR 0023：工作台精选（建档 status 驱动首页显示） ——


def _note_meta(vault: Path, project: str) -> dict[str, object] | None:
    path = vault / "projects" / f"{project}.md"
    if not path.is_file():
        return None
    note = load_note(path)
    assert note.parse_error is None
    return note.meta


def test_read_registration_missing_invalid_and_valid(tmp_path):
    assert read_project_registration(tmp_path, "Nope") == (False, None)
    _project(tmp_path, "P1")
    assert read_project_registration(tmp_path, "P1") == (True, "active")
    # 同名但非 project-main 笔记：不算已建档（与 load_project_registry 同口径）
    (tmp_path / "projects" / "Other.md").write_text(
        "---\nproject: Other\ndate: 2026-08-31\ntype: inbox\nstatus: active\n---\n\n# x\n",
        encoding="utf-8",
    )
    assert read_project_registration(tmp_path, "Other") == (False, None)


def test_ensure_project_active_creates_schema_valid_note(tmp_path):
    path = ensure_project_active(tmp_path, "BrandNew", now=datetime(2026, 9, 3, tzinfo=UTC))
    note = load_note(path)
    assert note.parse_error is None
    assert note.meta["status"] == "active"
    assert validate_note(note.meta, note.body) == []


def test_archive_restore_roundtrip_refreshes_updated(tmp_path):
    _project(tmp_path, "P1")
    archive_project(tmp_path, "P1", now=datetime(2026, 9, 3, tzinfo=UTC))
    meta = _note_meta(tmp_path, "P1")
    assert meta is not None
    assert meta["status"] == "archived"
    assert meta["updated"] == "2026-09-03"
    ensure_project_active(tmp_path, "P1", now=datetime(2026, 9, 4, tzinfo=UTC))
    meta = _note_meta(tmp_path, "P1")
    assert meta is not None
    assert meta["status"] == "active"
    assert meta["updated"] == "2026-09-04"


def test_curation_helpers_are_idempotent_noop(tmp_path):
    _project(tmp_path, "P1")
    ensure_project_active(tmp_path, "P1")
    path = tmp_path / "projects" / "P1.md"
    before = path.read_text(encoding="utf-8")
    ensure_project_active(tmp_path, "P1")  # 已 active：no-op，不改文件
    assert path.read_text(encoding="utf-8") == before
    archive_project(tmp_path, "P1")
    archived_text = path.read_text(encoding="utf-8")
    archive_project(tmp_path, "P1")  # 已 archived：no-op
    assert path.read_text(encoding="utf-8") == archived_text


def test_archive_creates_note_for_unregistered_folder(tmp_path):
    archive_project(tmp_path, "FreshFolder", now=datetime(2026, 9, 3, tzinfo=UTC))
    meta = _note_meta(tmp_path, "FreshFolder")
    assert meta is not None and meta["status"] == "archived"
    ensure_project_active(tmp_path, "FreshFolder")
    meta = _note_meta(tmp_path, "FreshFolder")
    assert meta is not None
    assert meta["status"] == "active"


def test_curation_helpers_reject_invalid_same_name_file(tmp_path):
    (tmp_path / "projects").mkdir(parents=True)
    (tmp_path / "projects" / "Broken.md").write_text("不是一篇笔记", encoding="utf-8")
    with pytest.raises(ValueError):
        ensure_project_active(tmp_path, "Broken")
    with pytest.raises(ValueError):
        archive_project(tmp_path, "Broken")
