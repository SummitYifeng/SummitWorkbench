"""外部动作中断恢复：只恢复本机确认已停止的执行者。"""

from __future__ import annotations

import threading

import summit_workbench.workflows.external_actions as external_actions
from summit_workbench.domain.external_action import ExternalActionKind, ExternalActionState
from summit_workbench.repositories.external_action_outbox import latest_action
from summit_workbench.workflows.external_actions import (
    external_action_execution,
    mark_sending,
    prepare_action,
    recover_interrupted_actions,
)


def _prepared(vault):
    return prepare_action(
        vault,
        candidate_id="meeting-1#action-item-0",
        kind=ExternalActionKind.FEISHU_TASK,
        request={"description": "准备发布"},
        target_account_ref="feishu:user",
    )


def test_disappeared_local_executor_is_recovered_once(tmp_path, monkeypatch):
    support = tmp_path / "application-support"
    monkeypatch.setattr(external_actions, "app_support_dir", lambda: support)
    vault = tmp_path / "vault"
    action = mark_sending(vault, _prepared(vault), executor_id="old-executor")

    recovered = recover_interrupted_actions(vault, executor_id="new-executor")

    assert [item.operation_id for item in recovered] == [action.operation_id]
    latest = latest_action(vault, action.operation_id)
    assert latest is not None
    assert latest.state is ExternalActionState.UNKNOWN
    assert latest.error == "external_action_interrupted"
    assert recover_interrupted_actions(vault, executor_id="new-executor") == []


def test_active_local_executor_cannot_be_recovered(tmp_path, monkeypatch):
    support = tmp_path / "application-support"
    monkeypatch.setattr(external_actions, "app_support_dir", lambda: support)
    vault = tmp_path / "vault"
    prepared = _prepared(vault)
    started = threading.Event()
    release = threading.Event()

    def active_executor() -> None:
        with external_action_execution(vault, prepared, executor_id="active-executor"):
            mark_sending(vault, prepared, executor_id="active-executor")
            started.set()
            release.wait(timeout=5)

    thread = threading.Thread(target=active_executor)
    thread.start()
    assert started.wait(timeout=5)
    try:
        assert recover_interrupted_actions(vault, executor_id="recovery-executor") == []
        latest = latest_action(vault, prepared.operation_id)
        assert latest is not None
        assert latest.state is ExternalActionState.SENDING
    finally:
        release.set()
        thread.join(timeout=5)
    assert not thread.is_alive()


def test_old_jsonl_without_executor_id_remains_readable_and_is_not_recovered(tmp_path, monkeypatch):
    support = tmp_path / "application-support"
    monkeypatch.setattr(external_actions, "app_support_dir", lambda: support)
    vault = tmp_path / "vault"
    action = mark_sending(vault, _prepared(vault))

    latest = latest_action(vault, action.operation_id)
    assert latest is not None
    assert latest.executor_id is None
    assert recover_interrupted_actions(vault, executor_id="recovery-executor") == []


def test_two_recovery_workers_only_append_one_unknown_transition(tmp_path, monkeypatch):
    support = tmp_path / "application-support"
    monkeypatch.setattr(external_actions, "app_support_dir", lambda: support)
    vault = tmp_path / "vault"
    action = mark_sending(vault, _prepared(vault), executor_id="old-executor")
    barrier = threading.Barrier(2)
    results: list[list[str]] = []

    def recover(worker_id: str) -> None:
        barrier.wait(timeout=5)
        results.append(
            [
                item.operation_id
                for item in recover_interrupted_actions(vault, executor_id=worker_id)
            ]
        )

    threads = [
        threading.Thread(target=recover, args=("recovery-a",)),
        threading.Thread(target=recover, args=("recovery-b",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert all(not thread.is_alive() for thread in threads)
    assert sorted(sum(results, [])) == [action.operation_id]
    latest = latest_action(vault, action.operation_id)
    assert latest is not None
    assert latest.state is ExternalActionState.UNKNOWN
