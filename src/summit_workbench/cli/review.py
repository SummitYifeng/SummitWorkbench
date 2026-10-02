"""``wb review``：刷新集中审批页，默认 dry-run 地批量应用。"""

from __future__ import annotations

from datetime import date
from functools import lru_cache

import typer

from summit_workbench.config.locking import LockBusy
from summit_workbench.config.settings import load_settings
from summit_workbench.providers.feishu import (
    FeishuClient,
    FeishuError,
    FeishuSession,
    create_task,
    load_feishu_config,
)
from summit_workbench.providers.feishu.meetings import verify_identity
from summit_workbench.repositories.review_edit import ReviewEditError
from summit_workbench.workflows.review import refresh_meeting_review
from summit_workbench.workflows.review_apply import apply_meeting_review
from summit_workbench.workflows.review_sweep import sweep_meeting_review

review_app = typer.Typer(
    name="review",
    help="会议提取集中审批（refresh / apply / sweep；apply 与 sweep 默认只预演）。",
    no_args_is_help=True,
    add_completion=False,
)


@review_app.command("refresh")
def refresh() -> None:
    """扫描 pending-review 会议笔记并幂等刷新 review/meetings.md。"""
    paths = load_settings().work_paths()
    try:
        report = refresh_meeting_review(paths.vault_dir)
    except LockBusy as exc:
        typer.echo(f"✗ 工作区忙，稍后重试：{exc}")
        raise typer.Exit(code=1) from exc
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
        # P0-06：Feishu refresh 锁根取本 workspace 单一解析入口的 lock_root。
        return FeishuClient(cfg, FeishuSession(cfg, lock_root=paths.lock_root).access_token())

    @lru_cache(maxsize=1)
    def current_open_id() -> str | None:
        """当前授权用户的 open_id。

        新建任务必须带 ``assignee``，否则飞书只记 creator 而不指派给本人，任务不会出现在
        用户自己的任务清单里——而今日简报读的正是那份清单。
        """
        return str(verify_identity(task_client()).get("open_id") or "") or None

    def create(
        summary: str,
        due_date: str | None,
        candidate_id: str,
        *,
        operation_id: str | None = None,
        start_at: str | None = None,
    ) -> str:
        return create_task(
            task_client(),
            summary,
            due_date,
            candidate_id,
            timezone=settings.timezone,
            start_date=start_at,
            operation_id=operation_id,
            assignee_open_id=current_open_id(),
        ).guid

    try:
        report = apply_meeting_review(
            paths.vault_dir,
            paths.work_root,
            apply=execute,
            task_creator=create if execute else None,
        )
    except LockBusy as exc:
        typer.echo(f"✗ 工作区忙，稍后重试：{exc}")
        raise typer.Exit(code=1) from exc
    except (ValueError, FeishuError) as exc:
        typer.echo(f"✗ 审批应用失败：{exc}")
        raise typer.Exit(code=1) from exc

    typer.echo("DRY-RUN（零写入）" if report.dry_run else "已显式应用")
    for action in report.actions:
        icon = "✓" if action.executable else "✗"
        detail = f"  原因：{action.reason}" if action.reason else ""
        typer.echo(
            f"{icon} {action.candidate_id}  {action.decision.value} → {action.destination}{detail}"
        )
    typer.echo(f"结果：批准写回={report.applied}  拒绝归档={report.rejected}  失败={report.failed}")
    if report.archive_path is not None:
        typer.echo(f"审计：{report.archive_path}")
    if report.failed:
        raise typer.Exit(code=1)


@review_app.command("sweep")
def sweep_review(
    execute: bool = typer.Option(
        False,
        "--apply",
        help="实际退役笔记（置 ignored）并批量拒绝其候选；省略时只显示计划。",
    ),
    before: str | None = typer.Option(
        None,
        "--before",
        help="只清理会议日期早于该日（YYYY-MM-DD）的笔记，用于一次性清掉测试会议。",
    ),
) -> None:
    """一键清理测试/旧会议：笔记正文保留、状态置 ignored，其候选批量拒绝归档。"""
    paths = load_settings().work_paths()
    try:
        report = sweep_meeting_review(
            paths.vault_dir,
            apply=execute,
            before=date.fromisoformat(before) if before else None,
        )
    except LockBusy as exc:
        typer.echo(f"✗ 工作区忙，稍后重试：{exc}")
        raise typer.Exit(code=1) from exc
    except (ValueError, ReviewEditError) as exc:
        typer.echo(f"✗ 清扫失败：{exc}")
        raise typer.Exit(code=1) from exc
    typer.echo("DRY-RUN（零写入）" if report.dry_run else "已清扫（正文原文保留）")
    for path in report.notes:
        typer.echo(f"  {path.name}")
    typer.echo(f"结果：会议笔记={len(report.notes)}  涉及候选={report.candidates}")
    if report.dry_run and report.notes:
        typer.echo("确认无误后加 --apply 执行。")
