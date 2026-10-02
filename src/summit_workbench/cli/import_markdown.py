"""Explicit preview and confirmation commands for selective Markdown imports."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from summit_workbench.workflows.selective_import import (
    ImportCandidate,
    apply_markdown_import,
    candidate_to_dict,
    preview_markdown_import,
)

import_app = typer.Typer(
    name="import", help="预览并选择性导入 Markdown 文件。", no_args_is_help=True
)


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


@import_app.command("preview")
def preview(source: Path) -> None:
    """只读扫描来源文件夹并输出可编辑的选择清单 JSON。"""
    candidates = preview_markdown_import(source)
    typer.echo(
        json.dumps([candidate_to_dict(item) for item in candidates], ensure_ascii=False, indent=2)
    )


@import_app.command("apply")
def apply(source: Path, workspace: Path, selection: Path) -> None:
    """导入选择清单中 selected=true 的条目；旧批准证明会被移除。"""
    raw = json.loads(selection.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise typer.BadParameter("选择清单必须是 preview 命令生成的 JSON 数组")
    candidates = tuple(
        ImportCandidate(
            source_path=str(item["source_path"]),
            content_sha256=str(item["content_sha256"]),
            note_type=_optional_string(item.get("note_type")),
            project=_optional_string(item.get("project")),
            dependencies=tuple(item.get("dependencies", ())),
            missing_dependencies=tuple(item.get("missing_dependencies", ())),
            suggested_path=str(item["suggested_path"]),
            classification=str(item["classification"]),
            warning=_optional_string(item.get("warning")),
        )
        for item in raw
        if isinstance(item, dict) and item.get("selected") is True
    )
    if not candidates:
        typer.echo("没有选中的条目。")
        return
    typer.echo(f"即将导入 {len(candidates)} 项到 {workspace}；来源库保持不变，批准证明将清除。")
    typer.confirm("继续？", abort=True)
    written = apply_markdown_import(source, workspace, candidates)
    typer.echo(json.dumps({"imported": list(written)}, ensure_ascii=False, indent=2))


__all__ = ["import_app"]
