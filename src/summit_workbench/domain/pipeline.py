"""会议处理链路的稳定状态机与幂等键（供应商无关，纯逻辑）。

对应 PRD 3.1.9 L14 第 6 条的防重规则与 DEVELOPMENT_PLAN §6 M1-1：

- ``ProcessingState`` 主状态 ``discovered → fetched → archived → processed →
  pending-review → applied/ignored``，外加 ``unavailable/failed`` 分支。
- 幂等键：飞书链路用 ``meeting_id + note_id``；本地导入用逐字稿内容哈希。
- ``MeetingTask`` 是把「来源 + 幂等键 + 处理状态」绑在一起的可推进记录。

本模块不读文件、不访问网络；持久化由 repositories 层负责。``ProcessingState`` 的字符串值
与 ``domain.vault.STATUS_VOCAB`` 中会议笔记会经历的状态（archived/pending-review/
applied/ignored）刻意保持一致，但两者是不同关注点：这里跟踪链路进度，那里是笔记 frontmatter。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from enum import StrEnum


class SourceKind(StrEnum):
    """逐字稿来源。与 ``providers...TranscriptResult.source`` 的字符串一致。"""

    FEISHU_NOTE = "feishu-note"
    LOCAL_FILE = "local-file"


class ProcessingState(StrEnum):
    """一场会议在处理链路中的位置。

    主链路：``DISCOVERED → FETCHED → ARCHIVED → PROCESSED → PENDING_REVIEW →
    APPLIED / IGNORED``。分支：``UNAVAILABLE``（无完整文本权限，L14 第 7 条）、
    ``FAILED``（模型调用耗尽重试，L41）。
    """

    DISCOVERED = "discovered"
    FETCHED = "fetched"
    ARCHIVED = "archived"
    PROCESSED = "processed"
    PENDING_REVIEW = "pending-review"
    APPLIED = "applied"
    IGNORED = "ignored"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


# 允许的状态迁移。空集合表示终态。
# - FETCHED 只进 ARCHIVED：双文件归档必须先于模型调用（L15）。取稿的瞬时失败不改状态，
#   停在 DISCOVERED 等重试；确认无完整文本权限才置 UNAVAILABLE。
# - 模型失败只发生在 ARCHIVED/PROCESSED 之后（L41），保留原文进 FAILED。
# - UNAVAILABLE / FAILED 可在用户修复权限、额度或配置后显式重试。
ALLOWED_TRANSITIONS: dict[ProcessingState, frozenset[ProcessingState]] = {
    ProcessingState.DISCOVERED: frozenset({ProcessingState.FETCHED, ProcessingState.UNAVAILABLE}),
    ProcessingState.FETCHED: frozenset({ProcessingState.ARCHIVED}),
    ProcessingState.ARCHIVED: frozenset({ProcessingState.PROCESSED, ProcessingState.FAILED}),
    ProcessingState.PROCESSED: frozenset({ProcessingState.PENDING_REVIEW, ProcessingState.FAILED}),
    ProcessingState.PENDING_REVIEW: frozenset({ProcessingState.APPLIED, ProcessingState.IGNORED}),
    ProcessingState.APPLIED: frozenset(),
    ProcessingState.IGNORED: frozenset(),
    ProcessingState.UNAVAILABLE: frozenset({ProcessingState.FETCHED}),
    ProcessingState.FAILED: frozenset({ProcessingState.PROCESSED, ProcessingState.FAILED}),
}

# 完全了结、不再推进的终态。UNAVAILABLE / FAILED 不在此列：它们是可重试的停泊态。
TERMINAL_STATES = frozenset({ProcessingState.APPLIED, ProcessingState.IGNORED})


class InvalidTransition(ValueError):
    """尝试了状态机不允许的迁移。"""

    def __init__(self, src: ProcessingState, dst: ProcessingState) -> None:
        allowed = sorted(s.value for s in ALLOWED_TRANSITIONS[src])
        super().__init__(
            f"不允许的状态迁移 {src.value} → {dst.value}；{src.value} 只能进 {allowed}"
        )
        self.src = src
        self.dst = dst


def can_transition(src: ProcessingState, dst: ProcessingState) -> bool:
    """``src`` 是否允许迁移到 ``dst``。"""
    return dst in ALLOWED_TRANSITIONS[src]


def ensure_transition(src: ProcessingState, dst: ProcessingState) -> None:
    """迁移非法时抛 ``InvalidTransition``。"""
    if not can_transition(src, dst):
        raise InvalidTransition(src, dst)


def is_terminal(state: ProcessingState) -> bool:
    """是否为完全了结的终态（applied/ignored）。"""
    return state in TERMINAL_STATES


def remote_idempotency_key(meeting_id: str, note_id: str | None) -> str:
    """飞书链路幂等键：``meeting_id`` 或 ``meeting_id:note_id``。

    无 ``note_id`` 的会议（通常无完整文本、记为 unavailable）以 ``meeting_id`` 独占防重。
    """
    if not meeting_id:
        raise ValueError("meeting_id 不能为空")
    return f"{meeting_id}:{note_id}" if note_id else meeting_id


def local_idempotency_key(content: str) -> str:
    """本地导入幂等键：逐字稿内容的 SHA-256（无 meeting_id/note_id 时的稳定防重）。

    对内容做 strip 归一，避免尾随空白导致同一份逐字稿产生不同键。
    """
    if not content.strip():
        raise ValueError("本地逐字稿内容为空，无法计算幂等键")
    digest = hashlib.sha256(content.strip().encode("utf-8")).hexdigest()
    return f"local:{digest}"


@dataclass(frozen=True)
class MeetingTask:
    """会议处理链路上的一条可推进记录：来源 + 幂等键 + 当前状态。

    不可变；``advanced_to`` 返回校验过迁移的新实例。``reason`` 承载 unavailable/failed
    的原因，供 ``wb status`` 与错误队列显示（L14 第 7 条 / L41）。
    """

    idem_key: str
    source: SourceKind
    state: ProcessingState
    meeting_id: str | None = None
    note_id: str | None = None
    reason: str | None = None

    @classmethod
    def for_remote(
        cls,
        meeting_id: str,
        note_id: str | None,
        *,
        state: ProcessingState = ProcessingState.DISCOVERED,
    ) -> MeetingTask:
        """从飞书会议发现新建一条任务（默认 discovered）。"""
        return cls(
            idem_key=remote_idempotency_key(meeting_id, note_id),
            source=SourceKind.FEISHU_NOTE,
            state=state,
            meeting_id=meeting_id,
            note_id=note_id,
        )

    @classmethod
    def for_local(
        cls,
        content: str,
        *,
        meeting_id: str | None = None,
        state: ProcessingState = ProcessingState.FETCHED,
    ) -> MeetingTask:
        """从本地导入的逐字稿新建一条任务（逐字稿已在手，默认 fetched）。"""
        return cls(
            idem_key=local_idempotency_key(content),
            source=SourceKind.LOCAL_FILE,
            state=state,
            meeting_id=meeting_id,
        )

    def advanced_to(self, new_state: ProcessingState, *, reason: str | None = None) -> MeetingTask:
        """迁移到 ``new_state``，非法迁移抛 ``InvalidTransition``。"""
        ensure_transition(self.state, new_state)
        return replace(self, state=new_state, reason=reason)

    @property
    def is_terminal(self) -> bool:
        return is_terminal(self.state)
