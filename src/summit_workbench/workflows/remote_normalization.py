"""P1-07D: safely normalize an existing production remote to HTTPS.

The preview validates a candidate in an isolated temporary clone.  Applying the
plan changes only ``origin`` and the local profile/keychain; it never commits,
pushes, or writes the vault.  The transaction record contains no credential.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import SecretStr

from summit_workbench.config.app_support import profile_dir
from summit_workbench.config.git_credentials import (
    GitCredentials,
    delete_git_credentials,
    normalize_git_username,
    resolve_git_credentials,
    store_git_credentials,
    strip_credentials,
)
from summit_workbench.repositories._atomic import atomic_write_text
from summit_workbench.repositories.git import GitRepo
from summit_workbench.repositories.git_backend import (
    AheadBehind,
    GitAuthError,
    GitError,
    GitRemoteSchemeUnsupported,
    GitTlsError,
)
from summit_workbench.repositories.profile_registry import load_profile, save_profile
from summit_workbench.repositories.workspace_manifest import load_workspace_manifest
from summit_workbench.workflows.remote_onboarding import validate_remote_url

if TYPE_CHECKING:
    from summit_workbench.repositories.dulwich_git import DulwichGitBackend


class RemoteNormalizationError(RuntimeError):
    """Stable, sanitized error for the settings transaction."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class RemoteValidation:
    remote_url: str
    workspace_id: str
    branch: str
    ahead: int
    behind: int
    fetched: bool = True


@dataclass(frozen=True)
class RemoteNormalizationPlan:
    plan_id: str
    workspace_id: str
    old_url: str
    candidate_url: str
    branch: str
    candidate: RemoteValidation


@dataclass(frozen=True)
class RemoteNormalizationTransaction:
    transaction_id: str
    workspace_id: str
    old_url: str
    new_url: str
    old_git_username: str | None
    old_git_remote_url: str | None
    status: str
    created_at: str


def _repo_identity(url: str) -> str | None:
    """Return host/path identity for HTTPS and GitHub scp-style URLs."""
    safe = strip_credentials(url.strip())
    scp = re.match(r"^[^@/:]+@([^:]+):(.+)$", safe)
    if scp:
        host, path = scp.group(1), scp.group(2)
    else:
        parsed = urlsplit(safe)
        if not parsed.hostname or not parsed.path:
            return None
        host, path = parsed.hostname, parsed.path
    return f"{host.lower()}/{path.strip('/').removesuffix('.git').lower()}"


def _transaction_path(workspace_id: str, home: Path | None) -> Path:
    return profile_dir(workspace_id, home) / "remote-normalization.json"


def _write_transaction(transaction: RemoteNormalizationTransaction, home: Path | None) -> None:
    path = _transaction_path(transaction.workspace_id, home)
    atomic_write_text(
        path,
        json.dumps(transaction.__dict__, ensure_ascii=False, indent=2) + "\n",
        new_mode=0o600,
    )


def load_transaction(workspace_id: str, home: Path | None) -> RemoteNormalizationTransaction | None:
    path = _transaction_path(workspace_id, home)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return RemoteNormalizationTransaction(**raw)
    except (OSError, ValueError, TypeError) as exc:
        raise RemoteNormalizationError(
            "normalization_transaction_invalid", "远端转换事务记录损坏，请重新预览"
        ) from exc


def credential_scoped_backend(
    path: Path, workspace_id: str, username: str, pat: SecretStr
) -> DulwichGitBackend:
    """带本次调用凭据的 Dulwich backend（PAT 只进短生命周期 callback，不落盘）。

    远端转换与 G2 的"首次发布"共用它：两处都必须只经 workspace 作用域的显式 resolver
    拿凭据，绝不把 PAT 写进 URL、配置或日志。
    """
    from summit_workbench.repositories.dulwich_git import DulwichGitBackend

    def resolve(_workspace_id: str, host: str, _username: str) -> GitCredentials:
        return GitCredentials(workspace_id, host, username, pat)

    return DulwichGitBackend(
        path,
        workspace_id=workspace_id,
        username=username,
        credential_resolver=resolve,
    )


