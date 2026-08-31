"""软预算与积压告警评估（PRD M1-5 / L44）：只在跨越阈值或升级时通知一次。

纯评估 :func:`evaluate_notifications` 不写盘；:func:`check_and_update` 负责读写去重状态。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from summit_workbench.domain.backlog import should_notify_backlog
from summit_workbench.observability.status import StatusReport
from summit_workbench.repositories.notify_state import (
    NotifyState,
    load_notify_state,
    save_notify_state,
)


@dataclass(frozen=True)
class Notification:
    kind: str  # "budget" | "backlog"
    message: str


def evaluate_notifications(
    report: StatusReport, state: NotifyState
) -> tuple[list[Notification], NotifyState]:
    """比对当前状态与已通知状态，返回需新发的通知与更新后的去重状态。"""
    notifications: list[Notification] = []

    # 预算按月去重：跨月即重置「本月是否已就预算告警」。
    budget_notified = state.budget_notified if state.month == report.month else False
    if report.budget.over_soft_limit and not budget_notified:
        notifications.append(
            Notification(
                "budget",
                f"当月模型费用 {report.budget.spent} {report.budget.currency} "
                f"已超过软预算 {report.budget.soft_limit} {report.budget.currency}"
                "（仅提示，不阻断新会议）。",
            )
        )
        budget_notified = True

    # 积压仅在严重度升高时通知；严重度回落也写回状态，日后再次跨阈值可重新通知。
    current_severity = report.backlog.severity
    if should_notify_backlog(current_severity, state.backlog_severity):
        notifications.append(
            Notification("backlog", f"待确认积压需要处理：{report.backlog.reason()}。")
        )

    new_state = NotifyState(
        month=report.month,
        budget_notified=budget_notified,
        backlog_severity=current_severity,
    )
    return notifications, new_state


def check_and_update(vault_dir: Path, report: StatusReport) -> list[Notification]:
    """评估并持久化去重状态，返回本次需要发出的新通知。"""
    state = load_notify_state(vault_dir)
    notifications, new_state = evaluate_notifications(report, state)
    save_notify_state(vault_dir, new_state)
    return notifications
