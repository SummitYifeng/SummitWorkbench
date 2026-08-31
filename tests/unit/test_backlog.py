"""M1-5 / L44：待确认积压阈值与「只在跨越阈值或升级时通知」。"""

from __future__ import annotations

from summit_workbench.domain.backlog import BacklogState, should_notify_backlog


def test_below_thresholds_is_inactive():
    state = BacklogState(count=4, oldest_age_days=2)
    assert state.severity == 0
    assert state.active is False


def test_count_threshold_triggers():
    state = BacklogState(count=5, oldest_age_days=1)
    assert state.count_triggered is True
    assert state.age_triggered is False
    assert state.severity == 1


def test_age_threshold_triggers_above_three_days():
    assert BacklogState(count=2, oldest_age_days=3).age_triggered is False  # 恰好 3 天不触发
    assert BacklogState(count=2, oldest_age_days=4).age_triggered is True


def test_both_thresholds_escalate_severity():
    state = BacklogState(count=6, oldest_age_days=5)
    assert state.severity == 2
    assert "待确认 6 条" in state.reason()
    assert "最老已等待 5 天" in state.reason()


def test_notify_only_on_escalation():
    # 首次跨越阈值：通知
    assert should_notify_backlog(1, 0) is True
    # 同一严重度：不再通知（只响一次）
    assert should_notify_backlog(1, 1) is False
    # 升级：再次通知
    assert should_notify_backlog(2, 1) is True
    # 回落：不通知
    assert should_notify_backlog(1, 2) is False
    assert should_notify_backlog(0, 2) is False
