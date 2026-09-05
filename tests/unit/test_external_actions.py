"""P0-04：外部动作状态机的安全转换。"""

from __future__ import annotations

from summit_workbench.domain.external_action import ExternalActionKind, ExternalActionState
from summit_workbench.repositories.external_action_outbox import latest_action
from summit_workbench.workflows.external_actions import (
    authorize_retry,
    mark_sending,
    mark_succeeded,
    mark_unknown,
    prepare_action,
    reconcile_not_found,
    reconcile_succeeded,
)


def _prepared(tmp_path):
    return prepare_action(
        tmp_path / "vault",
        candidate_id="m#task-0",
        kind=ExternalActionKind.FEISHU_TASK,
        request={"description": "任务"},
        target_account_ref="feishu:user",
    )


def test_unknown_requires_reconciliation_before_retry(tmp_path):
    action = _prepared(tmp_path)
    sending = mark_sending(tmp_path / "vault", action)
    unknown = mark_unknown(tmp_path / "vault", sending, "飞书请求超时")
    assert unknown.state is ExternalActionState.UNKNOWN
    assert unknown.retry_allowed is False

    succeeded = reconcile_succeeded(tmp_path / "vault", unknown, "remote-1")
    assert succeeded.state is ExternalActionState.RECONCILED_SUCCEEDED
    assert succeeded.remote_id == "remote-1"


def test_not_found_needs_second_confirmation_to_authorize_retry(tmp_path):
    action = _prepared(tmp_path)
    unknown = mark_unknown(tmp_path / "vault", mark_sending(tmp_path / "vault", action), "超时")
    not_found = reconcile_not_found(tmp_path / "vault", unknown)
    assert not_found.state is ExternalActionState.RECONCILED_NOT_FOUND
    assert not_found.retry_allowed is False

    retry = authorize_retry(tmp_path / "vault", not_found, confirm=True)
    assert retry.state is ExternalActionState.PREPARED
    assert retry.retry_allowed is True
    latest = latest_action(tmp_path / "vault", action.operation_id)
    assert latest is not None
    assert latest.state is ExternalActionState.PREPARED


def test_succeeded_transition_records_remote_id(tmp_path):
    action = _prepared(tmp_path)
    sending = mark_sending(tmp_path / "vault", action)
    succeeded = mark_succeeded(tmp_path / "vault", sending, "task-1")
    assert succeeded.state is ExternalActionState.SUCCEEDED
    assert succeeded.remote_id == "task-1"
