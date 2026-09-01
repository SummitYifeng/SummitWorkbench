"""定时任务运行心跳 + 健康度推导 + 连续失败告警（正式使用前加固 #2）。"""

from __future__ import annotations

import json
import warnings

from summit_workbench.domain.backlog import BacklogState
from summit_workbench.domain.budget import evaluate_budget
from summit_workbench.domain.run_health import (
    RunEvent,
    RunStatus,
    evaluate_runs,
)
from summit_workbench.observability.alerts import evaluate_notifications
from summit_workbench.observability.status import StatusReport
from summit_workbench.repositories._jsonl import CorruptLogLine
from summit_workbench.repositories._schema import RUN_HEARTBEAT_VERSION
from summit_workbench.repositories.feishu_auth_state import FeishuAuthState
from summit_workbench.repositories.notify_state import NotifyState
from summit_workbench.repositories.run_heartbeat import (
    RunHeartbeatRow,
    _log,
    read_events,
    record_run,
)
from summit_workbench.repositories.usage_ledger import UsageTotals


def _ev(job: str, status: RunStatus, day: str) -> RunEvent:
    return RunEvent(job=job, status=status, at=f"{day}T08:00:00+00:00", day=day)


# —— 纯领域：健康度推导 ——


def test_never_ran_jobs_still_present():
    health = evaluate_runs([])
    assert set(health) == {"brief", "weekly"}
    assert health["brief"].ever_ran is False
    assert health["brief"].total_runs == 0
    assert health["brief"].consecutive_failures == 0


def test_consecutive_failures_counts_trailing_only():
    events = [
        _ev("brief", RunStatus.SUCCESS, "2026-09-01"),
        _ev("brief", RunStatus.FAILED, "2026-09-02"),
        _ev("brief", RunStatus.FAILED, "2026-09-03"),
    ]
    brief = evaluate_runs(events)["brief"]
    assert brief.consecutive_failures == 2
    assert brief.last_status is RunStatus.FAILED
    assert brief.last_day == "2026-09-03"
    assert brief.ok is False


def test_success_or_degraded_breaks_streak_and_is_ok():
    events = [
        _ev("brief", RunStatus.FAILED, "2026-09-01"),
        _ev("brief", RunStatus.FAILED, "2026-09-02"),
        _ev("brief", RunStatus.DEGRADED, "2026-09-03"),
    ]
    brief = evaluate_runs(events)["brief"]
    assert brief.consecutive_failures == 0
    assert brief.ok is True  # 降级也算跑出来了
    assert brief.ran_on("2026-09-03") is True
    assert brief.ran_on("2026-09-04") is False


# —— 持久层：心跳读写 + 版本 + 容错 ——


def test_record_and_read_roundtrip_with_version(tmp_path):
    vault = tmp_path / "_vault"
    record_run(vault, job="brief", status=RunStatus.SUCCESS, day="2026-09-02")
    row = json.loads(_log(vault).read_text(encoding="utf-8").splitlines()[0])
    assert row["schema_version"] == RUN_HEARTBEAT_VERSION
    assert row["job"] == "brief"
    assert row["status"] == "success"
    events = read_events(vault)
    assert len(events) == 1 and events[0].status is RunStatus.SUCCESS


def test_legacy_row_without_version_reads_as_v1():
    row = RunHeartbeatRow.model_validate_json(
        json.dumps({"job": "brief", "status": "failed", "timestamp": "2026-09-02T08:00:00+00:00"})
    )
    assert row.schema_version == 1
    assert row.to_event().status is RunStatus.FAILED


def test_corrupt_tail_line_does_not_break_read(tmp_path):
    vault = tmp_path / "_vault"
    record_run(vault, job="brief", status=RunStatus.SUCCESS, day="2026-09-02")
    with _log(vault).open("a", encoding="utf-8") as fh:
        fh.write('{"job": "weekly", "sta')  # 半截行
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", CorruptLogLine)
        events = read_events(vault)
    assert len(events) == 1 and events[0].job == "brief"


# —— 心跳记录的最佳努力：绝不反噬任务 ——


def test_record_run_safely_swallows_errors(monkeypatch, tmp_path):
    """记录心跳失败（如落盘异常）被吞，绝不反过来令任务失败。"""
    from summit_workbench.observability import heartbeat

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(heartbeat, "record_run", boom)
    # 不应抛出。
    heartbeat.record_run_safely(
        tmp_path / "_vault", job="brief", status=RunStatus.FAILED, day="2026-09-02"
    )


# —— 告警：连续失败去重 ——


def _report_with_runs(runs) -> StatusReport:
    return StatusReport(
        month="2026-09",
        total_meetings=0,
        state_counts={},
        usage=UsageTotals(0, 0, 0, 0.0, "CNY"),
        budget=evaluate_budget(0.0, None, "CNY"),
        backlog=BacklogState(count=0, oldest_age_days=None),
        runs=runs,
        feishu_auth=FeishuAuthState(),
    )


def test_three_consecutive_failures_alerts_once_then_dedups():
    runs = evaluate_runs([_ev("brief", RunStatus.FAILED, f"2026-09-0{i}") for i in (1, 2, 3)])
    report = _report_with_runs(runs)
    notes, state = evaluate_notifications(report, NotifyState(month="2026-09"))
    assert [n.kind for n in notes] == ["run"]
    assert state.run_failures_alerted["brief"] == 3
    # 同状态再评估：不重复告警。
    again, _ = evaluate_notifications(report, state)
    assert again == []


def test_below_threshold_does_not_alert():
    runs = evaluate_runs([_ev("brief", RunStatus.FAILED, f"2026-09-0{i}") for i in (1, 2)])
    notes, _ = evaluate_notifications(_report_with_runs(runs), NotifyState(month="2026-09"))
    assert notes == []


def test_growing_streak_renotifies_and_success_resets():
    three = evaluate_runs([_ev("brief", RunStatus.FAILED, f"2026-09-0{i}") for i in (1, 2, 3)])
    _, state = evaluate_notifications(_report_with_runs(three), NotifyState(month="2026-09"))
    # 连击增至 4：再告警一次。
    four = evaluate_runs([_ev("brief", RunStatus.FAILED, f"2026-09-0{i}") for i in (1, 2, 3, 4)])
    notes2, state2 = evaluate_notifications(_report_with_runs(four), state)
    assert [n.kind for n in notes2] == ["run"]
    assert state2.run_failures_alerted["brief"] == 4
    # 成功清零后，未来新连击可重新告警。
    recovered = evaluate_runs([_ev("brief", RunStatus.SUCCESS, "2026-09-05")])
    _, state3 = evaluate_notifications(_report_with_runs(recovered), state2)
    assert state3.run_failures_alerted["brief"] == 0
