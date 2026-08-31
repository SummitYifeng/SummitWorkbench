"""月度软预算规则（PRD M1-5）：只告警、不阻断。

纯规则，不读文件、不发通知。费用与软上限比较，判定是否越过软预算。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BudgetEvaluation:
    """当月费用相对软预算的评估结果。"""

    spent: float
    soft_limit: float | None  # None 表示未配置软预算 → 永不告警
    currency: str

    @property
    def configured(self) -> bool:
        return self.soft_limit is not None and self.soft_limit > 0

    @property
    def over_soft_limit(self) -> bool:
        """越过软预算即告警；软预算只提示，绝不阻断新会议处理。"""
        return self.configured and self.spent > float(self.soft_limit or 0.0)

    @property
    def ratio(self) -> float | None:
        """已用/软上限；未配置时为 None。"""
        if not self.configured:
            return None
        return round(self.spent / float(self.soft_limit or 1.0), 4)


def evaluate_budget(spent: float, soft_limit: float | None, currency: str) -> BudgetEvaluation:
    return BudgetEvaluation(spent=round(spent, 6), soft_limit=soft_limit, currency=currency)
