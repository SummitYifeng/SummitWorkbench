"""外部副作用 outbox 的追加型、schema-versioned JSONL 仓库。"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from summit_workbench.config.locking import workspace_lock
from summit_workbench.domain.external_action import (
    ExternalAction,
    ExternalActionKind,
    ExternalActionState,
)
from summit_workbench.repositories._jsonl import append_row, read_models
from summit_workbench.repositories._schema import EXTERNAL_ACTION_VERSION, SCHEMA_VERSION_FIELD

EXTERNAL_ACTIONS_SUBDIR = ("_signals", "external-actions")


class ExternalActionRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: int = EXTERNAL_ACTION_VERSION
    operation_id: str
    candidate_id: str
    workspace_id: str
    kind: ExternalActionKind
    request_fingerprint: str
    target_account_ref: str
    state: ExternalActionState
    attempt: int
    timestamp: str
    remote_id: str | None = None
    error: str | None = None
    retry_allowed: bool = False


def outbox_path(vault_dir: Path) -> Path:
    return vault_dir.joinpath(*EXTERNAL_ACTIONS_SUBDIR, "log.jsonl")


def _to_domain(row: ExternalActionRow) -> ExternalAction:
    return ExternalAction(
        operation_id=row.operation_id,
        candidate_id=row.candidate_id,
        workspace_id=row.workspace_id,
        kind=row.kind,
        request_fingerprint=row.request_fingerprint,
        target_account_ref=row.target_account_ref,
        state=row.state,
        attempt=row.attempt,
        timestamp=row.timestamp,
        remote_id=row.remote_id,
        error=row.error,
        retry_allowed=row.retry_allowed,
    )


def read_actions(vault_dir: Path) -> list[ExternalAction]:
    """读取有效动作行；坏行沿用通用 quarantine 语义，不影响其它动作。"""
    return [_to_domain(row) for row in read_models(outbox_path(vault_dir), ExternalActionRow)]


def append_action(vault_dir: Path, action: ExternalAction) -> Path:
    row = asdict(action)
    row["kind"] = action.kind.value
    row["state"] = action.state.value
    row[SCHEMA_VERSION_FIELD] = EXTERNAL_ACTION_VERSION
    with workspace_lock(vault_dir.parent):
        return append_row(outbox_path(vault_dir), row)


def latest_action(vault_dir: Path, operation_id: str) -> ExternalAction | None:
    for action in reversed(read_actions(vault_dir)):
        if action.operation_id == operation_id:
            return action
    return None


def latest_for_candidate(
    vault_dir: Path,
    candidate_id: str,
    *,
    workspace_id: str | None = None,
    kind: ExternalActionKind | None = None,
    request_fingerprint: str | None = None,
) -> ExternalAction | None:
    """取指定工作区内候选的最后一条动作，可按动作类型/指纹进一步收窄。"""
    for action in reversed(read_actions(vault_dir)):
        if action.candidate_id != candidate_id:
            continue
        if workspace_id is not None and action.workspace_id != workspace_id:
            continue
        if kind is not None and action.kind is not kind:
            continue
        if request_fingerprint is not None and action.request_fingerprint != request_fingerprint:
            continue
        return action
    return None


def latest_actions(vault_dir: Path, *, workspace_id: str | None = None) -> list[ExternalAction]:
    """按操作 id 压缩为最新状态，保留最后写入顺序。"""
    latest: dict[str, ExternalAction] = {}
    for action in read_actions(vault_dir):
        if workspace_id is None or action.workspace_id == workspace_id:
            latest[action.operation_id] = action
    return list(latest.values())
