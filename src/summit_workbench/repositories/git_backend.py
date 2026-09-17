"""Git 后端契约、typed errors 与后端选择（P0-09）。

把「单个 Git 仓库的只读/安全写操作」从系统 ``git`` subprocess 中解耦：

- :class:`GitBackend`（Protocol）：能力契约 = repo detect/init/clone、status 与
  staged/unstaged/untracked 精确列表、add 显式路径、commit、log/filter、diff、
  revert wb commit、remote/upstream detect、fetch、ahead/behind、fast-forward、push、
  current branch、commit identity、错误分类。
- **绝不做破坏性动作**：没有 reset/stash/force/rebase；写操作仅限 fetch、ff 合并、
  add <显式路径>、commit、push。
- typed errors：远程不可达/认证失败/TLS 失败/非快进/冲突各自可分类，全部派生
  :class:`GitError`（既有上层仍可统一捕获）。

运行时选择（P0-09C）：默认 ``system``（开发/CLI 保持现状）；production/packaged
调用方必须把 ``dulwich`` 作为显式 backend 注入，不能依赖跨测试/跨请求的进程环境变量。
``WB_GIT_BACKEND=dulwich`` 仍保留给 development conformance 与离线调试。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

_GIT_BACKEND_ENV = "WB_GIT_BACKEND"
SUPPORTED_KINDS = ("system", "dulwich")


class GitError(RuntimeError):
    """git 操作失败。``stderr`` 保留摘要供审计；异常文本不含凭据。"""

    def __init__(self, message: str, *, stderr: str = "") -> None:
        super().__init__(message)
        self.stderr = stderr.strip().splitlines()[0] if stderr.strip() else ""


class GitRemoteUnavailable(GitError):
    """远端不可达 / 不存在（fetch/push 网络层或仓库层失败）。"""


class GitRemoteSchemeUnsupported(GitError):
    """生产同步拒绝不受支持的 remote scheme。"""


class GitAuthError(GitError):
    """远端认证失败（wrong credential / 401 / 403）。"""


class GitTlsError(GitError):
    """TLS/证书校验失败。"""


class GitNonFastForward(GitError):
    """推送或合并不是快进（分叉，需人工处理；绝不 force）。"""


class GitConflictError(GitError):
    """revert/合并产生冲突，操作未完成（仓库已清理回可继续状态）。"""


class GitInvalidRevision(GitError):
    """revision 无法解析为仓库中的 commit 对象。"""


class GitCredentialsUnavailable(GitError):
    """HTTPS 凭据缺失或无法从 workspace Keychain 读取（区别于「凭据错误」的 401/403）。"""


class GitCertificateError(GitError):
    """TLS 证书链校验失败（自签名/不受信 CA/吊销），区别于握手或协议层 TLS 失败。"""


class GitProxyError(GitError):
    """HTTP(S) 代理连接或代理认证失败。"""


class GitBackendRuntimeError(GitError):
    """git 后端内部运行时错误（非远端、非凭据、非 TLS 的意外异常）。"""


def classify_git_error(error: BaseException) -> str:
    """把 git 异常映射成稳定、脱敏的诊断码。

    诊断码绝不包含 URL、凭据或本机路径；acceptance preflight 与同步报告用它区分
    auth / tls / certificate / proxy / credentials-unavailable / network / backend。
    """
    if isinstance(error, GitCredentialsUnavailable):
        return "git_credentials_unavailable"
    if isinstance(error, GitCertificateError):
        return "git_certificate_failed"
    if isinstance(error, GitTlsError):
        return "git_tls_failed"
    if isinstance(error, GitProxyError):
        return "git_proxy_failed"
    if isinstance(error, GitAuthError):
        return "git_auth_failed"
    if isinstance(error, GitRemoteSchemeUnsupported):
        return "git_remote_scheme_unsupported"
    if isinstance(error, GitRemoteUnavailable):
        return "git_remote_unavailable"
    if isinstance(error, GitNonFastForward):
        return "git_non_fast_forward"
    if isinstance(error, GitConflictError):
        return "git_conflict"
    if isinstance(error, GitInvalidRevision):
        return "git_invalid_revision"
    if isinstance(error, GitError):
        return "git_error"
    return "git_backend_runtime_error"


@dataclass(frozen=True)
class AheadBehind:
    ahead: int  # 本地领先 upstream 的提交数（可 push）
    behind: int  # 本地落后 upstream 的提交数（可 ff-pull）


@dataclass(frozen=True)
class CommitIdentity:
    """提交作者/提交者身份（P0-09：profile 显示名 + 用户邮箱；缺省本地占位）。"""

    name: str
    email: str


@dataclass(frozen=True)
class CommitMetadata:
    """只读分叉诊断所需的提交元数据；不包含正文和作者邮箱。"""

    revision: str
    authored_at: str
    subject: str


def default_identity() -> CommitIdentity:
    """本地占位身份：绝不复制开发者 identity（P0-09 要求 6）。"""
    return CommitIdentity(name="SummitWorkbench", email="wb@local")


class GitBackend(Protocol):
    """单个仓库的 git 后端能力契约（全部操作只作用于本仓库路径）。"""

    @property
    def path(self) -> Path: ...

    def is_git_repo(self) -> bool: ...
    def init(self, *, bare: bool = False, default_branch: str = "main") -> None: ...
    def clone(self, url: str, destination: Path) -> None: ...

    def has_remote(self, name: str = "origin") -> bool: ...
    def remote_url(self, name: str = "origin") -> str | None: ...
    def set_remote_url(self, url: str, name: str = "origin") -> None: ...
    def add_remote(self, name: str, url: str) -> None: ...
    def remove_remote(self, name: str = "origin") -> None: ...
    def set_upstream(self, remote: str = "origin", branch: str | None = None) -> None: ...
    def current_branch(self) -> str: ...
    def head_revision(self) -> str: ...
    def has_upstream(self) -> bool: ...
    def upstream_revision(self) -> str: ...

    def is_dirty(self) -> bool: ...
    def is_dirty_paths(self, rel_paths: list[str]) -> bool: ...
    def staged_paths(self) -> list[str]: ...
    def has_staged_changes(self, paths: list[str] | None = None) -> bool: ...

    def add(self, paths: list[str]) -> None: ...
    def commit(self, message: str, *, author: CommitIdentity | None = None) -> None: ...
    def commit_merge(
        self,
        message: str,
        merge_parent: str,
        *,
        author: CommitIdentity | None = None,
    ) -> None: ...
    def fetch(self, remote: str = "origin") -> None: ...
    def ahead_behind(self) -> AheadBehind: ...
    def pending_wb_commits(self) -> int: ...
    def ff_merge_upstream(self) -> None: ...
    def push(self, remote: str = "origin") -> None: ...

    def resolve_commit(self, sha: str) -> str: ...
    def commit_subject(self, sha: str) -> str: ...
    def commit_parent_count(self, sha: str) -> int: ...
    def validate_commit(self, sha: str) -> tuple[str, int]: ...
    def files_changed_by(self, sha: str) -> list[str]: ...
    def merge_base(self, left: str, right: str) -> str: ...
    def files_changed_between(self, base: str, head: str) -> list[str]: ...
    def commit_metadata(self, sha: str) -> CommitMetadata: ...
    def read_file_at(self, revision: str, path: str) -> bytes | None: ...
    def log_grep(self, pattern: str, limit: int) -> list[tuple[str, str, str]]: ...
    def show_patch(self, sha: str) -> str: ...
    def commits_between(self, since_iso: str, until_iso: str) -> list[tuple[str, str]]: ...
    def revert(self, sha: str) -> None: ...


def backend_kind() -> str:
    """运行时后端：环境变量 ``WB_GIT_BACKEND``（system|dulwich），默认 system。"""
    kind = os.environ.get(_GIT_BACKEND_ENV, "system").strip().lower()
    if kind not in SUPPORTED_KINDS:
        raise ValueError(f"未知 git backend：{kind!r}（支持 {SUPPORTED_KINDS}）")
    return kind


def production_backend_kind() -> str:
    """production/packaged 的固定 backend；不读取环境变量。"""
    return "dulwich"


_SCP_REMOTE_RE = re.compile(r"^(?P<user>[^@\s/:]+)@(?P<host>[^:\s/]+):(?P<path>\S+)$")


def require_https_remote(url: str) -> None:
    """Require an HTTPS or SSH remote without echoing URL credentials."""
    raw = url.strip()
    match = _SCP_REMOTE_RE.fullmatch(raw)
    normalized = (
        f"ssh://{match.group('user')}@{match.group('host')}/{match.group('path')}" if match else raw
    )
    try:
        parsed = urlsplit(normalized)
    except ValueError as exc:
        raise GitRemoteSchemeUnsupported(
            "生产同步只支持 HTTPS 或 SSH remote（remote_scheme_unsupported）"
        ) from exc
    if (
        parsed.scheme.lower() not in {"https", "ssh"}
        or not parsed.hostname
        or parsed.password is not None
    ):
        raise GitRemoteSchemeUnsupported(
            "生产同步只支持 HTTPS 或 SSH remote（remote_scheme_unsupported）"
        )
