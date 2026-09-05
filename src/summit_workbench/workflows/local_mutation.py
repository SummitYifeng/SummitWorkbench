"""本地业务写入与 ``wb`` 自动提交的单一事务入口（P0-02）。

调用方把纯本地 mutation 作为回调传入；回调返回业务结果和本次实际可能触碰的路径。
工作区锁覆盖 mutation、路径收集与自动提交，底层 repository 自己的同线程锁可以安全重入。
网络、LLM 和外部副作用必须在调用本 helper 之前完成。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from summit_workbench.config.locking import workspace_lock
from summit_workbench.repositories.autocommit import CommitResult, commit_paths


@dataclass(frozen=True)
class LocalMutationOutcome[T]:
    """纯本地 mutation 的业务返回值和可能变更的路径。"""

    business_return: T
    changed_paths: Sequence[Path | str]


@dataclass(frozen=True)
class LocalMutationResult[T]:
    """一次本地业务操作的稳定 operation id、结果和自动提交结果。"""

    operation_id: str
    business_return: T
    changed_paths: tuple[Path, ...]
    commit_result: CommitResult


def run_local_mutation[T](
    vault_dir: Path,
    action: str,
    mutation: Callable[[str], LocalMutationOutcome[T]],
) -> LocalMutationResult[T]:
    """在同一工作区临界区完成本地 mutation 与自动提交。

    ``mutation`` 接收本次操作的稳定 id；若 mutation 抛错，异常原样向上传递且不会调用
    ``commit_paths``。Git 非仓库或无变化等提交状态不会回滚已经成功的本地业务写入。
    """
    operation_id = str(uuid4())
    with workspace_lock(vault_dir.parent):
        outcome = mutation(operation_id)
        changed_paths = tuple(Path(path) for path in outcome.changed_paths)
        commit_result = commit_paths(
            vault_dir,
            list(changed_paths),
            message=f"wb: {action} [{operation_id}]",
        )
    return LocalMutationResult(
        operation_id=operation_id,
        business_return=outcome.business_return,
        changed_paths=changed_paths,
        commit_result=commit_result,
    )
