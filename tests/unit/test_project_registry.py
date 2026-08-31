"""M1-4：项目名/别名 → 规范 ID 的解析器。"""

from __future__ import annotations

from pathlib import Path

from summit_workbench.repositories.project_registry import load_project_registry


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


def test_first_project_wins_on_alias_conflict(tmp_path):
    _project(tmp_path, "AProject", aliases=["共享别名"])
    _project(tmp_path, "BProject", aliases=["共享别名"])
    registry = load_project_registry(tmp_path)
    # 按文件名排序，AProject 先出现，结果稳定
    assert registry.resolve("共享别名") == "AProject"
