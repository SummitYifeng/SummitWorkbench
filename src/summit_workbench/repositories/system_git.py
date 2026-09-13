"""system git 后端（development 默认）：subprocess 调用 ``git``。

从旧 ``GitRepo`` 逐字提取，行为不变（NFR-3）；新增契约要求的 init/clone/add_remote
与 typed error 分类（仍派生 :class:`GitError`，上层可统一捕获）。
本后端供开发/CLI 使用；生产（打包 App）后端是 :mod:`.dulwich_git`，绝不调用系统 git。
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from summit_workbench.repositories.git_backend import (
    AheadBehind,
    CommitIdentity,
    CommitMetadata,
    GitAuthError,
    GitConflictError,
    GitError,
    GitInvalidRevision,
    GitNonFastForward,
    GitRemoteUnavailable,
    GitTlsError,
    default_identity,
)


def _classify(operation: str, message: str, stderr: str) -> GitError:
    """按 stderr 特征把失败分类成 typed error（找不到特征则退回通用 GitError）。"""
    text = stderr.casefold()
    if "non-fast-forward" in text or "rejected" in text or "fetch first" in text:
        return GitNonFastForward(message, stderr=stderr)
    if "conflict" in text or "could not revert" in text:
        return GitConflictError(message, stderr=stderr)
    if any(
        marker in text
        for marker in (
            "authentication failed",
            "invalid username",
            "could not read username",
            "could not read password",
            "403",
            "401",
        )
    ):
        return GitAuthError(message, stderr=stderr)
    if "ssl" in text or "certificate" in text or "tls" in text:
        return GitTlsError(message, stderr=stderr)
    if any(
        marker in text
        for marker in (
            "repository not found",
            "does not appear to be a git repository",
            "could not read from remote",
            "unable to access",
            "not a git repository",
        )
    ):
        return GitRemoteUnavailable(message, stderr=stderr)
    if operation in {"resolve_commit", "commit_subject", "commit_parent_count", "show_patch"}:
        return GitInvalidRevision(message, stderr=stderr)
    return GitError(message, stderr=stderr)


class SystemGitBackend:
    """把 :class:`~summit_workbench.repositories.git_backend.GitBackend` 契约映射到 ``git`` CLI。"""

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def _env_for(self, author: CommitIdentity | None) -> dict[str, str] | None:
        if author is None:
            return None
        return {
            "GIT_AUTHOR_NAME": author.name,
            "GIT_AUTHOR_EMAIL": author.email,
            "GIT_COMMITTER_NAME": author.name,
            "GIT_COMMITTER_EMAIL": author.email,
        }

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self._path), *args],
            capture_output=True,
            text=True,
            check=False,
        )

    def _must(self, *args: str, env: dict[str, str] | None = None) -> str:
        cp = subprocess.run(
            ["git", "-C", str(self._path), *args],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        if cp.returncode != 0:
            raise _classify(args[0], f"git {' '.join(args)} 失败", cp.stderr)
        return cp.stdout.strip()

    # ---- repo detect / init / clone / remote ----

    def is_git_repo(self) -> bool:
        return (self._path / ".git").exists()

    def init(self, *, bare: bool = False, default_branch: str = "main") -> None:
        args = ["git", "init", "--quiet", f"--initial-branch={default_branch}"]
        if bare:
            args.append("--bare")
        args.append(str(self._path))
        subprocess.run(args, capture_output=True, text=True, check=False)

    def clone(self, url: str, destination: Path) -> None:
        cp = subprocess.run(
            ["git", "clone", "--quiet", url, str(destination)],
            capture_output=True,
            text=True,
            check=False,
        )
        if cp.returncode != 0:
            raise _classify("clone", f"git clone {url} 失败", cp.stderr)

    def has_remote(self, name: str = "origin") -> bool:
        return name in self._run("remote").stdout.split()

    def remote_url(self, name: str = "origin") -> str | None:
        cp = self._run("remote", "get-url", name)
        return cp.stdout.strip() or None

    def set_remote_url(self, url: str, name: str = "origin") -> None:
        self._must("remote", "set-url", name, url)

    def add_remote(self, name: str, url: str) -> None:
        self._must("remote", "add", name, url)

    def current_branch(self) -> str:
        return self._must("rev-parse", "--abbrev-ref", "HEAD")

    def head_revision(self) -> str:
        return self._must("rev-parse", "HEAD")

    def has_upstream(self) -> bool:
        return (
            self._run("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").returncode == 0
        )

    def upstream_revision(self) -> str:
        return self._must("rev-parse", "--verify", "@{u}")

    # ---- 工作树 / 暂存区 ----

    def is_dirty(self) -> bool:
        return bool(self._must("status", "--porcelain"))

    def is_dirty_paths(self, rel_paths: list[str]) -> bool:
        if not rel_paths:
            return False
        cp = self._run("status", "--porcelain", "--", *rel_paths)
        return bool(cp.stdout.strip())

    def staged_paths(self) -> list[str]:
        cp = self._run("status", "--porcelain=v1", "-z", "--")
        if cp.returncode != 0:
            raise _classify("staged_paths", "读取暂存路径失败", cp.stderr)
        paths: set[str] = set()
        for entry in cp.stdout.split("\0"):
            if len(entry) < 3 or entry[0] in "?!" or (entry[0] == " " and entry[1] != "A"):
                continue
            paths.add(entry[3:])
        return sorted(paths)

    def has_staged_changes(self, paths: list[str] | None = None) -> bool:
        args = ["diff", "--cached", "--quiet"]
        if paths:
            args.extend(["--", *paths])
        return self._run(*args).returncode != 0

    # ---- 写操作 ----

    def add(self, paths: list[str]) -> None:
        if not paths:
            return
        cp = self._run("add", "--", *paths)
        if cp.returncode != 0:
            raise _classify("add", "git add 失败", cp.stderr)

    def commit(self, message: str, *, author: CommitIdentity | None = None) -> None:
        cp = subprocess.run(
            ["git", "-C", str(self._path), "commit", "-m", message],
            capture_output=True,
            text=True,
            check=False,
            env=self._env_for(author),
        )
        if cp.returncode != 0:
            raise _classify("commit", "git commit 失败", cp.stderr)

    def commit_merge(
        self,
        message: str,
        merge_parent: str,
        *,
        author: CommitIdentity | None = None,
    ) -> None:
        """Create a normal merge commit from the current index without force moves."""
        current = self.head_revision()
        parent = self.resolve_commit(merge_parent)
        if current == parent:
            raise GitError("merge parent 不能与当前 HEAD 相同")
        tree = self._must("write-tree")
        env = os.environ.copy()
        env.update(self._env_for(author or default_identity()) or {})
        cp = subprocess.run(
            [
                "git",
                "-C",
                str(self._path),
                "commit-tree",
                tree,
                "-p",
                current,
                "-p",
                parent,
            ],
            input=message + "\n",
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        if cp.returncode != 0:
            raise _classify("commit_merge", "git merge commit 失败", cp.stderr)
        new_revision = cp.stdout.strip()
        branch_ref = self._must("symbolic-ref", "HEAD")
        update = self._run("update-ref", branch_ref, new_revision, current)
        if update.returncode != 0:
            raise _classify("commit_merge", "更新 merge commit 引用失败", update.stderr)

    def fetch(self, remote: str = "origin") -> None:
        cp = self._run("fetch", "--quiet", remote)
        if cp.returncode != 0:
            raise _classify("fetch", f"fetch {remote} 失败", cp.stderr)

    def ahead_behind(self) -> AheadBehind:
        out = self._must("rev-list", "--left-right", "--count", "@{u}...HEAD")
        behind_str, ahead_str = out.split()
        return AheadBehind(ahead=int(ahead_str), behind=int(behind_str))

    def pending_wb_commits(self) -> int:
        args = ["log", "--format=%s", "HEAD"]
        if self.has_upstream():
            args.extend(["--not", "@{u}"])
        return sum(line.startswith("wb:") for line in self._must(*args).splitlines())

    def ff_merge_upstream(self) -> None:
        cp = self._run("merge", "--ff-only", "@{u}")
        if cp.returncode != 0:
            raise _classify("ff_merge_upstream", "无法快进合并（存在分叉，需人工处理）", cp.stderr)

    def push(self, remote: str = "origin") -> None:
        remote_url = self.remote_url(remote)
        if remote_url and "://" not in remote_url and not Path(remote_url).is_dir():
            raise GitRemoteUnavailable(f"push {remote} 失败", stderr="远端仓库不存在")
        cp = self._run("push", remote, "HEAD")
        if cp.returncode != 0:
            raise _classify("push", f"push {remote} 失败", cp.stderr)

    def revert(self, sha: str) -> None:
        cp = subprocess.run(
            ["git", "-C", str(self._path), "revert", "--no-edit", sha],
            capture_output=True,
            text=True,
            check=False,
            env=self._env_for(CommitIdentity("SummitWorkbench", "wb@local")),
        )
        if cp.returncode != 0:
            self._run("revert", "--abort")
            raise _classify("revert", f"git revert {sha} 失败", cp.stderr)

    # ---- 读提交 / 历史 ----

    def resolve_commit(self, sha: str) -> str:
        return self._must("rev-parse", "--verify", "--end-of-options", f"{sha}^{{commit}}")

    def commit_subject(self, sha: str) -> str:
        return self._must("show", "-s", "--format=%s", sha, "--")

    def commit_parent_count(self, sha: str) -> int:
        parents = self._must("rev-list", "--parents", "-n", "1", sha, "--").split()
        if not parents:
            raise GitError(f"无法读取提交 {sha} 的父节点")
        return len(parents) - 1

    def validate_commit(self, sha: str) -> tuple[str, int]:
        resolved = self.resolve_commit(sha)
        return self.commit_subject(resolved), self.commit_parent_count(resolved)

    def files_changed_by(self, sha: str) -> list[str]:
        cp = self._run("show", "--name-only", "--pretty=format:", sha, "--")
        if cp.returncode != 0:
            raise _classify("files_changed_by", f"git show {sha} 失败", cp.stderr)
        return sorted({line for line in cp.stdout.splitlines() if line.strip()})

    def merge_base(self, left: str, right: str) -> str:
        return self._must("merge-base", left, right)

    def files_changed_between(self, base: str, head: str) -> list[str]:
        cp = self._run("diff", "--name-only", base, head, "--")
        if cp.returncode != 0:
            raise _classify("files_changed_between", "读取提交间变更路径失败", cp.stderr)
        return sorted({line for line in cp.stdout.splitlines() if line.strip()})

    def commit_metadata(self, sha: str) -> CommitMetadata:
        cp = self._run("show", "-s", "--format=%H%x09%aI%x09%s", sha, "--")
        if cp.returncode != 0:
            raise _classify("commit_metadata", "读取提交元数据失败", cp.stderr)
        parts = cp.stdout.rstrip("\n").split("\t", 2)
        if len(parts) != 3:
            raise GitError("提交元数据格式无效")
        return CommitMetadata(revision=parts[0], authored_at=parts[1], subject=parts[2])

    def read_file_at(self, revision: str, path: str) -> bytes | None:
        cp = subprocess.run(
            ["git", "-C", str(self._path), "cat-file", "blob", f"{revision}:{path}"],
            capture_output=True,
            check=False,
        )
        if cp.returncode == 0:
            return cp.stdout
        if cp.returncode == 128:
            return None
        raise _classify("read_file_at", "读取提交文件失败", cp.stderr.decode("utf-8", "replace"))

    def log_grep(self, pattern: str, limit: int) -> list[tuple[str, str, str]]:
        cp = self._run("log", f"--grep={pattern}", f"-n{limit}", "--pretty=%H%x09%aI%x09%s", "--")
        if cp.returncode != 0:
            raise _classify("log_grep", "git log --grep 失败", cp.stderr)
        rows: list[tuple[str, str, str]] = []
        for line in cp.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) >= 3:
                rows.append((parts[0], parts[1], "\t".join(parts[2:])))
        return rows

    def show_patch(self, sha: str) -> str:
        cp = self._run("show", "--stat", "--patch", sha, "--")
        if cp.returncode != 0:
            raise _classify("show_patch", f"git show {sha} 失败", cp.stderr)
        return cp.stdout

    def commits_between(self, since_iso: str, until_iso: str) -> list[tuple[str, str]]:
        cp = self._run(
            "log", f"--since={since_iso} 00:00", f"--until={until_iso} 23:59", "--pretty=%h\t%s"
        )
        if cp.returncode != 0:
            raise _classify("commits_between", "git log 失败", cp.stderr)
        commits: list[tuple[str, str]] = []
        for line in cp.stdout.splitlines():
            if "\t" in line:
                sha, subject = line.split("\t", 1)
                commits.append((sha, subject))
        return commits
