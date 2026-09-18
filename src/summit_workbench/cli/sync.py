"""``wb sync`` 子命令：批量安全同步 WORK_ROOT 下的 Git 仓库。"""

from __future__ import annotations

from pathlib import Path

import typer

from summit_workbench.config.profiles import resolve_workspace
from summit_workbench.config.settings import load_settings
from summit_workbench.workflows.sync import SyncStatus, discover_repos, sync_work_root

sync_app = typer.Typer(
    name="sync",
    help="批量同步工作项目与 vault 仓库（git remote 为唯一真源，非破坏性）。",
    no_args_is_help=False,
    add_completion=False,
)


@sync_app.callback(invoke_without_command=True)
def run(
    work_root: Path | None = typer.Option(
        None, "--work-root", help="工作根目录；默认取配置解析出的 WORK_ROOT。"
    ),
) -> None:
    """遍历 WORK_ROOT 下的 git 仓库，安全 pull/push 并逐仓库报告状态。

    只做 fetch + ff-merge + push，绝不 reset/stash/force；dirty 仓库不动工作树。
    退出码：全部无问题 0；存在需人工处理的仓库（无远端/未设 upstream/分叉/网络/推送失败）1。
    """
    root = work_root or load_settings().work_paths().work_root
    if not root.is_dir():
        typer.echo(f"工作根目录不存在：{root}")
        raise typer.Exit(code=2)

    repos = discover_repos(root)
    if not repos:
        typer.echo(f"{root} 下没有 git 仓库")
        raise typer.Exit(code=0)

    resolution = resolve_workspace(allow_env_fallback=True)
    profile = resolution.profile
    results = sync_work_root(
        root,
        workspace_id=profile.workspace_id if profile is not None else None,
        username=profile.git_username if profile is not None else None,
    )
    problems = 0
    for r in results:
        mark = "⚠️" if r.status.is_problem else "✓"
        line = f"{mark} {r.name}：{r.status.value}"
        if r.detail:
            line += f" — {r.detail}"
        typer.echo(line)
        for note in r.notes:
            typer.echo(f"      · {note}")
        if r.status.is_problem:
            problems += 1

    typer.echo("")
    typer.echo(f"共 {len(results)} 个仓库，{problems} 个需人工处理")
    raise typer.Exit(code=1 if problems else 0)


# 便于测试时引用状态枚举
__all__ = ["SyncStatus", "sync_app"]
