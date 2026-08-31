"""M1-7：历史补导费用/预算预估规则。"""

from __future__ import annotations

from summit_workbench.domain.backfill import estimate_backfill
from summit_workbench.providers.llm.config import ModelPricing

PRICING = ModelPricing(currency="CNY", input_per_mtok=1.0, output_per_mtok=2.0)


def test_estimates_tokens_and_cost():
    est = estimate_backfill(
        pending_input_tokens=[1_000_000, 1_000_000],
        output_tokens_per_meeting=500_000,
        pricing=PRICING,
        already_done=1,
        month_spent=0.0,
        soft_limit=None,
    )
    assert est.total == 3
    assert est.pending == 2
    assert est.est_input_tokens == 2_000_000
    assert est.est_output_tokens == 1_000_000
    # 2M 输入 ×1 + 1M 输出 ×2 = 4.0
    assert est.est_cost == 4.0
    assert est.crosses_soft_budget is False  # 未配置软预算


def test_crosses_soft_budget_when_projected_exceeds():
    est = estimate_backfill(
        pending_input_tokens=[1_000_000],
        output_tokens_per_meeting=0,
        pricing=PRICING,
        already_done=0,
        month_spent=0.6,
        soft_limit=1.0,
    )
    assert est.est_cost == 1.0
    assert est.projected_month_cost == 1.6
    assert est.crosses_soft_budget is True


def test_within_budget_does_not_cross():
    est = estimate_backfill(
        pending_input_tokens=[100_000],
        output_tokens_per_meeting=0,
        pricing=PRICING,
        already_done=0,
        month_spent=0.0,
        soft_limit=1.0,
    )
    assert est.crosses_soft_budget is False
