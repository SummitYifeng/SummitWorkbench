"""M1-5：wb status 聚合、软预算读取与积压统计。"""

from __future__ import annotations

from datetime import UTC, datetime

from summit_workbench.domain.pipeline import MeetingTask, ProcessingState
from summit_workbench.domain.review import (
    ApprovalCandidate,
    CandidateDecision,
    CandidateKind,
    EvidenceRef,
    ReviewEntry,
    RouteTarget,
)
from summit_workbench.observability.status import build_status, load_budget_settings
from summit_workbench.providers.llm.usage import UsageRecord
from summit_workbench.repositories.meeting_state import record_task
from summit_workbench.repositories.review_page import refresh_review_page
from summit_workbench.repositories.usage_ledger import append_usage

NOW = datetime(2026, 8, 31, 12, tzinfo=UTC)


def _record_state(vault, key: str, state: ProcessingState) -> None:
    meeting_id, note_id = key.split(":", 1)
    task = MeetingTask.for_remote(meeting_id, note_id, state=state)
    record_task(vault, task, now=NOW)


def _usage(vault, cost: float, ts: str = "2026-08-15T09:00:00+00:00") -> None:
    append_usage(
        vault,
        UsageRecord(
            timestamp=ts,
            capability="meeting",
            model_id="m",
            input_tokens=1000,
            output_tokens=500,
            attempts=1,
            task_key="m:n",
            estimated_cost=cost,
            currency="CNY",
            price_input_per_mtok=0.0,
            price_output_per_mtok=0.0,
        ),
    )


def _pending_entry(stable_id: str, meeting_date: str) -> ReviewEntry:
    candidate = ApprovalCandidate(
        candidate_id=stable_id,
        kind=CandidateKind.ACTION_ITEM,
        description=f"desc-{stable_id}",
        target_project="P1",
        route=RouteTarget.PROJECT_MAIN,
        evidence=EvidenceRef(anchor="张三 00:03"),
        is_next_step=True,
        decision=CandidateDecision.PENDING,
    )
    return ReviewEntry(candidate, f"o-{stable_id}", meeting_date, "会", "[[n]]", "[[t]]")


def _budget_config(tmp_path, limit: float | None = 20.0):
    path = tmp_path / "config.toml"
    body = "[budget]\ncurrency = \"CNY\"\n"
    if limit is not None:
        body += f"monthly_soft_limit = {limit}\n"
    path.write_text(body, encoding="utf-8")
    return path


def test_load_budget_settings_missing_file_or_table(tmp_path):
    assert load_budget_settings(tmp_path / "nope.toml") == (None, "CNY")
    empty = tmp_path / "empty.toml"
    empty.write_text("timezone = \"Asia/Shanghai\"\n", encoding="utf-8")
    assert load_budget_settings(empty) == (None, "CNY")


def test_build_status_aggregates_states_usage_budget_backlog(tmp_path):
    vault = tmp_path / "vault"
    _record_state(vault, "m1:n1", ProcessingState.PENDING_REVIEW)
    _record_state(vault, "m2:n2", ProcessingState.UNAVAILABLE)
    _record_state(vault, "m3:n3", ProcessingState.FAILED)
    _record_state(vault, "m4:n4", ProcessingState.APPLIED)
    _usage(vault, 25.0)  # 超过软预算 20
    refresh_review_page(
        vault,
        [_pending_entry("a", "2026-08-30"), _pending_entry("b", "2026-08-20")],
    )

    report = build_status(vault, config_file=_budget_config(tmp_path), now=NOW)

    assert report.total_meetings == 4
    assert report.count(ProcessingState.UNAVAILABLE) == 1
    assert report.count(ProcessingState.FAILED) == 1
    assert report.succeeded == 2  # pending-review + applied
    assert report.usage.estimated_cost == 25.0
    assert report.budget.over_soft_limit is True
    # 最老一条 2026-08-20，距 08-31 为 11 天 > 3
    assert report.backlog.count == 2
    assert report.backlog.oldest_age_days == 11
    assert report.backlog.age_triggered is True


def test_build_status_without_budget_or_backlog(tmp_path):
    vault = tmp_path / "vault"
    _record_state(vault, "m1:n1", ProcessingState.PROCESSED)
    report = build_status(vault, config_file=_budget_config(tmp_path, limit=None), now=NOW)
    assert report.budget.configured is False
    assert report.budget.over_soft_limit is False
    assert report.backlog.count == 0
    assert report.backlog.oldest_age_days is None
    assert report.as_dict()["pending_review"] == 0
