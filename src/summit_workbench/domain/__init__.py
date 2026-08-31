"""领域类型与规则。

纯逻辑层：定义稳定 schema、词表、状态机与校验规则，不访问文件系统或网络
（见开发计划模块边界）。
"""

from summit_workbench.domain.meeting import ActionItem, MeetingExtraction
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
from summit_workbench.domain.review import (
    UNRESOLVED,
    ApprovalCandidate,
    CandidateDecision,
    CandidateKind,
    EvidenceRef,
    RouteTarget,
    candidate_id,
    route_candidate,
)
from summit_workbench.domain.vault import (
    NOTE_TYPES,
    REQUIRED_FRONTMATTER,
    STATUS_VOCAB,
    ValidationIssue,
    validate_note,
)

__all__ = [
    # vault schema
    "NOTE_TYPES",
    "REQUIRED_FRONTMATTER",
    "STATUS_VOCAB",
    "ValidationIssue",
    "validate_note",
    # 会议提取 schema
    "ActionItem",
    "MeetingExtraction",
    # 处理链路状态机
    "ALLOWED_TRANSITIONS",
    "TERMINAL_STATES",
    "InvalidTransition",
    "MeetingTask",
    "ProcessingState",
    "SourceKind",
    "can_transition",
    "ensure_transition",
    "is_terminal",
    "local_idempotency_key",
    "remote_idempotency_key",
    # 审批候选 / 路由
    "UNRESOLVED",
    "ApprovalCandidate",
    "CandidateDecision",
    "CandidateKind",
    "EvidenceRef",
    "RouteTarget",
    "candidate_id",
    "route_candidate",
]
