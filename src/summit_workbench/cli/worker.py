"""不启动 Web server 的一次性自动化 worker 入口（P1-01）。"""

from __future__ import annotations

import json
import os

import typer

from summit_workbench.config.profiles import resolve_active_workspace
from summit_workbench.domain.automation import AutomationJob
from summit_workbench.webapp.build_info import mode_from_environment
from summit_workbench.workflows.automation_worker import run_automation_job


def worker_command(
    job: AutomationJob = typer.Option(..., "--job", help="brief、weekly 或 meeting-sync。"),
    workspace_id: str | None = typer.Option(None, "--workspace-id", help="校验目标 workspace。"),
    as_json: bool = typer.Option(False, "--json", help="输出 JSON 结果。"),
) -> None:
    """执行一次已启用的自动化任务；不启动 Web server。"""
    context = resolve_active_workspace(
        allow_env_fallback=mode_from_environment(os.environ.get("WB_PANEL_MODE")) != "production"
    )
    result: dict[str, str | None]
    if workspace_id and workspace_id != context.workspace_id:
        result = {"job": job.value, "status": "failed", "detail": "workspace_id 不匹配"}
    else:
        result = run_automation_job(context, job).as_dict()
    if as_json:
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        detail = f" — {result['detail']}" if result["detail"] else ""
        typer.echo(f"{result['job']}：{result['status']}" + detail)
