"""系统写回自动 commit 与面板撤销（P0'）。

写入即留痕：每次「系统侧写回」成功后自动对触碰文件做一次 git commit（消息带 ``wb:`` 前缀），
供撤销与历史查看；推送交给既有 ``wb sync`` / launchd（本模块不新增强制 push）。

安全边界（铁律）：

1. 只 ``git add`` **显式列出的路径**，绝不 ``add -A``（用户其它未提交改动不受影响）；
2. 非 git 仓库优雅降级：返回可见状态、不抛错、不阻断业务写回；
3. 任何 git 失败都转成可见状态（NFR-6），由调用方决定是否提示用户；
4. 撤销只作用于 vault 文件；飞书侧副作用（已建任务/会议、已完成状态）不可撤销，
   需在 UI 文案明示——本模块不触碰 vault 之外的任何状态。

提交/撤销序列（add → commit / revert）在 :func:`workspace_lock` 内进行，与其它 wb 写入者互斥
（与 publish_brief 同一把 .wb.lock；锁只包文件临界区，绝不跨 LLM/网络调用）。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from summit_workbench.config.locking import LockBusy, workspace_lock
from summit_workbench.repositories.git import GitError, GitRepo

# 撤销历史只认本系统的自动提交（消息以 wb: 开头），不把人工/其它提交混进撤销列表。
_WB_PREFIX_GREP = "^wb:"


class CommitStatus(StrEnum):
    COMMITTED = "committed"
    NOTHING_TO_COMMIT = "nothing-to-commit"  # 内容未变，幂等跳过
    NOT_GIT = "not-git"  # 非 git 仓库：优雅降级
    REVERTED = "reverted"  # 撤销成功（生成了新的反向提交）
    FAILED = "failed"  # git 失败/撤销被拒绝：转可见状态，不抛错
    BUSY = "busy(locked)"  # 工作区被另一 wb 任务占用


@dataclass(frozen=True)
class CommitResult:
    status: CommitStatus
    detail: str = ""

    def as_dict(self) -> dict[str, object]:
        return {"status": self.status.value, "detail": self.detail}


@dataclass(frozen=True)
class WbCommitInfo:
    sha: str
    message: str
    time: str  # ISO 8601（git 提交作者时间）
    files: tuple[str, ...]  # 触碰文件（相对 vault 根，排序）

    def as_dict(self) -> dict[str, object]:
        return {
            "sha": self.sha,
            "short_sha": self.sha[:8],
            "message": self.message,
            "time": self.time,
            "files": list(self.files),
        }


def _vault_relative(vault_dir: Path, paths: list[Path]) -> list[str]:
    """把绝对/相对路径规整为 vault 仓库内相对路径（库外文件静默跳过）。"""
    root = vault_dir.resolve()
    rel: list[str] = []
    for p in paths:
        absolute = p.resolve() if p.is_absolute() else (vault_dir / p).resolve()
        try:
            rel_path = absolute.relative_to(root)
        except ValueError:
            continue  # 路径不在 vault 内（如 Work 仓库文件）→ 不提交、不报错
        if absolute.is_file():
            rel.append(str(rel_path))
    return sorted(set(rel))


def commit_paths(vault_dir: Path, paths: list[Path], message: str) -> CommitResult:
    """把显式列出的 vault 文件提交（消息带 ``wb:`` 前缀），返回可见状态、绝不抛出。

    :param message: 提交主题，应自带 ``wb:`` 前缀（撤销历史按它检索）。
    """
    repo = GitRepo(vault_dir)
    if not repo.is_git_repo():
        return CommitResult(CommitStatus.NOT_GIT, f"{vault_dir} 不是 git 仓库")
    rel = _vault_relative(vault_dir, paths)
    if not rel:
        return CommitResult(CommitStatus.NOTHING_TO_COMMIT, "没有 vault 内文件需要提交")
    try:
        # add → commit 序列在工作区锁内，与 publish_brief / sync 互斥（ADR 0016）。
        with workspace_lock(vault_dir.parent):
            repo.add(rel)
            if not repo.has_staged_changes():
                return CommitResult(CommitStatus.NOTHING_TO_COMMIT, "内容未变，无需提交")
            repo.commit(message)
    except LockBusy as exc:
        return CommitResult(CommitStatus.BUSY, str(exc))
    except GitError as exc:
        return CommitResult(CommitStatus.FAILED, exc.stderr or str(exc))
    return CommitResult(CommitStatus.COMMITTED)


def list_wb_commits(vault_dir: Path, *, limit: int = 20) -> tuple[list[WbCommitInfo], str | None]:
    """最近 N 次 ``wb:`` 自动提交（含触碰文件），供撤销面板展示。

    非 git 仓库返回 ``([], 'not-git')``；git 失败返回 ``([], 错误摘要)``，都不抛出。
    """
    repo = GitRepo(vault_dir)
    if not repo.is_git_repo():
        return [], "not-git"
    try:
        rows = repo.log_grep(_WB_PREFIX_GREP, limit)
    except GitError as exc:
        return [], exc.stderr or str(exc)
    commits: list[WbCommitInfo] = []
    for sha, when, subject in rows:
        try:
            files = repo.files_changed_by(sha)
        except GitError:
            files = []
        commits.append(WbCommitInfo(sha=sha, message=subject, time=when, files=tuple(files)))
    return commits, None


def revert_commit(vault_dir: Path, sha: str) -> CommitResult:
    """撤销一次 ``wb:`` 自动提交（等价 ``git revert``，生成新提交）。

    还原前校验该提交触碰的文件工作树干净（有未提交人工改动时拒绝，避免覆盖用户手改）；
    冲突/失败返回可见错误；非 git 仓库优雅降级。撤销只作用于 vault 文件。
    """
    repo = GitRepo(vault_dir)
    if not repo.is_git_repo():
        return CommitResult(CommitStatus.NOT_GIT, f"{vault_dir} 不是 git 仓库")
    try:
        files = repo.files_changed_by(sha)
    except GitError as exc:
        return CommitResult(CommitStatus.FAILED, exc.stderr or str(exc))
    if repo.is_dirty_paths(files):
        return CommitResult(
            CommitStatus.FAILED,
            "该提交触碰的文件存在未提交改动，拒绝还原（避免覆盖你的手动修改）",
        )
    try:
        with workspace_lock(vault_dir.parent):
            repo.revert(sha)
    except LockBusy as exc:
        return CommitResult(CommitStatus.BUSY, str(exc))
    except GitError as exc:
        return CommitResult(CommitStatus.FAILED, exc.stderr or str(exc))
    return CommitResult(
        CommitStatus.REVERTED,
        f"已还原 {sha[:8]}（生成反向提交；vault 文件已回到该次提交前的状态）",
    )


def commit_diff_text(vault_dir: Path, sha: str) -> tuple[str, str | None]:
    """某提交的 before/after 差异（``git show`` 输出），供撤销面板预览。

    返回 ``(text, error)``；非 git 或失败时 ``text`` 为空、``error`` 为可见原因。
    """
    repo = GitRepo(vault_dir)
    if not repo.is_git_repo():
        return "", "not-git"
    try:
        return repo.show_patch(sha), None
    except GitError as exc:
        return "", exc.stderr or str(exc)