def _validate_candidate(
    vault_dir: Path,
    *,
    workspace_id: str,
    username: str,
    pat: SecretStr,
    candidate_url: str,
    expected_branch: str | None = None,
) -> RemoteValidation:
    try:
        safe_url = validate_remote_url(candidate_url)
    except Exception as exc:
        code = getattr(exc, "code", "remote_url_invalid")
        if code == "remote_url_unsupported":
            code = "remote_scheme_unsupported"
        raise RemoteNormalizationError(code, str(exc)) from exc
    try:
        username = normalize_git_username(username)
    except ValueError as exc:
        raise RemoteNormalizationError("git_username_invalid", str(exc)) from exc
    if not pat.get_secret_value():
        raise RemoteNormalizationError("git_credential_missing", "GitHub PAT 不能为空")

    parent = Path(tempfile.mkdtemp(prefix=".summit-workbench-remote-check-"))
    clone_path = parent / "clone"
    try:
        backend = credential_scoped_backend(clone_path, workspace_id, username, pat)
        try:
            backend.clone(safe_url, clone_path)
            manifest = load_workspace_manifest(clone_path)
            if manifest is None or manifest.workspace_id != workspace_id:
                raise RemoteNormalizationError(
                    "workspace_identity_mismatch", "候选远端的 workspace marker 与当前工作台不一致"
                )
            branch = backend.current_branch()
            if expected_branch is not None and branch != expected_branch:
                raise RemoteNormalizationError(
                    "branch_mismatch", "候选远端默认分支与当前工作台分支不一致"
                )
            if not backend.has_upstream():
                raise RemoteNormalizationError("upstream_missing", "候选远端没有可验证的 upstream")
            backend.fetch()
            counts = backend.ahead_behind()
            if counts != AheadBehind(ahead=0, behind=0):
                raise RemoteNormalizationError(
                    "candidate_not_up_to_date", "候选远端 fetch 后不是一致的 branch/upstream"
                )
        except RemoteNormalizationError:
            raise
        except GitAuthError as exc:
            raise RemoteNormalizationError("git_auth_failed", "GitHub PAT 认证失败") from exc
        except GitTlsError as exc:
            raise RemoteNormalizationError("git_tls_failed", "HTTPS/TLS 校验失败") from exc
        except GitError as exc:
            raise RemoteNormalizationError(
                "remote_validation_failed", "候选 HTTPS remote 验证失败"
            ) from exc
        return RemoteValidation(
            remote_url=safe_url,
            workspace_id=workspace_id,
            branch=branch,
            ahead=counts.ahead,
            behind=counts.behind,
        )
    finally:
        shutil.rmtree(parent, ignore_errors=True)


def preview_remote_normalization(
    vault_dir: Path,
    *,
    workspace_id: str,
    username: str,
    pat: SecretStr,
    candidate_url: str,
    home: Path | None = None,
    backend_kind: str = "dulwich",
) -> RemoteNormalizationPlan:
    """Validate candidate credentials/repository without changing the local repo."""
    repo = GitRepo(vault_dir, backend_kind=backend_kind, workspace_id=workspace_id)
    try:
        old_url = repo.remote_url("origin")
    except GitError as exc:
        # 历史工作台可能没被纳入版本管理；给出可执行原因而不是 500 internal_error
        # （2026-09-13 真机复跑：新建工作台点「预览」就是这条路径）。
        raise RemoteNormalizationError(
            "vault_not_a_repository",
            "当前工作台还没有纳入版本管理：请重新创建它，或用「从另一台 Mac 克隆」接入已有工作台",
        ) from exc
    if not old_url:
        raise RemoteNormalizationError("remote_missing", "当前工作台没有 origin remote")
    try:
        branch = repo.current_branch()
    except GitError as exc:
        raise RemoteNormalizationError("branch_invalid", "当前工作台分支无法验证") from exc
    if not repo.has_upstream():
        raise RemoteNormalizationError("upstream_missing", "当前工作台没有可验证的 upstream")
    try:
        validation = _validate_candidate(
            vault_dir,
            workspace_id=workspace_id,
            username=username,
            pat=pat,
            candidate_url=candidate_url,
            expected_branch=branch,
        )
    except GitRemoteSchemeUnsupported as exc:
        raise RemoteNormalizationError("remote_scheme_unsupported", str(exc)) from exc
    old_identity = _repo_identity(old_url)
    candidate_identity = _repo_identity(validation.remote_url)
    if old_identity is None or candidate_identity is None or old_identity != candidate_identity:
        raise RemoteNormalizationError(
            "repository_identity_mismatch",
            "候选 HTTPS remote 不是当前工作台对应的同一 GitHub 仓库",
        )
    return RemoteNormalizationPlan(
        plan_id=str(uuid4()),
        workspace_id=workspace_id,
        old_url=old_url,
        candidate_url=validation.remote_url,
        branch=branch,
        candidate=validation,
    )


