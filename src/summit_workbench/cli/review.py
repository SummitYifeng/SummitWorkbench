"""``wb review``：刷新集中审批页，默认 dry-run 地批量应用。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from functools import lru_cache

import typer

from summit_workbench.config.locking import LockBusy
from summit_workbench.config.settings import load_settings
from summit_workbench.providers.feishu import (
    FeishuClient,
    FeishuError,
    FeishuSession,
    create_event,
    create_task,
    load_feishu_config,
)
from summit_workbench.providers.feishu.calendar import primary_calendar_id
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

    def create(
        summary: str,
        due_date: str | None,
        candidate_id: str,
        *,
        operation_id: str | None = None,
    ) -> str:
        return create_task(
            task_client(),
            summary,
            due_date,
            candidate_id,
            timezone=settings.timezone,
            operation_id=operation_id,
        ).guid

    def create_meeting(
        summary: str,
        start_at: str | None,
        end_at: str | None,
        candidate_id: str,
        *,
        operation_id: str | None = None,
    ) -> str:
        """审批「新建会议」写回器；行为与 webapp 一致（缺省结束 = 开始 + 60 分钟）。

        此前 CLI 只注入了 task_creator，导致 `feishu-meeting` 落点必然失败并报
        「缺少飞书日历会议创建器」——该落点只能从面板应用。这里补齐，使 CLI 与
        面板具备同等能力。
        """
        if start_at is None:
            raise ValueError("新建会议需要开始时间")
        start = datetime.fromisoformat(start_at).replace(tzinfo=None)
        end_iso = (
            end_at
            if end_at is not None
            else (start + timedelta(minutes=60)).strftime("%Y-%m-%dT%H:%M")
        )
        client = task_client()
        return create_event(
            client,
            primary_calendar_id(client),
            summary,
            start_at,
            end_iso,
            timezone=settings.timezone,
            candidate_id=candidate_id,
            operation_id=operation_id,
        )

    try:
        report = apply_meeting_review(
            paths.vault_dir,
            paths.work_root,
            apply=execute,
            task_creator=create if execute else None,
            meeting_creator=create_meeting if execute else None,
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
    if execute and report.notes:
        # 顺带收口（P0'）：清扫成功后自动留痕（笔记状态 + 审批页），失败可见不阻断。
        from summit_workbench.repositories.autocommit import commit_paths
        from summit_workbench.repositories.review_page import review_path

        commit_result = commit_paths(
            paths.vault_dir,
            [*report.notes, review_path(paths.vault_dir)],
            message=f"wb: review sweep 退役 {len(report.notes)} 篇笔记",
        )
        if commit_result.status.value.startswith(("committed", "reverted")):
            typer.echo(f"✓ git：已自动留痕（{commit_result.status.value}）")
        elif commit_result.status.value not in ("not-git", "nothing-to-commit"):
            typer.echo(f"⚠ git 留痕失败：{commit_result.detail or commit_result.status.value}")
    typer.echo("DRY-RUN（零写入）" if report.dry_run else "已清扫（正文原文保留）")
    for path in report.notes:
        typer.echo(f"  {path.name}")
    typer.echo(f"结果：会议笔记={len(report.notes)}  涉及候选={report.candidates}")
    if report.dry_run and report.notes:
        typer.echo("确认无误后加 --apply 执行。")
