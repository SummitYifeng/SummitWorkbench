"""``wb brief``：手动生成晨间简报（M2-8）。

采集飞书日历/任务 + 本地项目状态 → 模型排序（失败走确定性回退）→ 渲染写入当日笔记。
飞书或模型不可用时**降级**而非失败。输入装配与运行复用 :mod:`workflows.brief.runner`。
"""

from __future__ import annotations

import json

import typer

from summit_workbench.config.settings import load_settings
from summit_workbench.workflows.brief.publish import PublishResult, publish_brief
from summit_workbench.workflows.brief.runner import run_brief, today_iso


def brief_command(
    date: str | None = typer.Option(None, "--date", help="指定日期 YYYY-MM-DD（默认今天）。"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="只渲染打印，不写笔记/快照、不发通知。"
    ),
    commit: bool = typer.Option(
        False, "--commit", help="把当日笔记+快照提交到 vault（只暂存简报文件，供 launchd）。"
    ),
    push: bool = typer.Option(
        False, "--push", help="提交后推送到远端（需 --commit；落后 upstream 时不推）。"
    ),
    as_json: bool = typer.Option(False, "--json", help="以 JSON 输出结构化结果（便于脚本）。"),
) -> None:
    """生成今日晨间简报并幂等写入 ``_vault/daily/YYYY-MM-DD.md``。"""
    settings = load_settings()
    paths = settings.work_paths()
    day = date or today_iso(settings.timezone)

    run = run_brief(
        work_root=paths.work_root,
        vault_dir=paths.vault_dir,
        timezone=settings.timezone,
        day=day,
        write=not dry_run,
        notify=not dry_run,
    )
    result = run.result

    published: PublishResult | None = None
    if commit and not dry_run and result.note_path and result.snapshot_path:
        published = publish_brief(
            paths.vault_dir,
            [result.note_path, result.snapshot_path],
            message=f"chore(brief): 晨间简报 {day}",
            push=push,
        )

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
                    "publish": published.status.value if published else None,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    typer.echo(result.markdown)
    typer.echo("")
    if run.feishu_unavailable:
        typer.echo(f"ℹ 飞书事实源不可用，已降级：{run.feishu_unavailable}")
    if result.note_path:
        typer.echo(f"✓ 已写入 {result.note_path}")
        typer.echo(f"✓ 快照 {result.snapshot_path}")
    else:
        typer.echo("（--dry-run：未写入任何文件）")
    if published is not None:
        mark = "✓" if published.status.value.startswith("committed") else "ℹ"
        detail = f"（{published.detail}）" if published.detail else ""
        typer.echo(f"{mark} git：{published.status.value}{detail}")
