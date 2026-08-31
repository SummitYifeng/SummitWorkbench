"""单个 Git 仓库的只读/安全写操作封装（subprocess）。

只暴露 work-sync 需要的原子操作，且**绝不做破坏性动作**：没有 reset/stash/force/
rebase；写操作仅限 ``fetch``、``merge --ff-only`` 和 ``push``。任何失败都抛
:class:`GitError`，由上层聚合为可见状态（NFR-6）。
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
