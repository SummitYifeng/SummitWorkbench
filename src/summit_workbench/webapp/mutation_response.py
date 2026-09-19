"""Web mutation 的公共响应辅助函数。"""

from __future__ import annotations

from summit_workbench.repositories.autocommit import CommitResult, CommitStatus
from summit_workbench.workflows.local_mutation import LocalMutationResult


def _commit_note(result: CommitResult) -> str:
    if result.status in {
        CommitStatus.FAILED,
        CommitStatus.BUSY,
        CommitStatus.INDEX_NOT_CLEAN,
    }:
        return f"（git 留痕失败：{result.detail or result.status.value}）"
    return ""


def _mutation_fields[T](result: LocalMutationResult[T]) -> dict[str, object]:
    """把本地事务的 operation id 与可见提交状态加入 API 响应。"""
    fields: dict[str, object] = {
        "operation_id": result.operation_id,
        "commit": result.commit_result.as_dict(),
    }
    if result.activity_report is not None:
        fields["thread_activity_consistency"] = dict(result.activity_report)
    if result.push_note:
        # WB_NO_AUTO_PUSH 跳过后置推送：显式暴露，绝不伪装成一次成功的同步。
        fields["auto_push"] = {"skipped": True, "note": result.push_note}
    return fields


__all__ = ["_commit_note", "_mutation_fields"]
