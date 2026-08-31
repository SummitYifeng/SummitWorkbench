"""``wb status``：会议处理进度、当月用量、软预算与待确认积压告警（M1-5）。"""

from __future__ import annotations

import json

import typer

from summit_workbench.config.settings import default_config_file, load_settings
from summit_workbench.domain.pipeline import ProcessingState
from summit_workbench.observability.alerts import Notification, check_and_update
from summit_workbench.observability.status import StatusReport, build_status

# 面向用户的状态标签（保持稳定，脚本可读性用 --json）。
_STATE_LABELS: list[tuple[ProcessingState, str]] = [
    (ProcessingState.DISCOVERED, "已发现"),
    (ProcessingState.FETCHED, "已取稿"),
    (ProcessingState.ARCHIVED, "已归档"),
    (ProcessingState.PROCESSED, "已结构化"),
    (ProcessingState.PENDING_REVIEW, "待确认会议"),
    (ProcessingState.APPLIED, "已应用"),
    (ProcessingState.IGNORED, "已忽略"),
    (ProcessingState.UNAVAILABLE, "不可用"),
    (ProcessingState.FAILED, "失败"),
]


def status_command(
    as_json: bool = typer.Option(False, "--json", help="以 JSON 输出，便于脚本消费。"),
    notify: bool = typer.Option(
        False,
        "--notify",
        help="评估软预算/积压阈值并按去重规则发出新通知（供 launchd 定时调用）。",
    ),
) -> None:
    """汇总发现/成功/不可用/失败/待确认、当月 token 与估算费用；可选发出阈值通知。"""
    settings = load_settings()
    vault_dir = settings.work_paths().vault_dir
    report = build_status(vault_dir, config_file=default_config_file())
    notifications = check_and_update(vault_dir, report) if notify else []

    if as_json:
        payload = report.as_dict()
        payload["notifications"] = [{"kind": n.kind, "message": n.message} for n in notifications]
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    _print_human(report, notifications)


def _print_human(report: StatusReport, notifications: list[Notification]) -> None:
    typer.echo(f"会议处理进度（共 {report.total_meetings} 场，本月 {report.month}）")
    for state, label in _STATE_LABELS:
        typer.echo(f"  {label:<5} {report.count(state)}")

    usage = report.usage
    typer.echo("")
    typer.echo(
        f"当月用量：{usage.calls} 次调用，输入 {usage.input_tokens} / "
        f"输出 {usage.output_tokens} token，估算 {usage.estimated_cost} {usage.currency}"
    )

    budget = report.budget
    if not budget.configured:
        typer.echo("软预算：未配置（在 config.toml 的 [budget] 设 monthly_soft_limit 以启用告警）")
    else:
        ratio = f"{budget.ratio:.0%}" if budget.ratio is not None else "—"
        flag = "⚠ 已超软预算（仅提示，不阻断）" if budget.over_soft_limit else "在预算内"
        typer.echo(
            f"软预算：{budget.spent}/{budget.soft_limit} {budget.currency}（{ratio}）— {flag}"
        )

    backlog = report.backlog
    oldest = "—" if backlog.oldest_age_days is None else f"{backlog.oldest_age_days} 天"
    tag = "⚠ 需处理" if backlog.active else "正常"
    typer.echo(f"待确认候选积压：{backlog.count} 条候选，最老 {oldest} — {tag}")

    if notifications:
        typer.echo("")
        typer.echo("本次新通知：")
        for note in notifications:
            typer.echo(f"  • [{note.kind}] {note.message}")
