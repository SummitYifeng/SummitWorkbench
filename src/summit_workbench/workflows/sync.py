"""work-sync：批量安全同步 ``WORK_ROOT`` 下的 Git 仓库（PRD M0-9 / NFR-3）。

规则：
- git remote 是唯一真源；只做 ``fetch`` + ``merge --ff-only`` + ``push``。
- **不做破坏性修复**：dirty 仓库不动其工作树（只 fetch，不合并）；分叉/冲突只报告不 force。
- 单仓库失败不掩盖其它仓库（逐仓库隔离聚合）。
- 幂等：全部已同步时重复运行只报告 up-to-date，无副作用。
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from summit_workbench.repositories.git import GitError, GitRepo


class SyncStatus(StrEnum):
    UP_TO_DATE = "up-to-date"
    PULLED = "pulled"
    PUSHED = "pushed"
    PULLED_AND_PUSHED = "pulled+pushed"
    DIRTY = "dirty"  # 有未提交改动：已 fetch、可能已 push 提交，但不动工作树
    NO_REMOTE = "no-remote"
    NO_UPSTREAM = "no-upstream"
    DIVERGED = "diverged"  # 与 upstream 分叉，需人工处理，不 force
    FETCH_FAILED = "fetch-failed"
    PUSH_FAILED = "push-failed"

    @property
    def is_problem(self) -> bool:
        return self in {
            SyncStatus.NO_REMOTE,
            SyncStatus.NO_UPSTREAM,
            SyncStatus.DIVERGED,
            SyncStatus.FETCH_FAILED,
            SyncStatus.PUSH_FAILED,
        }


@dataclass
class RepoSyncResult:
    name: str
    status: SyncStatus
    detail: str = ""
    notes: list[str] = field(default_factory=list)


def discover_repos(work_root: Path) -> list[Path]:
    """``WORK_ROOT`` 下直接子目录中是 Git 仓库的那些（含 ``_vault``），按名排序。"""
    if not work_root.is_dir():
        return []
    return sorted(
        (p for p in work_root.iterdir() if p.is_dir() and (p / ".git").exists()),
        key=lambda p: p.name,
    )


def sync_repo(path: Path) -> RepoSyncResult:
    """安全同步单个仓库。任何异常都转成可见状态，绝不抛出。"""
    repo = GitRepo(path)
    name = path.name
    notes: list[str] = []

    if not repo.has_remote():
        return RepoSyncResult(name, SyncStatus.NO_REMOTE, "没有 origin 远端")

    try:
        repo.fetch()
    except GitError as exc:
        return RepoSyncResult(name, SyncStatus.FETCH_FAILED, exc.stderr or str(exc))

    if not repo.has_upstream():
        return RepoSyncResult(
            name, SyncStatus.NO_UPSTREAM, f"分支 {repo.current_branch()} 未设置 upstream"
        )

    dirty = repo.is_dirty()
    ab = repo.ahead_behind()

    pulled = pushed = False

    # 落后且工作树干净 → 快进；dirty 时不动工作树
    if ab.behind > 0:
        if dirty:
            notes.append(f"落后 {ab.behind} 但工作树有改动，跳过合并")
        else:
            try:
                repo.ff_merge_upstream()
                pulled = True
                notes.append(f"已快进 {ab.behind} 个提交")
            except GitError as exc:
                return RepoSyncResult(name, SyncStatus.DIVERGED, exc.stderr or str(exc))

    # 领先 → 推送（只推提交，不涉及工作树，dirty 也安全）
    if ab.ahead > 0:
        try:
            repo.push()
            pushed = True
            notes.append(f"已推送 {ab.ahead} 个提交")
        except GitError as exc:
            return RepoSyncResult(name, SyncStatus.PUSH_FAILED, exc.stderr or str(exc), notes)

    return RepoSyncResult(name, _summarize(dirty, pulled, pushed), notes=notes)


def _summarize(dirty: bool, pulled: bool, pushed: bool) -> SyncStatus:
    if dirty:
        return SyncStatus.DIRTY
    if pulled and pushed:
        return SyncStatus.PULLED_AND_PUSHED
    if pulled:
        return SyncStatus.PULLED
    if pushed:
        return SyncStatus.PUSHED
    return SyncStatus.UP_TO_DATE


def iter_sync(work_root: Path) -> Iterator[RepoSyncResult]:
    for path in discover_repos(work_root):
        yield sync_repo(path)


def sync_work_root(work_root: Path) -> list[RepoSyncResult]:
    return list(iter_sync(work_root))
