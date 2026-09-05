"""外部副作用的两阶段状态机与人工核对边界（P0-04）。"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from summit_workbench.config.locking import workspace_lock
from summit_workbench.domain.external_action import (
    ExternalAction,
    ExternalActionKind,
    ExternalActionState,
)
from summit_workbench.repositories.external_action_outbox import append_action


def workspace_id_for_vault(vault_dir: Path) -> str:
    """返回不含秘密的工作区标识。

    P0-07 起优先读 vault 内 workspace marker（``.summit-workbench/workspace.json``，
    随 Git 同步，跨设备稳定）；无 marker 的旧 vault 沿用规范化 vault 容器路径的
    不可逆短摘要作为兼容标识。路径本身不写入 outbox，不同 vault 不会复用候选动作。
    """
    from summit_workbench.repositories.workspace_manifest import (
        WorkspaceManifestError,
        load_workspace_manifest,
    )

    try:
        manifest = load_workspace_manifest(vault_dir)
    except WorkspaceManifestError:
        manifest = None
    if manifest is not None:
        return manifest.workspace_id
    root = vault_dir.expanduser().resolve().parent
    return "legacy-" + hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:24]


def request_fingerprint(
    *,
    candidate_id: str,
    kind: ExternalActionKind,
    business_request: dict[str, object],
) -> str:
    """仅对规范化业务字段做指纹，不把凭据、请求 body 或模型输入放入账本。"""
    canonical = {
        "candidate_id": candidate_id,
        "kind": kind.value,
        "request": business_request,
    }
    payload = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _append(vault_dir: Path, action: ExternalAction) -> ExternalAction:
    # 每次状态落盘单独持有文件临界区；绝不把外部网络调用放进锁内。
    with workspace_lock(vault_dir.parent):
        append_action(vault_dir, action)
    return action


def prepare_action(
    vault_dir: Path,
    *,
    candidate_id: str,
    kind: ExternalActionKind,
    request: dict[str, object],
    target_account_ref: str,
    operation_id: str | None = None,
    retry_allowed: bool = False,
    fingerprint: str | None = None,
    attempt: int = 0,
) -> ExternalAction:
    action = ExternalAction(
        operation_id=operation_id or str(uuid4()),
        candidate_id=candidate_id,
        workspace_id=workspace_id_for_vault(vault_dir),
        kind=kind,
        request_fingerprint=fingerprint
        or request_fingerprint(candidate_id=candidate_id, kind=kind, business_request=request),
        target_account_ref=target_account_ref,
        state=ExternalActionState.PREPARED,
        attempt=attempt,
        timestamp=_timestamp(),
        retry_allowed=retry_allowed,
    )
    return _append(vault_dir, action)


def _transition(
    vault_dir: Path,
    action: ExternalAction,
    *,
    state: ExternalActionState,
    attempt: int | None = None,
    remote_id: str | None = None,
    error: str | None = None,
    retry_allowed: bool = False,
) -> ExternalAction:
    next_action = ExternalAction(
        operation_id=action.operation_id,
        candidate_id=action.candidate_id,
        workspace_id=action.workspace_id,
        kind=action.kind,
        request_fingerprint=action.request_fingerprint,
        target_account_ref=action.target_account_ref,
        state=state,
        attempt=action.attempt if attempt is None else attempt,
        timestamp=_timestamp(),
        remote_id=remote_id if remote_id is not None else action.remote_id,
        error=error,
        retry_allowed=retry_allowed,
    )
    return _append(vault_dir, next_action)


def mark_sending(vault_dir: Path, action: ExternalAction) -> ExternalAction:
    if action.state is not ExternalActionState.PREPARED:
        raise ValueError(f"只有 prepared 动作可以发送：{action.state.value}")
    return _transition(
        vault_dir, action, state=ExternalActionState.SENDING, attempt=action.attempt + 1
    )


def _redact_error(error: str) -> str:
    text = re.sub(
        r"(?i)(bearer\s+|access[_-]?token|refresh[_-]?token)[^\s,;]+", "[redacted]", error
    )
    text = re.sub(
        r"(?i)(app[_-]?secret|client[_-]?secret|model[_-]?key)\s*[=:]\s*[^\s,;]+",
        r"\1=[redacted]",
        text,
    )
    return text[:240]


def mark_succeeded(vault_dir: Path, action: ExternalAction, remote_id: str) -> ExternalAction:
    if action.state is not ExternalActionState.SENDING:
        raise ValueError(f"只有 sending 动作可以成功收口：{action.state.value}")
    if not remote_id.strip():
        raise ValueError("成功的外部动作必须有 remote_id")
    return _transition(
        vault_dir,
        action,
        state=ExternalActionState.SUCCEEDED,
        remote_id=remote_id,
    )


def mark_failed(vault_dir: Path, action: ExternalAction, error: str) -> ExternalAction:
    if action.state is not ExternalActionState.SENDING:
        raise ValueError(f"只有 sending 动作可以失败收口：{action.state.value}")
    return _transition(
        vault_dir,
        action,
        state=ExternalActionState.FAILED,
        error=_redact_error(error),
    )


def mark_unknown(vault_dir: Path, action: ExternalAction, error: str) -> ExternalAction:
    if action.state is not ExternalActionState.SENDING:
        raise ValueError(f"只有 sending 动作可以进入未知：{action.state.value}")
    return _transition(
        vault_dir,
        action,
        state=ExternalActionState.UNKNOWN,
        error=_redact_error(error),
    )


def reconcile_succeeded(vault_dir: Path, action: ExternalAction, remote_id: str) -> ExternalAction:
    if action.state is not ExternalActionState.UNKNOWN:
        raise ValueError(f"只有 unknown 动作可以核对为已创建：{action.state.value}")
    if not remote_id.strip():
        raise ValueError("核对为已创建时必须提供 remote_id")
    return _transition(
        vault_dir,
        action,
        state=ExternalActionState.RECONCILED_SUCCEEDED,
        remote_id=remote_id,
    )


def reconcile_not_found(vault_dir: Path, action: ExternalAction) -> ExternalAction:
    if action.state is not ExternalActionState.UNKNOWN:
        raise ValueError(f"只有 unknown 动作可以核对为未找到：{action.state.value}")
    return _transition(
        vault_dir,
        action,
        state=ExternalActionState.RECONCILED_NOT_FOUND,
    )


def authorize_retry(vault_dir: Path, action: ExternalAction, *, confirm: bool) -> ExternalAction:
    """第二次明确确认后才允许对「核对未找到」动作重新准备。"""
    if action.state is not ExternalActionState.RECONCILED_NOT_FOUND:
        raise ValueError(f"只有 reconciled-not-found 动作可以重试：{action.state.value}")
    if not confirm:
        raise ValueError("重试外部创建需要再次确认")
    return prepare_action(
        vault_dir,
        candidate_id=action.candidate_id,
        kind=action.kind,
        request={},
        target_account_ref=action.target_account_ref,
        operation_id=action.operation_id,
        retry_allowed=True,
        fingerprint=action.request_fingerprint,
        attempt=action.attempt,
    )
