"""``wb weekly``：生成上一自然周的跨项目周复盘（M2-10）。"""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import typer

from summit_workbench.config.settings import default_config_file, load_settings
from summit_workbench.domain.run_health import RunStatus
from summit_workbench.observability.heartbeat import record_run_safely
from summit_workbench.observability.status import build_status
from summit_workbench.workflows.brief.publish import publish_brief
from summit_workbench.workflows.weekly.weekly import generate_weekly


def weekly_command(
    date_opt: str | None = typer.Option(
        None, "--date", help="参考日期 YYYY-MM-DD（默认今天）；复盘其上一自然周。"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="只渲染打印，不写文件。"),
    commit: bool = typer.Option(
        False, "--commit", help="把周复盘笔记提交到 vault（只暂存该文件，供 launchd）。"
    ),
    push: bool = typer.Option(False, "--push", help="提交后推送（需 --commit）。"),
    as_json: bool = typer.Option(False, "--json", help="以 JSON 输出结构化结果。"),
) -> None:
    """从 git + 会议笔记 + inbox + 项目状态重新汇总上周复盘，幂等写入 reviews/weekly/。"""
    settings = load_settings()
    paths = settings.work_paths()
    tz = ZoneInfo(settings.timezone)
    if date_opt:
        try:
            today = datetime.strptime(date_opt, "%Y-%m-%d").date()
        except ValueError as exc:
            typer.echo("日期格式应为 YYYY-MM-DD")
            raise typer.Exit(code=2) from exc
    else:
        today = datetime.now(tz).date()

    try:
        pending = build_status(paths.vault_dir, config_file=default_config_file()).backlog.count
    except (OSError, ValueError):
        pending = 0

    # 无人值守可见性：真实运行（非 --dry-run）在 CLI 边界记一条心跳，崩溃也记。
    try:
        result = generate_weekly(
            paths.work_root,
            paths.vault_dir,
            today=today,
            pending_review_count=pending,
            write=not dry_run,
        )
    except Exception as exc:
        if not dry_run:
            record_run_safely(
                paths.vault_dir,
                job="weekly",
                status=RunStatus.FAILED,
                day=today.isoformat(),
                detail=f"{type(exc).__name__}: {exc}",
            )
        raise

    if not dry_run:
        record_run_safely(
            paths.vault_dir, job="weekly", status=RunStatus.SUCCESS, day=today.isoformat()
        )

    publish_status: str | None = None
    if commit and not dry_run and result.note_path:
        publish_status = publish_brief(
            paths.vault_dir,
            [result.note_path],
            message=f"chore(weekly): 周复盘 {result.review.week}",
            push=push,
        ).status.value

    if as_json:
        typer.echo(
            json.dumps(
                {
                    "week": result.review.week,
                    "range": f"{result.review.start}~{result.review.end}",
                    **{k: v for k, v in result.review.as_snapshot().items() if k != "week"},
                    "note_path": str(result.note_path) if result.note_path else None,
                    "publish": publish_status,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    typer.echo(result.markdown)
    typer.echo("")
    if result.note_path:
        typer.echo(f"✓ 已写入 {result.note_path}")
    else:
        typer.echo("（--dry-run：未写入任何文件）")
    if publish_status:
        typer.echo(f"git：{publish_status}")
