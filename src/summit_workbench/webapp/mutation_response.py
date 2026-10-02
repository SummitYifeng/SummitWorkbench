"""Web mutation 的公共响应辅助函数。"""

from __future__ import annotations

from summit_workbench.workflows.local_mutation import LocalMutationResult


def _commit_note(result: None = None) -> str:
    """Deprecated UI helper retained while old responses are being removed."""
    del result
    return ""


def _mutation_fields[T](result: LocalMutationResult[T]) -> dict[str, object]:
    """把本地事务的 operation id 与可见提交状态加入 API 响应。"""
    fields: dict[str, object] = {"operation_id": result.operation_id}
    if result.activity_report is not None:
        fields["thread_activity_consistency"] = dict(result.activity_report)
    return fields


__all__ = ["_commit_note", "_mutation_fields"]
