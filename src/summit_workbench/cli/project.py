"""``wb project``：第二大脑侧项目主笔记的创建与查看。

多数会议未必对应已导入的项目；随着 workbench 梳理出新工作流会产生新项目。这里让新项目
在第二大脑里快速建档（不触碰任何 GitHub 仓库），建档后即可被后续会议审批解析命中。
"""

from __future__ import annotations

import typer

from summit_workbench.config.settings import load_settings
from summit_workbench.repositories.project_registry import (
    create_project_note,
    load_project_registry,
)

project_app = typer.Typer(name="project", help="项目主笔记的创建与查看（第二大脑侧）。")


@project_app.command("new")
def new(
    project_id: str = typer.Argument(..., help="规范项目 ID（字母/数字/下划线/连字符）。"),
    alias: list[str] = typer.Option(
        [], "--alias", "-a", help="自然语言别名，可重复；会议里这样称呼时能解析回该项目。"
    ),
) -> None:
    """新建一篇 project-main 笔记；已存在则报错，绝不覆盖历史。"""
    vault_dir = load_settings().work_paths().vault_dir
    try:
        path = create_project_note(vault_dir, project_id, aliases=alias or None)
    except (ValueError, FileExistsError) as exc:
        typer.echo(f"✗ {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"✓ 已创建项目笔记：{path}")
    if alias:
        typer.echo(f"  别名：{', '.join(alias)}")


@project_app.command("list")
def list_projects() -> None:
    """列出已建项目及其别名（审批写回可用的规范 ID）。"""
    vault_dir = load_settings().work_paths().vault_dir
    registry = load_project_registry(vault_dir)
    if not registry.canonical:
        typer.echo("（暂无项目主笔记，用 wb project new <ID> 创建）")
        return
    for project_id in sorted(registry.canonical):
        aliases = registry.aliases_by_project.get(project_id, [])
        suffix = f"  ← {', '.join(aliases)}" if aliases else ""
        typer.echo(f"{project_id}{suffix}")
