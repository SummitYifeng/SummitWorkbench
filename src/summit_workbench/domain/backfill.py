"""历史补导的费用/预算预估规则（PRD M1-7）：开始前给出会议数、token 与费用预估，
预计跨越月度软预算时要求再次确认。纯规则，不读文件、不调用模型。
"""

from __future__ import annotations

from dataclasses import dataclass

from summit_workbench.providers.llm.config import ModelPricing


@dataclass(frozen=True)
class BackfillEstimate:
    total: int
    already_done: int
    pending: int
    est_input_tokens: int
    est_output_tokens: int
    est_cost: float
    currency: str
    month_spent: float
    soft_limit: float | None

    @property
    def projected_month_cost(self) -> float:
        return round(self.month_spent + self.est_cost, 6)

    @property
    def crosses_soft_budget(self) -> bool:
        """预计本月累计费用越过软预算 → CLI 需二次确认（软预算只提示不阻断）。"""
        if self.soft_limit is None or self.soft_limit <= 0:
            return False
        return self.projected_month_cost > self.soft_limit


def estimate_backfill(
    *,
    pending_input_tokens: list[int],
    output_tokens_per_meeting: int,
    pricing: ModelPricing,
    already_done: int,
    month_spent: float,
    soft_limit: float | None,
) -> BackfillEstimate:
    """由待处理会议的逐字稿输入 token（本地文件可精确统计）汇总预估。"""
    pending = len(pending_input_tokens)
    est_input = sum(pending_input_tokens)
    est_output = pending * output_tokens_per_meeting
    est_cost = round(pricing.estimate(est_input, est_output), 6)
    return BackfillEstimate(
        total=already_done + pending,
        already_done=already_done,
        pending=pending,
        est_input_tokens=est_input,
        est_output_tokens=est_output,
        est_cost=est_cost,
        currency=pricing.currency,
        month_spent=round(month_spent, 6),
        soft_limit=soft_limit,
    )
