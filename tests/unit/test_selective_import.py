from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from summit_workbench.domain.approval import approval_record, has_valid_approval
from summit_workbench.repositories.vault import parse_frontmatter
from summit_workbench.workflows.selective_import import (
    apply_markdown_import,
    preview_markdown_import,
)


def test_preview_is_read_only_and_reports_links_and_missing_dependencies(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    source.mkdir()
    note = source / "note.md"
    note.write_text(
        "---\ntype: note\nstatus: active\ntitle: Note\n---\n\n[[known]] [[missing]]\n",
        encoding="utf-8",
    )
    (source / "known.md").write_text("# Known\n", encoding="utf-8")

    candidates = preview_markdown_import(source)

    assert [item.source_path for item in candidates] == ["known.md", "note.md"]
    selected = next(item for item in candidates if item.source_path == "note.md")
    assert selected.classification == "review"
    assert selected.dependencies == ("known", "missing")
    assert selected.missing_dependencies == ("missing",)
    assert note.read_text(encoding="utf-8").endswith("[[known]] [[missing]]\n")


def test_preview_rejects_symlink_outside_source_root(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    source.mkdir()
    (tmp_path / "private.md").write_text("private", encoding="utf-8")
    (source / "linked.md").symlink_to(tmp_path / "private.md")
    with pytest.raises(ValueError, match="escapes selected folder"):
        preview_markdown_import(source)


def test_import_is_explicit_idempotent_and_drops_legacy_approval(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    source.mkdir()
    source_note = source / "note.md"
    metadata = {"type": "note", "status": "active", "title": "Note"}
    body = "# Note\n\nConfirmed text.\n"
    metadata["approval"] = approval_record(metadata, body, operation_id="old-operation")
    source_note.write_text(
        "---\n" + yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False) + "---\n" + body,
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    preview = preview_markdown_import(source)
    assert not list(workspace.iterdir())

    written = apply_markdown_import(source, workspace, preview)
    imported = workspace / written[0]
    imported_meta, imported_body, error = parse_frontmatter(imported.read_text(encoding="utf-8"))
    assert error is None
    assert "approval" not in imported_meta
    assert not has_valid_approval(imported_meta, imported_body)
    assert source_note.exists()
    assert apply_markdown_import(source, workspace, preview) == written


def test_import_rejects_changed_source_and_conflicting_target(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    source.mkdir()
    note = source / "note.md"
    note.write_text("---\ntype: note\nstatus: active\n---\nBody\n", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    preview = preview_markdown_import(source)

    note.write_text("changed\n", encoding="utf-8")
    try:
        apply_markdown_import(source, workspace, preview)
    except ValueError as exc:
        assert "source changed" in str(exc)
    else:
        raise AssertionError("stale preview should not import")

    current = preview_markdown_import(source)
    target = workspace / current[0].suggested_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("different\n", encoding="utf-8")
    try:
        apply_markdown_import(source, workspace, current)
    except FileExistsError:
        pass
    else:
        raise AssertionError("conflicting target should not be overwritten")
