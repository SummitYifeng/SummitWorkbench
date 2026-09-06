"""把简报生成物提交/推送到 vault 仓库（M2-7 的 git 环节）。

**安全边界**：只 ``git add`` 简报自己写的文件（当日笔记 + 快照），绝不 ``add -A``，
因此用户在 vault 里的其它未提交改动不受影响，尊重「vault 由 ``wb sync``/用户提交」的既有约定。
幂等：内容未变时暂存区为空 → 跳过提交；落后 upstream 时不 push（不制造分叉，交给 ``wb sync``）。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from summit_workbench.config.locking import LockBusy, workspace_lock
from summit_workbench.repositories.git import GitError, GitRepo
from summit_workbench.repositories.git_backend import CommitIdentity


class PublishStatus(StrEnum):
    COMMITTED = "committed"
    COMMITTED_AND_PUSHED = "committed+pushed"
    NOTHING_TO_COMMIT = "nothing-to-commit"
    NOT_GIT = "not-git"
    NO_UPSTREAM = "committed(no-upstream)"
    BEHIND = "committed(behind-upstream)"
    PUSH_FAILED = "push-failed"
    COMMIT_FAILED = "commit-failed"
    BUSY = "busy(locked)"  # 工作区被另一 wb 任务占用，本次未提交（LHF #1）


@dataclass(frozen=True)
class PublishResult:
    status: PublishStatus
    detail: str = ""


def publish_brief(
    vault_dir: Path,
    paths: list[Path],
    *,
    message: str,
    push: bool,
    backend_kind: str | None = None,
    workspace_id: str | None = None,
    username: str | None = None,
    author: CommitIdentity | None = None,
) -> PublishResult:
    """提交（可选推送）简报文件。任何 git 失败转成可见状态，不抛出。

    整个 ``add → commit → (push)`` 序列在工作区锁内进行，与 ``wb sync`` 的
    ``fetch/ff-merge/push`` 互斥，避免并发触发源交错操作同一仓库（LHF #1）。
    锁被占用时不阻塞很久，直接返回 :attr:`PublishStatus.BUSY` 让上层可见。
    """
    repo = GitRepo(
        vault_dir,
        backend_kind=backend_kind,
        workspace_id=workspace_id,
        username=username,
    )
    if not repo.is_git_repo():
        return PublishResult(PublishStatus.NOT_GIT, f"{vault_dir} 不是 git 仓库")

    rel = [str(p.relative_to(vault_dir)) if p.is_absolute() else str(p) for p in paths]
    try:
        with workspace_lock(vault_dir.parent):
            try:
                repo.add(rel)
                if not repo.has_staged_changes():
                    return PublishResult(PublishStatus.NOTHING_TO_COMMIT, "内容未变，无需提交")
                repo.commit(message, author=author)
            except GitError as exc:
                return PublishResult(PublishStatus.COMMIT_FAILED, exc.stderr or str(exc))

            if not push:
                return PublishResult(PublishStatus.COMMITTED)
            if not repo.has_upstream():
                return PublishResult(
                    PublishStatus.NO_UPSTREAM, "已提交，但分支未设 upstream，未推送"
                )

            try:
                if repo.ahead_behind().behind > 0:
                    return PublishResult(
                        PublishStatus.BEHIND, "已提交，但落后 upstream，交由 wb sync 合并"
                    )
                repo.push()
            except GitError as exc:
                return PublishResult(PublishStatus.PUSH_FAILED, exc.stderr or str(exc))
            return PublishResult(PublishStatus.COMMITTED_AND_PUSHED)
    except LockBusy as exc:
        return PublishResult(PublishStatus.BUSY, str(exc))
