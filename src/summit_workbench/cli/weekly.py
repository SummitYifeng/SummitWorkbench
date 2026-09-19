"""``wb weekly``：生成上一自然周的跨项目周复盘（M2-10）。

周复盘**不在知识库内**（契约 §1/§3，2026-09-19 起落 ``profile_dir(workspace_id)/weekly/``），
因此 ``--commit`` / ``--push`` 是**显式无操作**（保留参数只为兼容既有 launchd 装机配置）。

workspace 身份与 ``wb brief`` 走**同一个解析入口**（``resolve_active_workspace``）：
CLI 与 Web 面板由此指向同一个 ``profile_dir(<同一 workspace_id>)``，不会读写分裂。
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import typer

from summit_workbench.config.profiles import resolve_active_workspace
from summit_workbench.config.settings import default_config_file
from summit_workbench.domain.run_health import RunStatus
from summit_workbench.observability.heartbeat import record_run_safely
from summit_workbench.observability.status import build_status
from summit_workbench.webapp.build_info import mode_from_environment
from summit_workbench.workflows.weekly.weekly import generate_weekly

_NOT_IN_VAULT = "skipped(not-in-vault)"


def weekly_command(
    date_opt: str | None = typer.Option(
        None, "--date", help="参考日期 YYYY-MM-DD（默认今天）；复盘其上一自然周。"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="只渲染打印，不写文件。"),
    commit: bool = typer.Option(
        False, "--commit", help="【已无操作】周复盘不在知识库内，无需提交（保留兼容）。"
    ),
    push: bool = typer.Option(
        False, "--push", help="【已无操作】周复盘不在知识库内，无需推送（保留兼容）。"
    ),
    as_json: bool = typer.Option(False, "--json", help="以 JSON 输出结构化结果。"),
) -> None:
    """从 git + 会议笔记 + inbox + 项目状态重新汇总上周复盘，幂等写入本机程序目录。"""
    context = resolve_active_workspace(
        allow_env_fallback=mode_from_environment(os.environ.get("WB_PANEL_MODE")) != "production"
    )
    if context.paths is None:
        typer.echo("✗ 尚未选择工作区，请先在 SummitWorkbench 中完成 onboarding")
        raise typer.Exit(code=2)
    paths = context.paths
    tz = ZoneInfo(context.timezone)
    if date_opt:
        try:
            today = datetime.strptime(date_opt, "%Y-%m-%d").date()
        except ValueError as exc:
            typer.echo("日期格式应为 YYYY-MM-DD")
            raise typer.Exit(code=2) from exc
    else:
        today = datetime.now(tz).date()

    try:
        pending = build_status(
            paths.vault_dir, config_file=context.config_file or default_config_file()
        ).backlog.count
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
            workspace_id=context.workspace_id,
            home=context.home,
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

    # 周复盘不在知识库内 → 没有任何库内产物需要提交；--commit/--push 显式无操作。
    publish_note: str | None = _NOT_IN_VAULT if (commit or push) else None

    if as_json:
        typer.echo(
            json.dumps(
                {
                    "week": result.review.week,
                    "range": f"{result.review.start}~{result.review.end}",
                    **{k: v for k, v in result.review.as_snapshot().items() if k != "week"},
                    "note_path": str(result.note_path) if result.note_path else None,
                    "publish": publish_note,
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
    if publish_note is not None:
        typer.echo("ℹ 周复盘已不在知识库内，无需提交")
