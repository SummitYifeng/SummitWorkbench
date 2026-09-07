"""本地业务写入与 ``wb`` 自动提交的单一事务入口（P0-02）。

调用方把纯本地 mutation 作为回调传入；回调返回业务结果和本次实际可能触碰的路径。
工作区锁覆盖 mutation、路径收集与自动提交，底层 repository 自己的同线程锁可以安全重入。
网络、LLM 和外部副作用必须在调用本 helper 之前完成。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from summit_workbench.config.locking import workspace_lock
from summit_workbench.domain.sync import SyncSnapshot, SyncState
from summit_workbench.domain.workspace import Compatibility
from summit_workbench.repositories.autocommit import CommitResult, commit_paths
from summit_workbench.repositories.git_backend import CommitIdentity


@dataclass(frozen=True)
class LocalMutationOutcome[T]:
    """纯本地 mutation 的业务返回值和可能变更的路径。"""

    business_return: T
    changed_paths: Sequence[Path | str]
    activity_report: Mapping[str, object] | None = None


@dataclass(frozen=True)
class LocalMutationResult[T]:
    """一次本地业务操作的稳定 operation id、结果和自动提交结果。"""

    operation_id: str
    business_return: T
    changed_paths: tuple[Path, ...]
    commit_result: CommitResult
    activity_report: Mapping[str, object] | None = None


class MutationBlocked(RuntimeError):
    """共享 vault 写入被统一的 compatibility/sync 保护门拒绝。"""


def run_local_mutation[T](
    vault_dir: Path,
    action: str,
    mutation: Callable[[str], LocalMutationOutcome[T]],
    *,
    sync_snapshot: SyncSnapshot | None = None,
    compatibility: Compatibility | None = None,
    backend_kind: str | None = None,
    author: CommitIdentity | None = None,
    push_after_commit: Callable[[], object] | None = None,
) -> LocalMutationResult[T]:
    """在同一工作区临界区完成本地 mutation 与自动提交。

    ``mutation`` 接收本次操作的稳定 id；若 mutation 抛错，异常原样向上传递且不会调用
    ``commit_paths``。Git 非仓库或无变化等提交状态不会回滚已经成功的本地业务写入。
    """
    if compatibility in {Compatibility.READ_ONLY_UPGRADE_REQUIRED, Compatibility.CANNOT_OPEN}:
        raise MutationBlocked("workspace compatibility gate 拒绝共享 vault 写入")
    if sync_snapshot is not None and sync_snapshot.state in {
        SyncState.DIVERGED_PROTECTED,
        SyncState.DIRTY_PROTECTED,
    }:
        raise MutationBlocked(
            f"workspace 处于 {sync_snapshot.state.value}，修改共享 vault 的操作已被阻止"
        )
    operation_id = str(uuid4())
    with workspace_lock(vault_dir.parent):
        outcome = mutation(operation_id)
        # The primary business result is often the newly-created legacy file.  Keep it
        # in the explicit commit set even if a caller only reports auxiliary paths
        # (for example, a dual-write event path).  This preserves the transaction
        # invariant that the user-visible source and its projections share one commit.
        candidate_paths = list(outcome.changed_paths)
        if isinstance(outcome.business_return, (Path, str)):
            candidate_paths.insert(0, outcome.business_return)
        changed_paths = tuple(dict.fromkeys(Path(path) for path in candidate_paths))
        commit_result = commit_paths(
            vault_dir,
            list(changed_paths),
            message=f"wb: {action} [{operation_id}]",
            backend_kind=backend_kind,
            author=author,
        )
    result = LocalMutationResult(
        operation_id=operation_id,
        business_return=outcome.business_return,
        changed_paths=changed_paths,
        commit_result=commit_result,
        activity_report=outcome.activity_report,
    )
    if push_after_commit is not None and commit_result.status.value == "committed":
        # 网络调用明确位于 workspace 文件锁外。
        push_after_commit()
    return result
