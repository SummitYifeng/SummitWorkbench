"""P0-04：外部副作用 outbox 的持久化、容错读与工作区隔离。"""

from __future__ import annotations

import json

import pytest

from summit_workbench.domain.external_action import ExternalActionKind, ExternalActionState
from summit_workbench.repositories.external_action_outbox import (
    latest_action,
)
from summit_workbench.workflows.external_actions import (
    prepare_action,
    workspace_id_for_vault,
)


def test_prepared_action_survives_restart(tmp_path):
    vault = tmp_path / "vault"
    action = prepare_action(
        vault,
        candidate_id="meeting-1#action-item-0",
        kind=ExternalActionKind.FEISHU_TASK,
        request={"description": "准备发布", "due_date": "2026-09-10"},
        target_account_ref="feishu:user",
    )

    assert action.state is ExternalActionState.PREPARED
    reloaded = latest_action(vault, action.operation_id)
    assert reloaded is not None
    assert reloaded.operation_id == action.operation_id
    assert reloaded.state is ExternalActionState.PREPARED


def test_corrupt_outbox_row_is_quarantined(tmp_path):
    vault = tmp_path / "vault"
    action = prepare_action(
        vault,
        candidate_id="meeting-1#action-item-0",
        kind=ExternalActionKind.FEISHU_TASK,
        request={"description": "准备发布"},
        target_account_ref="feishu:user",
    )
    log = vault / "_signals" / "external-actions" / "log.jsonl"
    with log.open("a", encoding="utf-8") as fh:
        fh.write("{not-json}\n")

    with pytest.warns(UserWarning):
        reloaded = latest_action(vault, action.operation_id)

    assert reloaded is not None
    assert log.with_name("log.jsonl.quarantine").is_file()
    assert "{not-json}" in log.with_name("log.jsonl.quarantine").read_text(encoding="utf-8")


def test_same_candidate_in_two_workspaces_does_not_collide(tmp_path):
    vault_a = tmp_path / "a" / "vault"
    vault_b = tmp_path / "b" / "vault"
    candidate_id = "meeting-1#action-item-0"
    action_a = prepare_action(
        vault_a,
        candidate_id=candidate_id,
        kind=ExternalActionKind.FEISHU_TASK,
        request={"description": "A"},
        target_account_ref="feishu:user",
    )
    action_b = prepare_action(
        vault_b,
        candidate_id=candidate_id,
        kind=ExternalActionKind.FEISHU_TASK,
        request={"description": "B"},
        target_account_ref="feishu:user",
    )

    assert workspace_id_for_vault(vault_a) != workspace_id_for_vault(vault_b)
    assert latest_action(vault_a, action_a.operation_id).request_fingerprint != (  # type: ignore[union-attr]
        latest_action(vault_b, action_b.operation_id).request_fingerprint  # type: ignore[union-attr]
    )


def test_outbox_rows_are_schema_versioned_and_business_request_only(tmp_path):
    vault = tmp_path / "vault"
    action = prepare_action(
        vault,
        candidate_id="m#task-0",
        kind=ExternalActionKind.FEISHU_TASK,
        request={"description": "业务请求", "due_date": None},
        target_account_ref="feishu:user",
    )
    row = json.loads(
        (vault / "_signals" / "external-actions" / "log.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    assert row["schema_version"] == 1
    assert row["request_fingerprint"] == action.request_fingerprint
    assert "description" not in row
    assert "token" not in json.dumps(row).lower()
