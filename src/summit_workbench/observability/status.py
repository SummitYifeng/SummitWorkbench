"""``wb status`` 聚合：会议处理进度、当月用量、软预算与待确认积压（PRD M1-5）。

只读账本与审批页并汇总；是否发通知交给 :mod:`summit_workbench.observability.alerts`。
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from summit_workbench.domain.backlog import BacklogState
from summit_workbench.domain.budget import BudgetEvaluation, evaluate_budget
from summit_workbench.domain.pipeline import ProcessingState
from summit_workbench.domain.review import CandidateDecision
from summit_workbench.repositories.meeting_state import all_latest
from summit_workbench.repositories.review_page import parse_review_page, review_path
from summit_workbench.repositories.usage_ledger import UsageTotals, monthly_totals


def load_budget_settings(config_file: Path) -> tuple[float | None, str]:
    """从 ``[budget]`` 读取月度软上限与币种；缺失则 (None, "CNY")。"""
    if not config_file.is_file():
        return None, "CNY"
    with config_file.open("rb") as fh:
        data = tomllib.load(fh)
    budget = data.get("budget")
    if not isinstance(budget, dict):
        return None, "CNY"
    raw = budget.get("monthly_soft_limit")
    limit = float(raw) if isinstance(raw, int | float) and not isinstance(raw, bool) else None
    currency = str(budget.get("currency", "CNY"))
    return limit, currency


def _state_counts(vault_dir: Path) -> dict[str, int]:
    counts = {state.value: 0 for state in ProcessingState}
    for task in all_latest(vault_dir).values():
        counts[task.state.value] += 1
    return counts


def _backlog(vault_dir: Path, today: date) -> BacklogState:
    """从审批页统计未确认（``- [ ]``）候选条数与最老条目的等待天数。"""
    page = review_path(vault_dir)
    if not page.is_file():
        return BacklogState(count=0, oldest_age_days=None)
    parsed = parse_review_page(page.read_text(encoding="utf-8"))
    pending = [
        entry
        for entry in parsed.entries
        if entry.candidate.decision is CandidateDecision.PENDING
    ]
    if not pending:
        return BacklogState(count=0, oldest_age_days=None)
    oldest_age: int | None = None
    for entry in pending:
        try:
            meeting_day = date.fromisoformat(entry.meeting_date)
        except ValueError:
            continue
        age = (today - meeting_day).days
        oldest_age = age if oldest_age is None else max(oldest_age, age)
    return BacklogState(count=len(pending), oldest_age_days=oldest_age)


@dataclass(frozen=True)
class StatusReport:
    month: str
    total_meetings: int
    state_counts: dict[str, int]
    usage: UsageTotals
    budget: BudgetEvaluation
    backlog: BacklogState

    def count(self, state: ProcessingState) -> int:
        return self.state_counts.get(state.value, 0)

    @property
    def succeeded(self) -> int:
        """已成功进入第二大脑：结构化完成或已应用/忽略的会议。"""
        return (
            self.count(ProcessingState.PROCESSED)
            + self.count(ProcessingState.PENDING_REVIEW)
            + self.count(ProcessingState.APPLIED)
            + self.count(ProcessingState.IGNORED)
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "month": self.month,
            "total_meetings": self.total_meetings,
            "state_counts": dict(self.state_counts),
            "succeeded": self.succeeded,
            "unavailable": self.count(ProcessingState.UNAVAILABLE),
            "failed": self.count(ProcessingState.FAILED),
            "pending_review": self.backlog.count,
            "usage": {
                "calls": self.usage.calls,
                "input_tokens": self.usage.input_tokens,
                "output_tokens": self.usage.output_tokens,
                "estimated_cost": self.usage.estimated_cost,
                "currency": self.usage.currency,
            },
            "budget": {
                "spent": self.budget.spent,
                "soft_limit": self.budget.soft_limit,
                "currency": self.budget.currency,
                "over_soft_limit": self.budget.over_soft_limit,
                "ratio": self.budget.ratio,
            },
            "backlog": {
                "count": self.backlog.count,
                "oldest_age_days": self.backlog.oldest_age_days,
                "severity": self.backlog.severity,
                "active": self.backlog.active,
            },
        }


def build_status(
    vault_dir: Path,
    *,
    config_file: Path,
    now: datetime | None = None,
) -> StatusReport:
    """聚合当前进度、当月用量与预算/积压评估。"""
    moment = now or datetime.now(UTC)
    month = moment.strftime("%Y-%m")
    counts = _state_counts(vault_dir)
    total = sum(counts.values())
    usage = monthly_totals(vault_dir, month)
    soft_limit, budget_currency = load_budget_settings(config_file)
    budget = evaluate_budget(
        usage.estimated_cost, soft_limit, budget_currency or usage.currency
    )
    backlog = _backlog(vault_dir, moment.date())
    return StatusReport(
        month=month,
        total_meetings=total,
        state_counts=counts,
        usage=usage,
        budget=budget,
        backlog=backlog,
    )
