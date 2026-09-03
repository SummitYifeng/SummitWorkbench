"""单个 Git 仓库的只读/安全写操作封装（subprocess）。

**绝不做破坏性动作**：没有 reset/stash/force/rebase；写操作仅限 ``fetch``、
``merge --ff-only``、``add <指定路径>``、``commit`` 和 ``push``。``add`` 只暂存**显式列出**
的路径（绝不 ``add -A``），因此提交简报生成物不会波及用户在 vault 里的其它改动。
任何失败都抛 :class:`GitError`，由上层聚合为可见状态（NFR-6）。
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitError(RuntimeError):
    """git 命令失败。``stderr`` 保留首行摘要供审计。"""

    def __init__(self, message: str, *, stderr: str = "") -> None:
        super().__init__(message)
        self.stderr = stderr.strip().splitlines()[0] if stderr.strip() else ""


@dataclass(frozen=True)
class AheadBehind:
    ahead: int  # 本地领先 upstream 的提交数（可 push）
    behind: int  # 本地落后 upstream 的提交数（可 ff-pull）


class GitRepo:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.path), *args],
            capture_output=True,
            text=True,
            check=False,
        )

    def _must(self, *args: str) -> str:
        cp = self._run(*args)
        if cp.returncode != 0:
            raise GitError(f"git {' '.join(args)} 失败", stderr=cp.stderr)
        return cp.stdout.strip()

    def is_git_repo(self) -> bool:
        return (self.path / ".git").exists()

    def has_remote(self, name: str = "origin") -> bool:
        return name in self._run("remote").stdout.split()

    def current_branch(self) -> str:
        return self._must("rev-parse", "--abbrev-ref", "HEAD")

    def has_upstream(self) -> bool:
        return (
            self._run("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").returncode == 0
        )

    def is_dirty(self) -> bool:
        return bool(self._must("status", "--porcelain"))

    def fetch(self, remote: str = "origin") -> None:
        cp = self._run("fetch", "--quiet", remote)
        if cp.returncode != 0:
            raise GitError(f"fetch {remote} 失败", stderr=cp.stderr)

    def ahead_behind(self) -> AheadBehind:
        # 输出 "behind\tahead"
        out = self._must("rev-list", "--left-right", "--count", "@{u}...HEAD")
        behind_str, ahead_str = out.split()
        return AheadBehind(ahead=int(ahead_str), behind=int(behind_str))

    def ff_merge_upstream(self) -> None:
        """仅快进合并 upstream；无法快进时失败（绝不制造合并提交或 force）。"""
        cp = self._run("merge", "--ff-only", "@{u}")
        if cp.returncode != 0:
            raise GitError("无法快进合并（存在分叉，需人工处理）", stderr=cp.stderr)

    def push(self, remote: str = "origin") -> None:
        cp = self._run("push", remote, "HEAD")
        if cp.returncode != 0:
            raise GitError(f"push {remote} 失败", stderr=cp.stderr)

    def add(self, paths: list[str]) -> None:
        """只暂存显式列出的路径（相对仓库根）。绝不 ``add -A``，避免波及用户其它改动。"""
        if not paths:
            return
        cp = self._run("add", "--", *paths)
        if cp.returncode != 0:
            raise GitError("git add 失败", stderr=cp.stderr)

    def has_staged_changes(self) -> bool:
        """暂存区是否有待提交内容（``diff --cached --quiet`` 返回 1 表示有）。"""
        return self._run("diff", "--cached", "--quiet").returncode != 0

    def commit(self, message: str) -> None:
        """提交暂存区。无暂存内容时应由调用方先判 :meth:`has_staged_changes`（幂等）。"""
        cp = self._run("commit", "-m", message)
        if cp.returncode != 0:
            raise GitError("git commit 失败", stderr=cp.stderr)

    def files_changed_by(self, sha: str) -> list[str]:
        """某提交触碰的文件（相对仓库根，去重排序）；非提交 sha → :class:`GitError`。"""
        cp = self._run("show", "--name-only", "--pretty=format:", sha)
        if cp.returncode != 0:
            raise GitError(f"git show {sha} 失败", stderr=cp.stderr)
        return sorted({line for line in cp.stdout.splitlines() if line.strip()})

    def log_grep(self, pattern: str, limit: int) -> list[tuple[str, str, str]]:
        """grep 提交主题的最近提交，返回 ``(sha, ISO 时间, 主题)``（供 wb 撤销历史）。"""
        cp = self._run("log", f"--grep={pattern}", f"-n{limit}", "--pretty=%H%x09%aI%x09%s")
        if cp.returncode != 0:
            raise GitError("git log --grep 失败", stderr=cp.stderr)
        rows: list[tuple[str, str, str]] = []
        for line in cp.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) >= 3:
                rows.append((parts[0], parts[1], "\t".join(parts[2:])))
        return rows

    def is_dirty_paths(self, rel_paths: list[str]) -> bool:
        """显式列出的相对路径是否有未提交改动（只查这些路径，绝不扫全库）。"""
        if not rel_paths:
            return False
        cp = self._run("status", "--porcelain", "--", *rel_paths)
        return bool(cp.stdout.strip())

    def revert(self, sha: str) -> None:
        """用 ``git revert --no-edit`` 撤销某提交（生成一个新提交）；冲突/失败抛错。

        失败时尽力 ``revert --abort`` 清理冲突态，让仓库回到可继续工作的状态。
        """
        cp = self._run("revert", "--no-edit", sha)
        if cp.returncode != 0:
            self._run("revert", "--abort")  # 冲突/失败后清理，返回码忽略
            raise GitError(f"git revert {sha} 失败", stderr=cp.stderr)

    def show_patch(self, sha: str) -> str:
        """某提交的完整差异输出（``git show --stat --patch``），供撤销面板预览。"""
        cp = self._run("show", "--stat", "--patch", sha)
        if cp.returncode != 0:
            raise GitError(f"git show {sha} 失败", stderr=cp.stderr)
        return cp.stdout

    def commits_between(self, since_iso: str, until_iso: str) -> list[tuple[str, str]]:
        """列出 [since, until] 内本地提交的 (短 hash, 主题)。只读，不联网。

        ``since_iso`` / ``until_iso`` 为 ISO 日期（``git log`` 的 --since/--until 语义，
        含边界当天）。仓库无提交或范围为空时返回空列表。
        """
        cp = self._run(
            "log",
            f"--since={since_iso} 00:00",
            f"--until={until_iso} 23:59",
            "--pretty=%h\t%s",
        )
        if cp.returncode != 0:
            raise GitError("git log 失败", stderr=cp.stderr)
        commits: list[tuple[str, str]] = []
        for line in cp.stdout.splitlines():
            if "\t" in line:
                sha, subject = line.split("\t", 1)
                commits.append((sha, subject))
        return commits
