"""``wb status``：会议处理进度、当月用量、软预算与待确认积压告警（M1-5）。"""

from __future__ import annotations

import json
import os

import typer

from summit_workbench.config.profiles import resolve_active_workspace
from summit_workbench.config.settings import default_config_file
from summit_workbench.domain.pipeline import ProcessingState
from summit_workbench.domain.run_health import RunStatus
from summit_workbench.observability.alerts import Notification, check_and_update
from summit_workbench.observability.status import StatusReport, build_status
from summit_workbench.webapp.build_info import mode_from_environment

# 定时任务的面向用户标签。
_JOB_LABELS: dict[str, str] = {"brief": "晨间简报", "weekly": "周复盘"}

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
    context = resolve_active_workspace(
        allow_env_fallback=mode_from_environment(os.environ.get("WB_PANEL_MODE")) != "production"
    )
    if context.paths is None:
        if as_json:
            typer.echo(
                json.dumps(
                    {
                        "ok": True,
                        "state": "onboarding-required",
                        "message": "尚未选择工作区，请先完成 onboarding",
                        "notifications": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            typer.echo("工作区：尚未选择，请先在 SummitWorkbench 中完成 onboarding。")
        return
    vault_dir = context.paths.vault_dir
    report = build_status(vault_dir, config_file=context.config_file or default_config_file())
    notifications = check_and_update(vault_dir, report) if notify else []
    if notify:
        _deliver_notifications(notifications)

    if as_json:
        payload = report.as_dict()
        payload["notifications"] = [{"kind": n.kind, "message": n.message} for n in notifications]
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    _print_human(report, notifications)


# 通知副标题（macOS 通知中心的分组标题）。
_KIND_SUBTITLE: dict[str, str] = {
    "budget": "费用提醒",
    "backlog": "待确认积压",
    "run": "定时任务告警",
}


def _deliver_notifications(notifications: list[Notification]) -> None:
    """把评估出的新通知发到 macOS 通知中心；环境不支持时安全空转（不中断 CLI）。"""
    from summit_workbench.observability.notifier import send_notification

    for note in notifications:
        send_notification(
            "SummitWorkbench",
            note.message,
            subtitle=_KIND_SUBTITLE.get(note.kind, "工作台提醒"),
        )


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

    _print_runs(report)

    auth = report.feishu_auth
    if auth.needs_reauthorize:
        typer.echo("")
        since = f"（自 {auth.since_day}）" if auth.since_day else ""
        typer.echo(f"⚠ 飞书授权已失效{since}：简报的飞书事实源已降级。")
        typer.echo("  → 请运行 wb feishu authorize-url 重新授权，再 wb feishu login")

    if notifications:
        typer.echo("")
        typer.echo("本次新通知：")
        for note in notifications:
            typer.echo(f"  • [{note.kind}] {note.message}")


def _print_runs(report: StatusReport) -> None:
    """定时任务健康度：上次何时跑、成没跑出、是否连续失败（无人值守可见性）。"""
    if not report.runs:
        return
    typer.echo("")
    typer.echo("定时任务健康度：")
    for job, health in report.runs.items():
        label = _JOB_LABELS.get(job, job)
        if not health.ever_ran:
            typer.echo(f"  {label:<5} 尚未运行")
            continue
        if health.last_status is RunStatus.SUCCESS:
            icon, tail = "✅", ""
        elif health.last_status is RunStatus.DEGRADED:
            icon, tail = "⚠️", "（降级：事实源/排序回退）"
        else:
            icon, tail = "❌", f"（连续失败 {health.consecutive_failures} 次）"
        typer.echo(f"  {label:<5} {icon} 最近 {health.last_day}{tail}")
