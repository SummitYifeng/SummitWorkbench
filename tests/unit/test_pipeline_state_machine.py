"""会议处理链路状态机与幂等键测试（M1-1）。"""

from __future__ import annotations

from itertools import pairwise

import pytest

from summit_workbench.domain.pipeline import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATES,
    InvalidTransition,
    MeetingTask,
    ProcessingState,
    SourceKind,
    can_transition,
    ensure_transition,
    is_terminal,
    local_idempotency_key,
    remote_idempotency_key,
)

S = ProcessingState


def test_happy_path_transitions_allowed():
    path = [S.DISCOVERED, S.FETCHED, S.ARCHIVED, S.PROCESSED, S.PENDING_REVIEW, S.APPLIED]
    for src, dst in pairwise(path):
        assert can_transition(src, dst)


def test_pending_review_can_be_ignored():
    assert can_transition(S.PENDING_REVIEW, S.IGNORED)


def test_illegal_transition_rejected():
    assert not can_transition(S.DISCOVERED, S.APPLIED)
    assert not can_transition(S.FETCHED, S.FAILED)  # 归档前不产生模型失败
    with pytest.raises(InvalidTransition):
        ensure_transition(S.DISCOVERED, S.APPLIED)


def test_terminal_states_have_no_outgoing():
    for state in TERMINAL_STATES:
        assert ALLOWED_TRANSITIONS[state] == frozenset()
        assert is_terminal(state)


def test_unavailable_and_failed_are_retryable_not_terminal():
    assert not is_terminal(S.UNAVAILABLE)
    assert not is_terminal(S.FAILED)
    assert can_transition(S.UNAVAILABLE, S.FETCHED)  # 修复权限后重试
    assert can_transition(S.FAILED, S.PROCESSED)  # 显式重跑
    assert can_transition(S.FAILED, S.FAILED)  # 重跑再次失败


def test_every_state_has_transition_entry():
    for state in ProcessingState:
        assert state in ALLOWED_TRANSITIONS


def test_remote_key_with_and_without_note():
    assert remote_idempotency_key("m123", "n456") == "m123:n456"
    assert remote_idempotency_key("m123", None) == "m123"


def test_remote_key_requires_meeting_id():
    with pytest.raises(ValueError):
        remote_idempotency_key("", "n456")


def test_local_key_is_stable_and_whitespace_insensitive():
    a = local_idempotency_key("hello world")
    b = local_idempotency_key("  hello world\n\n")
    assert a == b
    assert a.startswith("local:")


def test_local_key_differs_by_content():
    assert local_idempotency_key("a") != local_idempotency_key("b")


def test_local_key_rejects_empty():
    with pytest.raises(ValueError):
        local_idempotency_key("   \n  ")


def test_meeting_task_remote_factory():
    task = MeetingTask.for_remote("m1", "n1")
    assert task.source == SourceKind.FEISHU_NOTE
    assert task.state == S.DISCOVERED
    assert task.idem_key == "m1:n1"


def test_meeting_task_local_factory_starts_fetched():
    task = MeetingTask.for_local("transcript body")
    assert task.source == SourceKind.LOCAL_FILE
    assert task.state == S.FETCHED
    assert task.idem_key.startswith("local:")


def test_meeting_task_advance_validates_and_is_immutable():
    task = MeetingTask.for_remote("m1", "n1")
    fetched = task.advanced_to(S.FETCHED)
    assert fetched.state == S.FETCHED
    assert task.state == S.DISCOVERED  # 原实例不变
    with pytest.raises(InvalidTransition):
        task.advanced_to(S.APPLIED)


def test_meeting_task_carries_reason_on_failure_branch():
    task = MeetingTask.for_remote("m1", "n1").advanced_to(S.FETCHED).advanced_to(S.ARCHIVED)
    failed = task.advanced_to(S.FAILED, reason="模型 4 次调用全失败")
    assert failed.state == S.FAILED
    assert failed.reason == "模型 4 次调用全失败"
    assert not failed.is_terminal


def test_discovered_to_unavailable_branch():
    task = MeetingTask.for_remote("m1", None)
    unavailable = task.advanced_to(S.UNAVAILABLE, reason="无完整逐字稿权限")
    assert unavailable.state == S.UNAVAILABLE
    assert unavailable.reason == "无完整逐字稿权限"
