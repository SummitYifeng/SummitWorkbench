"""``wb brief``：手动生成晨间简报（M2-8）。

采集飞书日历/任务 + 本地项目状态 → 模型排序（失败走确定性回退）→ 渲染写入本机程序目录。
飞书或模型不可用时**降级**而非失败。输入装配与运行复用 :mod:`workflows.brief.runner`。

简报**不在知识库内**（契约 §1/§3，2026-09-19 起落 ``profile_dir(workspace_id)/briefs/``），
因此 ``--commit`` / ``--push`` 是**显式无操作**（保留参数只为兼容既有 launchd 装机配置）。
"""

from __future__ import annotations

import json
import os

import typer

from summit_workbench.config.profiles import resolve_active_workspace
from summit_workbench.domain.run_health import RunStatus
from summit_workbench.observability.heartbeat import record_run_safely
from summit_workbench.webapp.build_info import mode_from_environment
from summit_workbench.workflows.brief.runner import run_brief, today_iso

_NOT_IN_VAULT = "skipped(not-in-vault)"


def brief_command(
    date: str | None = typer.Option(None, "--date", help="指定日期 YYYY-MM-DD（默认今天）。"),
    dry_run: bool = typer.Option(False, "--dry-run", help="只渲染打印，不写文件、不发通知。"),
    commit: bool = typer.Option(
        False, "--commit", help="【已无操作】简报不在知识库内，无需提交（保留兼容）。"
    ),
    push: bool = typer.Option(
        False, "--push", help="【已无操作】简报不在知识库内，无需推送（保留兼容）。"
    ),
    as_json: bool = typer.Option(False, "--json", help="以 JSON 输出结构化结果（便于脚本）。"),
) -> None:
    """生成今日晨间简报并幂等写入本机程序目录（不再写 ``_vault/daily/``）。"""
    context = resolve_active_workspace(
        allow_env_fallback=mode_from_environment(os.environ.get("WB_PANEL_MODE")) != "production"
    )
    if context.paths is None:
        typer.echo("✗ 尚未选择工作区，请先在 SummitWorkbench 中完成 onboarding")
        raise typer.Exit(code=2)
    paths = context.paths
    day = date or today_iso(context.timezone)

    # 无人值守可见性：真实运行（非 --dry-run）在 CLI 边界记一条心跳，崩溃也记。
    try:
        run = run_brief(
            work_root=paths.work_root,
            vault_dir=paths.vault_dir,
            timezone=context.timezone,
            day=day,
            write=not dry_run,
            notify=not dry_run,
            config_file=context.config_file,
            workspace_id=context.workspace_id,
            home=context.home,
        )
    except Exception as exc:
        if not dry_run:
            record_run_safely(
                paths.vault_dir,
                job="brief",
                status=RunStatus.FAILED,
                day=day,
                detail=f"{type(exc).__name__}: {exc}",
            )
        raise
    result = run.result

    if not dry_run:
        degraded = bool(run.feishu_unavailable) or result.ranking.degraded
        record_run_safely(
            paths.vault_dir,
            job="brief",
            status=RunStatus.DEGRADED if degraded else RunStatus.SUCCESS,
            day=day,
            detail=run.feishu_unavailable,
        )

    # 简报不在知识库内 → 没有任何库内产物需要提交；--commit/--push 显式无操作。
    publish_note: str | None = None
    if commit or push:
        publish_note = _NOT_IN_VAULT

    if as_json:
        typer.echo(
            json.dumps(
                {
                    "date": day,
                    "health": result.brief.health.level,
                    "actions": len(result.brief.actions),
                    "meetings": len(result.brief.meetings),
                    "tasks": len(result.brief.tasks),
                    "ranking_degraded": result.ranking.degraded,
                    "note_path": str(result.note_path) if result.note_path else None,
                    "snapshot_path": str(result.snapshot_path) if result.snapshot_path else None,
                    "feishu_unavailable": run.feishu_unavailable,
                    "feishu_needs_reauthorize": run.feishu_needs_reauthorize,
                    "publish": publish_note,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    typer.echo(result.markdown)
    typer.echo("")
    if run.feishu_needs_reauthorize:
        typer.echo(f"⚠ 飞书授权已失效，简报已降级：{run.feishu_unavailable}")
        typer.echo("  → 请运行 wb feishu authorize-url 重新授权，再 wb feishu login")
    elif run.feishu_unavailable:
        typer.echo(f"ℹ 飞书事实源不可用，已降级：{run.feishu_unavailable}")
    if result.note_path:
        typer.echo(f"✓ 已写入 {result.note_path}")
        typer.echo(f"✓ 快照 {result.snapshot_path}")
    else:
        typer.echo("（--dry-run：未写入任何文件）")
    if publish_note is not None:
        typer.echo("ℹ 简报已不在知识库内，无需提交")
