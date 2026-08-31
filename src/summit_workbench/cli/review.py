"""``wb review``：刷新集中审批页，默认 dry-run 地批量应用。"""

from __future__ import annotations

from functools import lru_cache

import typer

from summit_workbench.config.settings import load_settings
from summit_workbench.providers.feishu import (
    FeishuClient,
    FeishuError,
    FeishuSession,
    create_task,
    load_feishu_config,
)
from summit_workbench.workflows.review import refresh_meeting_review
from summit_workbench.workflows.review_apply import apply_meeting_review

review_app = typer.Typer(
    name="review",
    help="会议提取集中审批（refresh / apply；apply 默认只预演）。",
    no_args_is_help=True,
    add_completion=False,
)


@review_app.command("refresh")
def refresh() -> None:
    """扫描 pending-review 会议笔记并幂等刷新 review/meetings.md。"""
    paths = load_settings().work_paths()
    try:
        report = refresh_meeting_review(paths.vault_dir)
    except ValueError as exc:
        typer.echo(f"✗ 审批页刷新失败：{exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"✓ 审批页：{report.outcome.path}")
    typer.echo(
        f"  扫描笔记={report.notes_scanned}  候选={report.candidates_found}  "
        f"新增={report.outcome.added}  保留={report.outcome.preserved}"
    )


@review_app.command("apply")
def apply_review(
    execute: bool = typer.Option(
        False,
        "--apply",
        help="实际执行已批准/拒绝条目；省略时只显示 dry-run 计划。",
    ),
) -> None:
    """预演或显式应用审批结果；仅编辑审批页永远不会触发写回。"""
    settings = load_settings()
    paths = settings.work_paths()

    @lru_cache(maxsize=1)
    def task_client() -> FeishuClient:
        cfg = load_feishu_config()
        return FeishuClient(cfg, FeishuSession(cfg).access_token())

    def create(summary: str, due_date: str | None, candidate_id: str) -> str:
        return create_task(
            task_client(),
            summary,
            due_date,
            candidate_id,
            timezone=settings.timezone,
        ).guid

    try:
        report = apply_meeting_review(
            paths.vault_dir,
            paths.work_root,
            apply=execute,
            task_creator=create if execute else None,
        )
    except (ValueError, FeishuError) as exc:
        typer.echo(f"✗ 审批应用失败：{exc}")
        raise typer.Exit(code=1) from exc

    typer.echo("DRY-RUN（零写入）" if report.dry_run else "已显式应用")
    for action in report.actions:
        icon = "✓" if action.executable else "✗"
        detail = f"  原因：{action.reason}" if action.reason else ""
        typer.echo(
            f"{icon} {action.candidate_id}  {action.decision.value} → "
            f"{action.destination}{detail}"
        )
    typer.echo(
        f"结果：批准写回={report.applied}  拒绝归档={report.rejected}  失败={report.failed}"
    )
    if report.archive_path is not None:
        typer.echo(f"审计：{report.archive_path}")
    if report.failed:
        raise typer.Exit(code=1)
