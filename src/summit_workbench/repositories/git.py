"""GitRepo 门面（P0-09）：在系统 git 与 dulwich 后端之间转发，API 保持兼容。

- :class:`GitError` / :class:`AheadBehind` 与既有方法签名全部保留（上层无感）。
- 后端选择：默认 ``system``（development/CLI，行为与 v0.4.1 完全一致）；环境变量
  ``WB_GIT_BACKEND=dulwich`` 显式启用生产后端（纯 Python，不依赖系统 git）。
- conformance suite（tests/unit/test_git_backends.py）直接验证两个后端对同一临时
  bare remote 的行为一致性；本文件是业务调用方的稳定入口。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from summit_workbench.repositories.git_backend import (
    AheadBehind,
    CommitIdentity,
    CommitMetadata,
    GitBackend,
    backend_kind,
)

# 显式再导出：历史消费方（sync/autocommit/publish/collect/project_scan）从本模块取 GitError。
from summit_workbench.repositories.git_backend import GitError as GitError  # noqa: F401, PLC0414


def _new_backend(
    path: Path,
    kind: str | None = None,
    *,
    workspace_id: str | None = None,
    username: str | None = None,
    credential_resolver: Callable[[str, str, str], Any] | None = None,
) -> GitBackend:
    chosen = kind or backend_kind()
    if chosen == "dulwich":
        from summit_workbench.repositories.dulwich_git import DulwichGitBackend

        return DulwichGitBackend(
            path,
            workspace_id=workspace_id,
            username=username,
            credential_resolver=credential_resolver,
        )
    from summit_workbench.repositories.system_git import SystemGitBackend

    return SystemGitBackend(path)


class GitRepo:
    """单个 Git 仓库的只读/安全写操作门面（无破坏性动作）。

    **绝不做破坏性动作**：没有 reset/stash/force/rebase；写操作仅限 ``fetch``、
    ``merge --ff-only``、``add <指定路径>``、``commit`` 和 ``push``。``add`` 只暂存
    **显式列出**的路径（绝不 ``add -A``），因此提交简报生成物不会波及用户在 vault
    里的其它改动。任何失败都抛 :class:`GitError`，由上层聚合为可见状态（NFR-6）。
    """

    def __init__(
        self,
        path: Path,
        *,
        backend_kind: str | None = None,
        backend: GitBackend | None = None,
        workspace_id: str | None = None,
        username: str | None = None,
        credential_resolver: Callable[[str, str, str], Any] | None = None,
    ) -> None:
        self.path = path
        if backend is not None:
            if backend.path != path:
                raise ValueError("注入的 Git backend 路径必须与 GitRepo 一致")
            self._backend = backend
        else:
            if backend_kind is not None and backend_kind not in ("system", "dulwich"):
                raise ValueError(f"未知 git backend：{backend_kind!r}")
            self._backend = _new_backend(
                path,
                backend_kind,
                workspace_id=workspace_id,
                username=username,
                credential_resolver=credential_resolver,
            )

    @property
    def backend(self) -> GitBackend:
        """返回本次调用显式选择/注入的 backend（供 runtime wiring 与测试）。"""
        return self._backend

    def is_git_repo(self) -> bool:
        return self._backend.is_git_repo()

    def has_remote(self, name: str = "origin") -> bool:
        return self._backend.has_remote(name)

    def remote_url(self, name: str = "origin") -> str | None:
        return self._backend.remote_url(name)

    def set_remote_url(self, url: str, name: str = "origin") -> None:
        self._backend.set_remote_url(url, name)

    def add_remote(self, name: str, url: str) -> None:
        """新增 remote（G2 首次发布用；调用方负责失败回滚）。"""
        self._backend.add_remote(name, url)

    def remove_remote(self, name: str = "origin") -> None:
        """删除 remote 配置段（幂等；不碰 refs 与工作树）。"""
        self._backend.remove_remote(name)

    def set_upstream(self, remote: str = "origin", branch: str | None = None) -> None:
        """写 branch.<name>.remote/merge（等价 ``git push -u``），只改本机配置。"""
        self._backend.set_upstream(remote, branch)

    def current_branch(self) -> str:
        return self._backend.current_branch()

    def head_revision(self) -> str:
        """返回当前 HEAD 的完整 revision（备份审计使用，不修改仓库）。"""
        return self._backend.head_revision()

    def has_upstream(self) -> bool:
        return self._backend.has_upstream()

    def upstream_revision(self) -> str:
        return self._backend.upstream_revision()

    def is_dirty(self) -> bool:
        return self._backend.is_dirty()

    def is_dirty_paths(self, rel_paths: list[str]) -> bool:
        return self._backend.is_dirty_paths(rel_paths)

    def staged_paths(self) -> list[str]:
        return self._backend.staged_paths()

    def has_staged_changes(self, paths: list[str] | None = None) -> bool:
        return self._backend.has_staged_changes(paths)

    def fetch(self, remote: str = "origin") -> None:
        self._backend.fetch(remote)

    def ahead_behind(self) -> AheadBehind:
        return self._backend.ahead_behind()

    def pending_wb_commits(self) -> int:
        return self._backend.pending_wb_commits()

    def ff_merge_upstream(self) -> None:
        self._backend.ff_merge_upstream()

    def push(self, remote: str = "origin") -> None:
        self._backend.push(remote)

    def add(self, paths: list[str]) -> None:
        """只暂存显式列出的路径（相对仓库根）。绝不 ``add -A``，避免波及用户其它改动。"""
        self._backend.add(paths)

    def commit(self, message: str, *, author: CommitIdentity | None = None) -> None:
        """提交暂存区。无暂存内容时应由调用方先判 :meth:`has_staged_changes`（幂等）。"""
        self._backend.commit(message, author=author)

    def commit_merge(
        self,
        message: str,
        merge_parent: str,
        *,
        author: CommitIdentity | None = None,
    ) -> None:
        """Create a normal two-parent merge commit from the already prepared index."""
        self._backend.commit_merge(message, merge_parent, author=author)

    def resolve_commit(self, sha: str) -> str:
        return self._backend.resolve_commit(sha)

    def commit_subject(self, sha: str) -> str:
        return self._backend.commit_subject(sha)

    def commit_parent_count(self, sha: str) -> int:
        return self._backend.commit_parent_count(sha)

    def validate_commit(self, sha: str) -> tuple[str, int]:
        """返回 ``(规范 SHA 的主题, 父节点数)``，失败则抛 :class:`GitError`。"""
        return self._backend.validate_commit(sha)

    def files_changed_by(self, sha: str) -> list[str]:
        return self._backend.files_changed_by(sha)

    def merge_base(self, left: str, right: str) -> str:
        return self._backend.merge_base(left, right)

    def files_changed_between(self, base: str, head: str) -> list[str]:
        return self._backend.files_changed_between(base, head)

    def commit_metadata(self, sha: str) -> CommitMetadata:
        return self._backend.commit_metadata(sha)

    def read_file_at(self, revision: str, path: str) -> bytes | None:
        return self._backend.read_file_at(revision, path)

    def log_grep(self, pattern: str, limit: int) -> list[tuple[str, str, str]]:
        """grep 提交主题的最近提交，返回 ``(sha, ISO 时间, 主题)``（供 wb 撤销历史）。"""
        return self._backend.log_grep(pattern, limit)

    def show_patch(self, sha: str) -> str:
        return self._backend.show_patch(sha)

    def commits_between(self, since_iso: str, until_iso: str) -> list[tuple[str, str]]:
        return self._backend.commits_between(since_iso, until_iso)

    def revert(self, sha: str) -> None:
        """撤销某提交（生成一个新提交，类似 ``git revert --no-edit``）；冲突/失败抛错。"""
        self._backend.revert(sha)
