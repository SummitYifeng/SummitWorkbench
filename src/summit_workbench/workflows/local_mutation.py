"""本地业务写入的单一事务入口。

调用方把纯本地 mutation 作为回调传入；回调返回业务结果和本次实际可能触碰的路径。
工作区锁覆盖 mutation 与路径收集；中断时保留可检查的文件清单，不自动覆盖文件。
网络、LLM 和外部副作用必须在调用本 helper 之前完成。
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from summit_workbench.config.locking import workspace_lock
from summit_workbench.domain.workspace import Compatibility
from summit_workbench.repositories.local_mutation_journal import (
    finish_mutation_record,
    interrupted_mutations,
    start_mutation_record,
)


@dataclass(frozen=True)
class LocalMutationOutcome[T]:
    """纯本地 mutation 的业务返回值和可能变更的路径。"""

    business_return: T
    changed_paths: Sequence[Path | str]
    activity_report: Mapping[str, object] | None = None


@dataclass(frozen=True)
class LocalMutationResult[T]:
    """一次本地业务操作的稳定 operation id 与结果。"""

    operation_id: str
    business_return: T
    changed_paths: tuple[Path, ...]
    commit_result: None = None
    activity_report: Mapping[str, object] | None = None


class MutationBlocked(RuntimeError):
    """Workspace compatibility or profile switching blocks a local write."""


class MutationInvariantError(RuntimeError):
    """A local mutation violated its declared write contract."""

    def __init__(
        self,
        message: str,
        *,
        committed: bool = False,
        commit_sha: str | None = None,
        paths: Sequence[str] = (),
    ) -> None:
        super().__init__(message)
        self.committed = committed
        self.commit_sha = commit_sha
        self.paths = tuple(paths)


def run_local_mutation[T](
    vault_dir: Path,
    action: str,
    mutation: Callable[[str], LocalMutationOutcome[T]],
    *,
    compatibility: Compatibility | None = None,
    lock_root: Path | None = None,
    lock_timeout: float | None = 2.0,
) -> LocalMutationResult[T]:
    """Run a local mutation under the per-workspace process lock.

    ``mutation`` receives a stable operation ID. It writes through the repository's atomic
    primitives; no work-library Git operation is part of this transaction.
    """
    if compatibility in {Compatibility.READ_ONLY_UPGRADE_REQUIRED, Compatibility.CANNOT_OPEN}:
        raise MutationBlocked("workspace compatibility gate 拒绝共享 vault 写入")
    operation_id = str(uuid4())
    # Web/manual mutations fail visibly after a short wait and leave the
    # caller's draft intact; background workers can pass their existing longer
    # policy explicitly.
    with workspace_lock(lock_root or vault_dir.parent, timeout=lock_timeout):
        before = _file_snapshot(vault_dir)
        interrupted_mutations(vault_dir, before)
        journal_path = start_mutation_record(vault_dir, operation_id, action, before)
        try:
            outcome = mutation(operation_id)
        except BaseException:
            after_failed = _file_snapshot(vault_dir)
            changed_failed = sorted(
                path
                for path in before.keys() | after_failed.keys()
                if before.get(path) != after_failed.get(path)
            )
            finish_mutation_record(
                vault_dir,
                operation_id,
                journal_path,
                state="interrupted" if changed_failed else "failed",
                changed_paths=changed_failed,
                after=after_failed,
            )
            raise
        candidate_paths = list(outcome.changed_paths)
        if isinstance(outcome.business_return, Path):
            candidate_paths.insert(0, outcome.business_return)
        changed_paths = tuple(dict.fromkeys(Path(path) for path in candidate_paths))
        after = _file_snapshot(vault_dir)
        actual = {
            path for path in before.keys() | after.keys() if before.get(path) != after.get(path)
        }
        declared: set[str] = set()
        for path in changed_paths:
            try:
                declared.add(path.resolve().relative_to(vault_dir.resolve()).as_posix())
            except ValueError:
                raise MutationInvariantError(
                    f"本地 mutation 写入工作库之外的路径：{path}", paths=(str(path),)
                ) from None
        missing = sorted(actual - declared)
        if missing:
            finish_mutation_record(
                vault_dir,
                operation_id,
                journal_path,
                state="interrupted",
                changed_paths=sorted(actual),
                after=after,
            )
            raise MutationInvariantError(
                f"本地 mutation 未报告全部写入：{action}；未列路径：{', '.join(missing)}",
                paths=missing,
            )
        finish_mutation_record(
            vault_dir,
            operation_id,
            journal_path,
            state="completed",
            changed_paths=sorted(actual),
            after=after,
        )
    return LocalMutationResult(
        operation_id=operation_id,
        business_return=outcome.business_return,
        changed_paths=changed_paths,
        activity_report=outcome.activity_report,
    )


def _file_snapshot(root: Path) -> dict[str, str]:
    """Hash portable regular files without inspecting Git metadata."""
    if not root.exists():
        return {}
    result: dict[str, str] = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if (
            ".git" in relative.parts
            or (
                len(relative.parts) >= 2
                and relative.parts[:2] == (".summit-workbench", "operations")
            )
            or not path.is_file()
        ):
            continue
        try:
            result[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            result[relative.as_posix()] = "<unreadable>"
    return result
