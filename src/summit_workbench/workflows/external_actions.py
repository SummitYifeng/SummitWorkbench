"""外部副作用的两阶段状态机与人工核对边界（P0-04）。"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from summit_workbench.config.app_support import app_support_dir
from summit_workbench.config.locking import LockBusy, workspace_lock
from summit_workbench.domain.external_action import (
    ExternalAction,
    ExternalActionKind,
    ExternalActionState,
)
from summit_workbench.repositories._atomic import atomic_write_text
from summit_workbench.repositories.external_action_outbox import (
    append_action,
    latest_action,
    latest_actions,
)

EXTERNAL_ACTION_INTERRUPTED = "external_action_interrupted"
EXTERNAL_ACTION_ACCOUNTING_FAILED = "external_action_accounting_failed"
OPERATION_OUTCOME_UNKNOWN = "operation_outcome_unknown"


def _execution_root(action: ExternalAction) -> Path:
    """Return the per-operation local state root outside the synced vault."""
    return app_support_dir() / "runtime" / "external-actions" / action.workspace_id


def _execution_record_path(action: ExternalAction) -> Path:
    return _execution_root(action) / f"{action.operation_id}.json"


def _execution_lock_root(action: ExternalAction) -> Path:
    return (
        app_support_dir() / "locks" / "external-actions" / action.workspace_id / action.operation_id
    )


def _write_execution_record(action: ExternalAction, executor_id: str) -> None:
    record = {
        "operation_id": action.operation_id,
        "workspace_id": action.workspace_id,
        "executor_id": executor_id,
        "kind": action.kind.value,
        "pid": os.getpid(),
        "started_at": _timestamp(),
    }
    atomic_write_text(
        _execution_record_path(action),
        json.dumps(record, ensure_ascii=False, sort_keys=True),
        ensure_parents=True,
        new_mode=0o600,
    )


def _clear_execution_record(action: ExternalAction, executor_id: str | None = None) -> None:
    path = _execution_record_path(action)
    try:
        if executor_id is not None:
            record = json.loads(path.read_text(encoding="utf-8"))
            if record.get("executor_id") != executor_id:
                return
        path.unlink()
    except (FileNotFoundError, OSError, ValueError):
        # The synced outbox is the source of truth.  A stale local marker is
        # diagnostic state and must not make a successful transition fail.
        return


def _local_executor_matches(action: ExternalAction) -> bool:
    if not action.executor_id:
        return False
    path = _execution_record_path(action)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        return False
    return bool(
        record.get("operation_id") == action.operation_id
        and record.get("workspace_id") == action.workspace_id
        and record.get("executor_id") == action.executor_id
    )


@contextmanager
def external_action_execution(
    vault_dir: Path, action: ExternalAction, *, executor_id: str
) -> Iterator[None]:
    """Hold a local non-blocking operation lock during one external send.

    The lock is deliberately outside the vault and is only local-machine
    coordination.  If the process disappears, flock releases while the
    marker remains for recovery to identify the interrupted local executor.
    """
    try:
        with workspace_lock(_execution_lock_root(action), timeout=0):
            _write_execution_record(action, executor_id)
            yield
    except LockBusy:
        raise ValueError("外部动作正在由另一个本机执行者处理，请稍后核对") from None
    finally:
        _clear_execution_record(action, executor_id)


def workspace_id_for_vault(vault_dir: Path) -> str:
    """返回不含秘密的工作区标识。

    P0-07 起优先读 vault 内 workspace marker（``.summit-workbench/workspace.json``，
    随 Git 同步，跨设备稳定）；无 marker 的旧 vault 沿用规范化 vault 容器路径的
    不可逆短摘要作为兼容标识。路径本身不写入 outbox，不同 vault 不会复用候选动作。

    实现下移到了 ``repositories/workspace_manifest.py``（repositories 层也要用同一实现）；
    这里保留同名再导出，既有调用方与测试不受影响。
    """
    from summit_workbench.repositories.workspace_manifest import (
        workspace_id_for_vault as _workspace_id_for_vault,
    )

    return _workspace_id_for_vault(vault_dir)


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
    executor_id: str | None = None,
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
        executor_id=executor_id if executor_id is not None else action.executor_id,
    )
    result = _append(vault_dir, next_action)
    if state is not ExternalActionState.SENDING:
        _clear_execution_record(action, action.executor_id)
    return result


def mark_sending(
    vault_dir: Path, action: ExternalAction, *, executor_id: str | None = None
) -> ExternalAction:
    if action.state is not ExternalActionState.PREPARED:
        raise ValueError(f"只有 prepared 动作可以发送：{action.state.value}")
    next_executor_id = executor_id or action.executor_id
    result = _transition(
        vault_dir,
        action,
        state=ExternalActionState.SENDING,
        attempt=action.attempt + 1,
        executor_id=next_executor_id,
    )
    if next_executor_id:
        _write_execution_record(result, next_executor_id)
    return result


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


def mark_unknown(
    vault_dir: Path,
    action: ExternalAction,
    error: str,
    *,
    remote_id: str | None = None,
) -> ExternalAction:
    if action.state is not ExternalActionState.SENDING:
        raise ValueError(f"只有 sending 动作可以进入未知：{action.state.value}")
    return _transition(
        vault_dir,
        action,
        state=ExternalActionState.UNKNOWN,
        error=_redact_error(error),
        remote_id=remote_id,
    )


def recover_interrupted_actions(vault_dir: Path, *, executor_id: str) -> list[ExternalAction]:
    """Convert only locally-owned, no-longer-running sends to ``unknown``.

    Callers must invoke this only after proving the old process stopped.  The
    per-operation flock is the final race gate; no PID is treated as a
    cross-device ownership proof, and rows without an executor identity are
    left untouched for manual reconciliation.
    """
    recovered: list[ExternalAction] = []
    workspace_id = workspace_id_for_vault(vault_dir)
    for action in latest_actions(vault_dir, workspace_id=workspace_id):
        if (
            action.state is not ExternalActionState.SENDING
            or not action.executor_id
            or action.executor_id == executor_id
            or not _local_executor_matches(action)
        ):
            continue
        try:
            with workspace_lock(_execution_lock_root(action), timeout=0):
                current = latest_action(vault_dir, action.operation_id)
                if (
                    current is None
                    or current.state is not ExternalActionState.SENDING
                    or current.executor_id != action.executor_id
                ):
                    continue
                recovered.append(mark_unknown(vault_dir, current, EXTERNAL_ACTION_INTERRUPTED))
        except (LockBusy, ValueError):
            # An active executor or a concurrent recovery won the race.
            continue
    return recovered


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
