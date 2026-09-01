"""通知去重状态：记住上次已通知的预算/积压等级，避免重复打扰（PRD L44）。

落盘 ``_vault/_signals/notifications/state.json``。只读写状态，是否发通知由 observability
的纯规则决定。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from summit_workbench.repositories._atomic import atomic_write_text

NOTIFY_STATE_SUBDIR = ("_signals", "notifications")
_STATE_NAME = "state.json"


@dataclass(frozen=True)
class NotifyState:
    """上次通知时的月份、是否已就预算告警、积压严重度、以及各定时任务已告警的连续失败数。"""

    month: str = ""
    budget_notified: bool = False
    backlog_severity: int = 0
    # 每个定时任务「上次已就连续失败告警到的失败次数」，用于去重：失败连击继续增长才再告警，
    # 一旦成功清零则未来新连击可重新告警。
    run_failures_alerted: dict[str, int] = field(default_factory=dict)


def _state_path(vault_dir: Path) -> Path:
    return vault_dir.joinpath(*NOTIFY_STATE_SUBDIR, _STATE_NAME)


def load_notify_state(vault_dir: Path) -> NotifyState:
    path = _state_path(vault_dir)
    if not path.is_file():
        return NotifyState()
    try:
        row = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return NotifyState()
    if not isinstance(row, dict):
        return NotifyState()
    raw_failures = row.get("run_failures_alerted", {})
    failures = (
        {str(k): int(v) for k, v in raw_failures.items()} if isinstance(raw_failures, dict) else {}
    )
    return NotifyState(
        month=str(row.get("month", "")),
        budget_notified=bool(row.get("budget_notified", False)),
        backlog_severity=int(row.get("backlog_severity", 0)),
        run_failures_alerted=failures,
    )


def save_notify_state(vault_dir: Path, state: NotifyState) -> Path:
    path = _state_path(vault_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "month": state.month,
        "budget_notified": state.budget_notified,
        "backlog_severity": state.backlog_severity,
        "run_failures_alerted": dict(state.run_failures_alerted),
    }
    atomic_write_text(path, json.dumps(row, ensure_ascii=False, indent=2))
    return path
