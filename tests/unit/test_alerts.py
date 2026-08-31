"""M1-5 / L44：预算与积压通知去重——只在跨越阈值或升级时通知一次。"""

from __future__ import annotations

from summit_workbench.domain.backlog import BacklogState
from summit_workbench.domain.budget import evaluate_budget
from summit_workbench.observability.alerts import check_and_update, evaluate_notifications
from summit_workbench.observability.status import StatusReport
from summit_workbench.repositories.notify_state import NotifyState, load_notify_state
from summit_workbench.repositories.usage_ledger import UsageTotals


def _report(*, month="2026-08", spent=25.0, limit=20.0, count=5, oldest=10) -> StatusReport:
    return StatusReport(
        month=month,
        total_meetings=1,
        state_counts={},
        usage=UsageTotals(1, 1000, 500, spent, "CNY"),
        budget=evaluate_budget(spent, limit, "CNY"),
        backlog=BacklogState(count=count, oldest_age_days=oldest),
    )


def test_first_crossing_notifies_both_then_silent():
    report = _report()
    notes, state = evaluate_notifications(report, NotifyState())
    kinds = {n.kind for n in notes}
    assert kinds == {"budget", "backlog"}
    assert state.budget_notified is True
    assert state.backlog_severity == 2
    # 同状态再评估：零新通知（只响一次）
    again, _ = evaluate_notifications(report, state)
    assert again == []


def test_backlog_escalation_renotifies():
    low = _report(count=5, oldest=1, spent=10.0)  # backlog severity 1, 预算内
    notes, state = evaluate_notifications(low, NotifyState(month="2026-08"))
    assert [n.kind for n in notes] == ["backlog"]
    assert state.backlog_severity == 1
    high = _report(count=6, oldest=10, spent=10.0)  # backlog severity 2, 预算内
    notes2, state2 = evaluate_notifications(high, state)
    assert [n.kind for n in notes2] == ["backlog"]
    assert state2.backlog_severity == 2


def test_backlog_deescalation_records_lower_and_allows_future_renotify():
    high = _report(count=6, oldest=10)
    _, state = evaluate_notifications(high, NotifyState(month="2026-08", budget_notified=True))
    cleared = _report(count=0, oldest=None, limit=None, spent=0.0)
    notes, state2 = evaluate_notifications(cleared, state)
    assert notes == []
    assert state2.backlog_severity == 0
    # 日后再次跨越阈值应重新通知
    notes3, _ = evaluate_notifications(high, state2)
    assert [n.kind for n in notes3] == ["backlog"]


def test_budget_resets_across_month():
    aug = _report(month="2026-08")
    _, state = evaluate_notifications(aug, NotifyState())
    assert state.budget_notified is True
    sep = _report(month="2026-09")
    notes, _ = evaluate_notifications(sep, state)
    assert any(n.kind == "budget" for n in notes)


def test_check_and_update_persists_state(tmp_path):
    vault = tmp_path / "vault"
    report = _report()
    first = check_and_update(vault, report)
    assert len(first) == 2
    # 状态已落盘，再次调用零新通知
    second = check_and_update(vault, report)
    assert second == []
    assert load_notify_state(vault).backlog_severity == 2
