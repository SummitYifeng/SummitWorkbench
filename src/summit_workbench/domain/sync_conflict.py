"""可解释的同步冲突分类与恢复计划（P2-02，纯领域逻辑）。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath

from summit_workbench.domain.sync import SyncState, next_step_for


class ConflictKind(StrEnum):
    APPEND_ONLY_EVENT = "append-only-event"
    GENERATED_VIEW = "generated-view"
    MANUAL_MARKDOWN = "manual-markdown"
    OPAQUE_BINARY = "opaque-binary"


class ConflictAction(StrEnum):
    AUTO_COLLECT = "auto-collect"
    REBUILD = "rebuild"
    MANUAL_SELECT = "manual-select"
    PRESERVE_BOTH = "preserve-both"


class RecoveryStage(StrEnum):
    """恢复工作台当前允许推进到的阶段。"""

    PROTECTED = "protected"
    TEMPORARY_WORKTREE_VALIDATION = "temporary-worktree-validation"
    MANUAL_CONFIRMATION = "manual-confirmation"
    NOT_APPLICABLE = "not-applicable"


@dataclass(frozen=True)
class ConflictItem:
    path: str
    kind: ConflictKind
    action: ConflictAction
    automatic: bool
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "kind": self.kind.value,
            "action": self.action.value,
            "automatic": self.automatic,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ConflictExplanation:
    state: SyncState
    items: tuple[ConflictItem, ...] = ()

    @property
    def auto_mergeable(self) -> bool:
        return bool(self.items) and all(item.automatic for item in self.items)

    @property
    def manual_required(self) -> bool:
        return any(not item.automatic for item in self.items)

    def as_dict(self) -> dict[str, object]:
        return {
            "state": self.state.value,
            "auto_mergeable": self.auto_mergeable,
            "manual_required": self.manual_required,
            "next_step": next_step_for(self.state, online=True),
            "items": [item.as_dict() for item in self.items],
        }


@dataclass(frozen=True)
class ConflictRecoveryPlan:
    """描述恢复边界，但不执行恢复动作。

    这是 UI 和后续恢复 workflow 共用的安全契约。尤其重要的是：
    ``write_required`` 永远表示“后续动作是否需要写入”，而不是已发生写入；
    计划阶段本身不得改变仓库。
    """

    state: SyncState
    items: tuple[ConflictItem, ...] = ()

    @property
    def automatic_items(self) -> tuple[ConflictItem, ...]:
        return tuple(item for item in self.items if item.automatic)

    @property
    def manual_items(self) -> tuple[ConflictItem, ...]:
        return tuple(item for item in self.items if not item.automatic)

    @property
    def stage(self) -> RecoveryStage:
        if self.state is not SyncState.DIVERGED_PROTECTED:
            return RecoveryStage.NOT_APPLICABLE
        if self.manual_items:
            return RecoveryStage.MANUAL_CONFIRMATION
        if self.automatic_items:
            return RecoveryStage.TEMPORARY_WORKTREE_VALIDATION
        return RecoveryStage.PROTECTED

    @property
    def write_required(self) -> bool:
        """Whether applying the eventual plan would require a repository write."""
        return bool(self.items) and self.state is SyncState.DIVERGED_PROTECTED

    @property
    def can_prepare_in_temporary_worktree(self) -> bool:
        return self.stage is RecoveryStage.TEMPORARY_WORKTREE_VALIDATION

    def as_dict(self) -> dict[str, object]:
        return {
            "state": self.state.value,
            "stage": self.stage.value,
            "write_required": self.write_required,
            "can_prepare_in_temporary_worktree": self.can_prepare_in_temporary_worktree,
            "automatic_item_count": len(self.automatic_items),
            "manual_item_count": len(self.manual_items),
            "forbidden_actions": ["force-push", "reset", "rebase", "stash"],
            "items": [item.as_dict() for item in self.items],
        }


def _safe_path(value: str) -> str:
    candidate = value.strip().replace("\\", "/")
    path = PurePosixPath(candidate)
    if not candidate or path.is_absolute() or ".." in path.parts or "\x00" in candidate:
        raise ValueError("conflict path 必须是 vault 内相对路径")
    return path.as_posix()


def classify_conflict_path(path: str) -> ConflictItem:
    """Classify one Git-relative path without reading its contents."""
    safe = _safe_path(path)
    parts = PurePosixPath(safe).parts
    if len(parts) >= 2 and parts[0] == "_events" and safe.endswith(".json"):
        return ConflictItem(
            safe,
            ConflictKind.APPEND_ONLY_EVENT,
            ConflictAction.AUTO_COLLECT,
            True,
            "追加式 event 可合并收集，合并后重建 thread activity 投影",
        )
    if parts and parts[0] == "_views":
        return ConflictItem(
            safe,
            ConflictKind.GENERATED_VIEW,
            ConflictAction.REBUILD,
            True,
            "派生视图不作为人工事实，合并后从来源重建",
        )
    if safe.endswith(".md"):
        return ConflictItem(
            safe,
            ConflictKind.MANUAL_MARKDOWN,
            ConflictAction.MANUAL_SELECT,
            False,
            "Markdown 可能包含人工编辑，确认前不自动覆盖任一侧",
        )
    return ConflictItem(
        safe,
        ConflictKind.OPAQUE_BINARY,
        ConflictAction.PRESERVE_BOTH,
        False,
        "无法安全推断二进制或未知格式的合并语义，先保留双方副本",
    )


def explain_conflict(state: SyncState, paths: Iterable[str] = ()) -> ConflictExplanation:
    """Return a stable, non-mutating explanation for a protected sync state."""
    items = tuple(
        sorted((classify_conflict_path(path) for path in paths), key=lambda item: item.path)
    )
    return ConflictExplanation(state=state, items=items)


def plan_conflict_recovery(state: SyncState, paths: Iterable[str] = ()) -> ConflictRecoveryPlan:
    """Build a deterministic, non-mutating recovery plan for the given paths."""
    explanation = explain_conflict(state, paths)
    return ConflictRecoveryPlan(state=explanation.state, items=explanation.items)


__all__ = [
    "ConflictAction",
    "ConflictExplanation",
    "ConflictItem",
    "ConflictKind",
    "ConflictRecoveryPlan",
    "RecoveryStage",
    "classify_conflict_path",
    "explain_conflict",
    "plan_conflict_recovery",
]
