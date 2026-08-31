"""``wb vault`` 子命令：校验工作 vault 的 Markdown 结构。"""

from __future__ import annotations

from pathlib import Path

import typer

from summit_workbench.config.settings import load_settings
from summit_workbench.repositories.vault import check_vault, iter_markdown_files

vault_app = typer.Typer(
    name="vault",
    help="工作 vault 相关命令（M0-3：check）。",
    no_args_is_help=True,
    add_completion=False,
)


@vault_app.command("check")
def check(
    path: Path | None = typer.Argument(
        None, help="要校验的 vault 目录；默认取配置解析出的 vault_dir。"
    ),
) -> None:
    """校验 vault 内全部 Markdown 的 frontmatter 与固定区块。

    退出码：全部通过 0；存在问题 1；vault 不存在 2。
    """
    vault_dir = path or load_settings().work_paths().vault_dir
    if not vault_dir.is_dir():
        typer.echo(f"vault 目录不存在：{vault_dir}")
        raise typer.Exit(code=2)

    total = sum(1 for _ in iter_markdown_files(vault_dir))
    results = check_vault(vault_dir)

    if not results:
        typer.echo(f"✓ {vault_dir}：{total} 篇 Markdown 全部通过 schema 校验")
        raise typer.Exit(code=0)

    for file_path, issues in results.items():
        typer.echo(f"✗ {file_path.relative_to(vault_dir)}")
        for issue in issues:
            typer.echo(f"    - {issue}")
    typer.echo("")
    typer.echo(f"{len(results)}/{total} 篇存在问题")
    raise typer.Exit(code=1)
