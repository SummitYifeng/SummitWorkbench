"""M1-5：月度软预算规则——只告警、不阻断。"""

from __future__ import annotations

from summit_workbench.domain.budget import evaluate_budget


def test_over_soft_limit_flags_alert():
    ev = evaluate_budget(25.0, 20.0, "CNY")
    assert ev.configured is True
    assert ev.over_soft_limit is True
    assert ev.ratio == 1.25


def test_within_limit_no_alert():
    ev = evaluate_budget(10.0, 20.0, "CNY")
    assert ev.over_soft_limit is False
    assert ev.ratio == 0.5


def test_unconfigured_never_alerts():
    ev = evaluate_budget(9999.0, None, "CNY")
    assert ev.configured is False
    assert ev.over_soft_limit is False
    assert ev.ratio is None


def test_zero_or_negative_limit_is_unconfigured():
    assert evaluate_budget(5.0, 0.0, "CNY").over_soft_limit is False
