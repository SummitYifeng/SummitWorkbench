"""会议处理状态账本读写测试（M1-2）。"""

from __future__ import annotations

import warnings

from summit_workbench.domain.pipeline import MeetingTask, ProcessingState, SourceKind
from summit_workbench.repositories._jsonl import CorruptLogLine
from summit_workbench.repositories.meeting_state import (
    _state_log,
    all_latest,
    latest_task,
    record_task,
)


def test_latest_returns_none_when_empty(tmp_path):
    assert latest_task(tmp_path, "m1:n1") is None
    assert all_latest(tmp_path) == {}


def test_record_and_latest_roundtrip(tmp_path):
    task = MeetingTask.for_remote("m1", "n1")
    record_task(tmp_path, task)
    got = latest_task(tmp_path, "m1:n1")
    assert got is not None
    assert got.state == ProcessingState.DISCOVERED
    assert got.source == SourceKind.FEISHU_NOTE
    assert got.meeting_id == "m1"
    assert got.note_id == "n1"


def test_latest_reflects_most_recent_state(tmp_path):
    task = MeetingTask.for_remote("m1", "n1")
    record_task(tmp_path, task)
    record_task(tmp_path, task.advanced_to(ProcessingState.FETCHED))
    archived = task.advanced_to(ProcessingState.FETCHED).advanced_to(ProcessingState.ARCHIVED)
    record_task(tmp_path, archived)
    got = latest_task(tmp_path, "m1:n1")
    assert got is not None and got.state == ProcessingState.ARCHIVED


def test_reason_persisted_on_unavailable(tmp_path):
    task = MeetingTask.for_remote("m2", None).advanced_to(
        ProcessingState.UNAVAILABLE, reason="无完整逐字稿权限"
    )
    record_task(tmp_path, task)
    got = latest_task(tmp_path, "m2")
    assert got is not None
    assert got.state == ProcessingState.UNAVAILABLE
    assert got.reason == "无完整逐字稿权限"


def test_all_latest_keeps_one_per_key(tmp_path):
    record_task(tmp_path, MeetingTask.for_remote("m1", "n1"))
    record_task(
        tmp_path,
        MeetingTask.for_remote("m1", "n1").advanced_to(ProcessingState.FETCHED),
    )
    local_task = MeetingTask.for_local("body text")
    record_task(tmp_path, local_task)
    latest = all_latest(tmp_path)
    assert set(latest) == {"m1:n1", local_task.idem_key}  # 同一 key 只留最新
    assert latest["m1:n1"].state == ProcessingState.FETCHED
    assert latest[local_task.idem_key].source == SourceKind.LOCAL_FILE


def test_corrupt_tail_line_does_not_break_lookup(tmp_path):
    """半截末行（被 kill/断电）不再让整本崩溃：前面的状态仍可查（LHF #2）。"""
    record_task(tmp_path, MeetingTask.for_remote("m1", "n1"))
    with _state_log(tmp_path).open("a", encoding="utf-8") as fh:
        fh.write('{"idem_key": "m9", "sour')  # 半截行
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", CorruptLogLine)
        got = latest_task(tmp_path, "m1:n1")
        assert got is not None and got.state == ProcessingState.DISCOVERED
        assert set(all_latest(tmp_path)) == {"m1:n1"}
