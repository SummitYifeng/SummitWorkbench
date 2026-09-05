"""外部副作用 outbox 的领域模型（P0-04）。

该模型只描述「准备向外部系统执行什么业务动作」及其结果，不携带请求 body、凭据或模型
输入。状态变迁由 ``workflows.external_actions`` 负责并追加到本地账本。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ExternalActionKind(StrEnum):
    FEISHU_TASK = "feishu-task"
    FEISHU_MEETING = "feishu-meeting"


class ExternalActionState(StrEnum):
    PREPARED = "prepared"
    SENDING = "sending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"
    RECONCILED_SUCCEEDED = "reconciled-succeeded"
    RECONCILED_NOT_FOUND = "reconciled-not-found"


@dataclass(frozen=True)
class ExternalAction:
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
