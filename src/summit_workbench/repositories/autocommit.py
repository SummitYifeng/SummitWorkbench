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

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from summit_workbench.config.locking import LockBusy, workspace_lock
from summit_workbench.repositories.git import GitError, GitRepo
from summit_workbench.repositories.git_backend import CommitIdentity

# 撤销历史只认本系统的自动提交（消息以 wb: 开头），不把人工/其它提交混进撤销列表。
_WB_PREFIX_GREP = "^wb:"
_FULL_SHA = re.compile(r"^[0-9a-fA-F]{40}$")


def _normalize_message(message: str) -> str | None:
    """规整提交主题为单行，并拒绝非 ``wb:`` 系统提交。"""
    normalized = " ".join(message.split())
    return normalized if normalized.startswith("wb:") else None


def _validate_wb_commit(repo: GitRepo, sha: str) -> tuple[str, str | None]:
    """校验完整 SHA、commit 类型、主题和单父边界，返回规范 SHA 与错误。"""
    if not _FULL_SHA.fullmatch(sha):
        return "", "无效 wb commit：只接受完整 40 位十六进制 commit id"
    try:
        resolved = repo.resolve_commit(sha)
        subject, parent_count = repo.validate_commit(resolved)
    except GitError as exc:
        return "", "无效 wb commit：" + (exc.stderr or "commit 不存在或不是可解析的 commit 对象")
    if not subject.startswith("wb:"):
        return "", "无效 wb commit：该提交不是系统自动提交（主题必须以 wb: 开头）"
    if parent_count != 1:
        return "", "无效 wb commit：该提交不是单父提交，拒绝操作"
    return resolved, None


def undo_error_code(detail: str) -> str:
    """把撤销读操作的错误归一为 Web API 可稳定消费的错误码。"""
    if detail == "not-git":
        return "undo_not_git"
    if (
        "无效 wb commit" in detail
        or "完整 40 位" in detail
        or "不是系统自动提交" in detail
        or "不是单父提交" in detail
        or "commit 不存在" in detail
        or "不是可解析的 commit" in detail
    ):
        return "undo_invalid_commit"
    return "undo_failed"


class CommitStatus(StrEnum):
    COMMITTED = "committed"
    INDEX_NOT_CLEAN = "index-not-clean"  # 调用前已有用户暂存内容，拒绝接管 index
    NOTHING_TO_COMMIT = "nothing-to-commit"  # 内容未变，幂等跳过
    NOT_GIT = "not-git"  # 非 git 仓库：优雅降级
    REVERTED = "reverted"  # 撤销成功（生成了新的反向提交）
    FAILED = "failed"  # git 失败/撤销被拒绝：转可见状态，不抛错
    BUSY = "busy(locked)"  # 工作区被另一 wb 任务占用


@dataclass(frozen=True)
class CommitResult:
    status: CommitStatus
    detail: str = ""
    error_code: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "detail": self.detail,
            "error_code": self.error_code,
        }


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


def commit_paths(
    vault_dir: Path,
    paths: list[Path],
    message: str,
    *,
    backend_kind: str | None = None,
    author: CommitIdentity | None = None,
) -> CommitResult:
    """把显式列出的 vault 文件提交（消息带 ``wb:`` 前缀），返回可见状态、绝不抛出。

    :param message: 提交主题，应自带 ``wb:`` 前缀（撤销历史按它检索）。
    """
    normalized_message = _normalize_message(message)
    if normalized_message is None:
        return CommitResult(
            CommitStatus.FAILED,
            "系统提交主题必须是单行且以 wb: 开头",
            error_code="invalid-message",
        )
    repo = GitRepo(vault_dir, backend_kind=backend_kind)
    if not repo.is_git_repo():
        return CommitResult(CommitStatus.NOT_GIT, f"{vault_dir} 不是 git 仓库")
    try:
        # add → commit 序列在工作区锁内，与 publish_brief / sync 互斥（ADR 0016）。
        with workspace_lock(vault_dir.parent):
            if repo.staged_paths():
                return CommitResult(
                    CommitStatus.INDEX_NOT_CLEAN,
                    "调用前暂存区已有用户内容，拒绝接管（请先完成或撤销手动暂存）",
                    error_code="index-not-clean",
                )
            rel = _vault_relative(vault_dir, paths)
            if not rel:
                return CommitResult(CommitStatus.NOTHING_TO_COMMIT, "没有 vault 内文件需要提交")
            repo.add(rel)
            if not repo.has_staged_changes(rel):
                return CommitResult(CommitStatus.NOTHING_TO_COMMIT, "内容未变，无需提交")
            repo.commit(normalized_message, author=author)
    except LockBusy as exc:
        return CommitResult(CommitStatus.BUSY, str(exc), error_code="workspace-locked")
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
        validated_sha, validation_error = _validate_wb_commit(repo, sha)
        if validation_error is not None:
            continue
        try:
            files = repo.files_changed_by(validated_sha)
        except GitError:
            files = []
        commits.append(
            WbCommitInfo(sha=validated_sha, message=subject, time=when, files=tuple(files))
        )
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
        with workspace_lock(vault_dir.parent):
            validated_sha, validation_error = _validate_wb_commit(repo, sha)
            if validation_error is not None:
                return CommitResult(
                    CommitStatus.FAILED,
                    validation_error,
                    error_code="invalid-wb-commit",
                )
            files = repo.files_changed_by(validated_sha)
            if repo.is_dirty_paths(files):
                return CommitResult(
                    CommitStatus.FAILED,
                    "该提交触碰的文件存在未提交改动，拒绝还原（避免覆盖你的手动修改）",
                    error_code="undo-target-dirty",
                )
            repo.revert(validated_sha)
    except LockBusy as exc:
        return CommitResult(CommitStatus.BUSY, str(exc), error_code="workspace-locked")
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
        validated_sha, validation_error = _validate_wb_commit(repo, sha)
        if validation_error is not None:
            return "", validation_error
        return repo.show_patch(validated_sha), None
    except GitError as exc:
        return "", exc.stderr or str(exc)