def apply_remote_normalization(
    vault_dir: Path,
    plan: RemoteNormalizationPlan,
    *,
    username: str,
    pat: SecretStr,
    home: Path | None = None,
    backend_kind: str = "dulwich",
) -> RemoteNormalizationTransaction:
    """Revalidate, then atomically update origin/profile/keychain with rollback."""
    try:
        username = normalize_git_username(username)
    except ValueError as exc:
        raise RemoteNormalizationError("git_username_invalid", str(exc)) from exc
    repo = GitRepo(vault_dir, backend_kind=backend_kind, workspace_id=plan.workspace_id)
    profile = load_profile(plan.workspace_id, home=home)
    if profile is None:
        raise RemoteNormalizationError("profile_missing", "当前 workspace profile 不存在")
    try:
        current_url = repo.remote_url("origin")
    except GitError as exc:
        raise RemoteNormalizationError(
            "vault_not_a_repository",
            "当前工作台还没有纳入版本管理：请重新创建它，或用「从另一台 Mac 克隆」接入已有工作台",
        ) from exc
    if current_url != plan.old_url:
        raise RemoteNormalizationError("plan_stale", "当前 origin 已变化，请重新预览")
    if repo.is_dirty():
        raise RemoteNormalizationError("dirty_tree", "工作树必须干净才能转换 remote")
    validation = _validate_candidate(
        vault_dir,
        workspace_id=plan.workspace_id,
        username=username,
        pat=pat,
        candidate_url=plan.candidate_url,
        expected_branch=plan.branch,
    )
    safe_url = validation.remote_url
    if _repo_identity(plan.old_url) != _repo_identity(safe_url):
        raise RemoteNormalizationError(
            "repository_identity_mismatch",
            "候选 HTTPS remote 不是当前工作台对应的同一 GitHub 仓库",
        )
    old_profile_username = profile.git_username
    old_profile_remote = profile.git_remote_url
    candidate_host = urlsplit(safe_url).hostname or ""
    previous_candidate_credential: GitCredentials | None = None
    if old_profile_username and candidate_host:
        try:
            previous_candidate_credential = resolve_git_credentials(
                plan.workspace_id, candidate_host, old_profile_username
            )
        except Exception:
            previous_candidate_credential = None
    url_changed = False
    credential_stored = False
    try:
        repo.set_remote_url(safe_url, "origin")
        url_changed = True
        save_profile(
            profile.model_copy(update={"git_username": username, "git_remote_url": safe_url}),
            home=home,
        )
        parsed = urlsplit(safe_url)
        store_git_credentials(plan.workspace_id, f"{parsed.hostname or ''}", username, pat)
        credential_stored = True
        transaction = RemoteNormalizationTransaction(
            transaction_id=str(uuid4()),
            workspace_id=plan.workspace_id,
            old_url=plan.old_url,
            new_url=safe_url,
            old_git_username=old_profile_username,
            old_git_remote_url=old_profile_remote,
            status="applied",
            created_at=datetime.now(UTC).isoformat(),
        )
        _write_transaction(transaction, home)
        return transaction
    except Exception as exc:  # noqa: BLE001 - rollback boundary
        if url_changed:
            try:
                repo.set_remote_url(plan.old_url, "origin")
            except GitError:
                pass
        try:
            save_profile(
                profile.model_copy(
                    update={
                        "git_username": old_profile_username,
                        "git_remote_url": old_profile_remote,
                    }
                ),
                home=home,
            )
        except Exception:
            pass
        if credential_stored and candidate_host:
            try:
                if previous_candidate_credential is not None and old_profile_username == username:
                    store_git_credentials(
                        plan.workspace_id,
                        candidate_host,
                        old_profile_username,
                        previous_candidate_credential.password,
                    )
                else:
                    delete_git_credentials(plan.workspace_id, candidate_host, username)
            except Exception:
                pass
        if isinstance(exc, RemoteNormalizationError):
            raise
        raise RemoteNormalizationError(
            "normalization_rolled_back", "远端转换失败，已恢复原配置"
        ) from exc


def rollback_remote_normalization(
    vault_dir: Path,
    *,
    workspace_id: str,
    home: Path | None = None,
    backend_kind: str = "dulwich",
) -> RemoteNormalizationTransaction:
    """Restore the exact pre-conversion origin/profile without touching vault content."""
    transaction = load_transaction(workspace_id, home)
    if transaction is None or transaction.status != "applied":
        raise RemoteNormalizationError(
            "normalization_transaction_missing", "没有可回滚的远端转换事务"
        )
    repo = GitRepo(vault_dir, backend_kind=backend_kind, workspace_id=workspace_id)
    if repo.remote_url("origin") != transaction.new_url:
        raise RemoteNormalizationError(
            "normalization_transaction_stale", "当前 origin 已变化，未执行回滚"
        )
    profile = load_profile(workspace_id, home=home)
    if profile is None:
        raise RemoteNormalizationError("profile_missing", "当前 workspace profile 不存在")
    repo.set_remote_url(transaction.old_url, "origin")
    save_profile(
        profile.model_copy(
            update={
                "git_username": transaction.old_git_username,
                "git_remote_url": transaction.old_git_remote_url,
            }
        ),
        home=home,
    )
    rolled_back = RemoteNormalizationTransaction(
        transaction_id=transaction.transaction_id,
        workspace_id=transaction.workspace_id,
        old_url=transaction.old_url,
        new_url=transaction.new_url,
        old_git_username=transaction.old_git_username,
        old_git_remote_url=transaction.old_git_remote_url,
        status="rolled-back",
        created_at=transaction.created_at,
    )
    _write_transaction(rolled_back, home)
    return rolled_back


__all__ = [
    "RemoteNormalizationError",
    "RemoteNormalizationPlan",
    "RemoteNormalizationTransaction",
    "apply_remote_normalization",
    "credential_scoped_backend",
    "load_transaction",
    "preview_remote_normalization",
    "rollback_remote_normalization",
]
