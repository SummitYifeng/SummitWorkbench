"""G2：把已有本地工作台首次发布到一个新建的 HTTPS 远端。

设置页原先只有「规范化」（要求**已存在** origin + upstream）与向导的 clone
（远端 → 本地）；本地已存在、远端尚未创建的工作台只能手工 ``git init`` /
``git remote add`` / 首次 push。这里补上「绑定已有远端并首次推送」这条路径，
复用规范化那条凭据链（``credential_scoped_backend`` + workspace Keychain）。

安全约定：

- **只走 HTTPS**（``validate_remote_url``），凭据只经短生命周期 callback 进请求，
  只在成功后写入 workspace Keychain；URL 与凭据绝不进 vault、提交或日志。
- **只接受空远端**：目标远端必须没有任何 ``refs/heads/*``。本地工作台的历史与
  远端已有提交通常无关，盲推只会在远端留下"被拒的非快进"，不如在预检阶段说清楚。
- **绝不 force**：先在一个临时克隆里真推一次证明"可推送"，成功后才在真 vault 上
  ``add_remote`` → ``push`` → 写 profile/Keychain → 最后写 upstream 配置；
  push 之前任何一步失败都 ``remove_remote`` 回到"没有远端"。
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from dulwich import porcelain
from pydantic import SecretStr

from summit_workbench.config.git_credentials import (
    delete_git_credentials,
    normalize_git_username,
    resolve_git_credentials,
    store_git_credentials,
)
from summit_workbench.repositories.git import GitRepo
from summit_workbench.repositories.git_backend import (
    GitAuthError,
    GitError,
    GitNonFastForward,
    GitRemoteSchemeUnsupported,
    GitTlsError,
)
from summit_workbench.repositories.profile_registry import load_profile, save_profile
from summit_workbench.workflows.remote_normalization import (
    RemoteNormalizationError,
    credential_scoped_backend,
)
from summit_workbench.workflows.remote_onboarding import validate_remote_url

if TYPE_CHECKING:
    from summit_workbench.repositories.dulwich_git import DulwichGitBackend


class RemotePublishError(RemoteNormalizationError):
    """首次发布的稳定、脱敏错误（与远端转换共用同一条 API 错误通道）。"""


@dataclass(frozen=True)
class RemotePublishValidation:
    """预检结果：只包含可安全展示的非敏感字段。"""

    remote_url: str
    workspace_id: str
    branch: str


@dataclass(frozen=True)
class RemotePublishResult:
    remote_url: str
    workspace_id: str
    branch: str
    head: str


def _check_remote_empty(backend: DulwichGitBackend, url: str) -> None:
    """确认目标远端没有任何分支（ls_remote 只读，不推送、不落盘）。"""
    try:
        refs = porcelain.ls_remote(url, **backend.transport_kwargs(url, operation="fetch"))
    except GitAuthError as exc:
        raise RemotePublishError("git_auth_failed", "GitHub PAT 认证失败") from exc
    except GitTlsError as exc:
        raise RemotePublishError("git_tls_failed", "HTTPS/TLS 校验失败") from exc
    except Exception as exc:  # noqa: BLE001 - service boundary must stay stable/sanitized
        raise RemotePublishError(
            "remote_unreachable", "无法访问目标远端，请检查地址、网络或代理"
        ) from exc
    if any(ref.startswith(b"refs/heads/") for ref in refs):
        raise RemotePublishError(
            "remote_not_empty",
            "目标远端已有提交：首次发布只接受空仓库。请新建一个空仓库（不要勾选 README），"
            "或对已有工作台使用「预览 HTTPS 转换」",
        )


def _checked_publish_target(
    vault_dir: Path, workspace_id: str, candidate_url: str, backend_kind: str
) -> tuple[GitRepo, str, str]:
    """共同的本地前置检查：是仓库、有提交、拿到分支名。"""
    try:
        safe_url = validate_remote_url(candidate_url)
    except Exception as exc:
        code = getattr(exc, "code", "remote_url_invalid")
        if code == "remote_url_unsupported":
            code = "remote_scheme_unsupported"
        raise RemotePublishError(code, str(exc)) from exc
    repo = GitRepo(vault_dir, backend_kind=backend_kind, workspace_id=workspace_id)
    if not repo.is_git_repo():
        raise RemotePublishError(
            "vault_not_a_repository",
            "当前工作台还没有纳入版本管理：请重新创建它，或用「从另一台 Mac 克隆」接入已有工作台",
        )
    try:
        branch = repo.current_branch()
    except GitError as exc:
        raise RemotePublishError("branch_invalid", "当前工作台分支无法验证") from exc
    try:
        repo.head_revision()
    except GitError as exc:
        raise RemotePublishError(
            "vault_has_no_commits", "当前工作台还没有任何提交，没有可发布的内容"
        ) from exc
    return repo, safe_url, branch


def validate_publish_target(
    vault_dir: Path,
    *,
    workspace_id: str,
    username: str,
    pat: SecretStr,
    candidate_url: str,
    backend_kind: str = "dulwich",
) -> RemotePublishValidation:
    """在临时克隆里验证凭据与目标远端；不修改真实 vault。"""
    try:
        username = normalize_git_username(username)
    except ValueError as exc:
        raise RemotePublishError("git_username_invalid", str(exc)) from exc
    if not pat.get_secret_value():
        raise RemotePublishError("git_credential_missing", "GitHub PAT 不能为空")
    _, safe_url, branch = _checked_publish_target(
        vault_dir, workspace_id, candidate_url, backend_kind
    )

    parent = Path(tempfile.mkdtemp(prefix=".summit-workbench-remote-publish-"))
    clone_path = parent / "clone"
    try:
        backend = credential_scoped_backend(clone_path, workspace_id, username, pat)
        try:
            _check_remote_empty(backend, safe_url)
            # 从本地 vault 克隆一份历史，再真推一次：证明可推送（权限/分支保护/网络）。
            repo, _, _ = _checked_publish_target(
                vault_dir, workspace_id, candidate_url, backend_kind
            )
            repo.backend.clone(str(vault_dir), clone_path)
            backend.add_remote("origin", safe_url)
            backend.push()
        except RemotePublishError:
            raise
        except GitNonFastForward as exc:
            raise RemotePublishError(
                "remote_not_empty",
                "目标远端已有不相关的历史，首次发布被拒。请新建空仓库或改用「预览 HTTPS 转换」",
            ) from exc
        except GitAuthError as exc:
            raise RemotePublishError("git_auth_failed", "GitHub PAT 认证失败") from exc
        except GitTlsError as exc:
            raise RemotePublishError("git_tls_failed", "HTTPS/TLS 校验失败") from exc
        except GitRemoteSchemeUnsupported as exc:
            raise RemotePublishError("remote_scheme_unsupported", str(exc)) from exc
        except GitError as exc:
            raise RemotePublishError("remote_publish_failed", "目标远端不可推送") from exc
    finally:
        shutil.rmtree(parent, ignore_errors=True)
    return RemotePublishValidation(remote_url=safe_url, workspace_id=workspace_id, branch=branch)


def _scrub(message: str, pat: SecretStr) -> str:
    """异常文本里若混进了 PAT（某个库把它拼进消息）就在这里抹掉再上抛。"""
    value = pat.get_secret_value()
    return message.replace(value, "***") if value else message


def _push_with_credentials(
    repo: GitRepo,
    vault_dir: Path,
    *,
    workspace_id: str,
    username: str,
    pat: SecretStr,
    backend_kind: str,
) -> None:
    """把本地工作台的历史推到 origin——**必须带本次凭据**。

    BUG-1（2026-09-14 实测）：``_checked_publish_target`` 构造的 repo 只带 ``workspace_id``、
    没有 ``username`` 与凭据回调，而 dulwich 后端在 ``not self._username`` 时直接抛
    ``GitCredentialsUnavailable``——它又被调用点的兜底 ``except`` 吞成
    ``remote_publish_rolled_back``。结果是**全新 workspace 的首次发布必然失败**；
    更糟的是预检那次 push 是带凭据的，所以远端会先被推上 ``main``，留下
    「远端有 main、本地没有 origin」的半成品状态。

    ``system`` 后端走操作系统的凭据助手，不需要显式注入。
    """
    if backend_kind == "system":
        repo.push()
        return
    scoped = GitRepo(
        vault_dir,
        backend_kind=backend_kind,
        workspace_id=workspace_id,
        backend=credential_scoped_backend(vault_dir, workspace_id, username, pat),
    )
    scoped.push()


def publish_workspace_to_remote(
    vault_dir: Path,
    *,
    workspace_id: str,
    username: str,
    pat: SecretStr,
    candidate_url: str,
    home: Path | None = None,
    backend_kind: str = "dulwich",
) -> RemotePublishResult:
    """校验后把本地工作台绑定到新远端并首次推送（失败回到「没有远端」）。"""
    try:
        username = normalize_git_username(username)
    except ValueError as exc:
        raise RemotePublishError("git_username_invalid", str(exc)) from exc
    repo, safe_url, branch = _checked_publish_target(
        vault_dir, workspace_id, candidate_url, backend_kind
    )
    try:
        existing_url = repo.remote_url("origin")
    except GitError as exc:
        raise RemotePublishError(
            "vault_not_a_repository",
            "当前工作台还没有纳入版本管理：请重新创建它，或用「从另一台 Mac 克隆」接入已有工作台",
        ) from exc
    if existing_url is not None:
        raise RemotePublishError(
            "remote_already_configured",
            "当前工作台已经配置了 origin：如需换到新远端，请使用「预览 HTTPS 转换」",
        )
    if repo.is_dirty():
        raise RemotePublishError("dirty_tree", "工作树必须干净才能发布到远端")
    profile = load_profile(workspace_id, home=home)
    if profile is None:
        raise RemotePublishError("profile_missing", "当前 workspace profile 不存在")

    validation = validate_publish_target(
        vault_dir,
        workspace_id=workspace_id,
        username=username,
        pat=pat,
        candidate_url=candidate_url,
        backend_kind=backend_kind,
    )
    safe_url = validation.remote_url
    host = urlsplit(safe_url).hostname or ""
    head = repo.head_revision()

    old_username = profile.git_username
    old_remote_url = profile.git_remote_url
    previous_credential = None
    if host:
        try:
            previous_credential = resolve_git_credentials(workspace_id, host, username)
        except Exception:
            previous_credential = None
    remote_added = False
    credential_stored = False
    try:
        repo.add_remote("origin", safe_url)
        remote_added = True
        _push_with_credentials(
            repo,
            vault_dir,
            workspace_id=workspace_id,
            username=username,
            pat=pat,
            backend_kind=backend_kind,
        )
        save_profile(
            profile.model_copy(update={"git_username": username, "git_remote_url": safe_url}),
            home=home,
        )
        if host:
            store_git_credentials(workspace_id, host, username, pat)
            credential_stored = True
        # upstream 配置最后写：纯本地配置写失败也不会留下"origin 指向空远端但 upstream 半配"的状态
        repo.set_upstream("origin", validation.branch)
    except Exception as exc:  # noqa: BLE001 - rollback boundary
        if remote_added:
            try:
                repo.remove_remote("origin")
            except GitError:
                pass
        try:
            save_profile(
                profile.model_copy(
                    update={"git_username": old_username, "git_remote_url": old_remote_url}
                ),
                home=home,
            )
        except Exception:
            pass
        if credential_stored and host:
            try:
                if previous_credential is not None:
                    store_git_credentials(
                        workspace_id, host, username, previous_credential.password
                    )
                else:
                    delete_git_credentials(workspace_id, host, username)
            except Exception:
                pass
        if isinstance(exc, RemotePublishError):
            raise
        if isinstance(exc, GitRemoteSchemeUnsupported):
            raise RemotePublishError("remote_scheme_unsupported", str(exc)) from exc
        # 把真正的原因带出来：早先这里只写「已恢复到没有远端的状态」，于是 BUG-1 的真因
        # （GitCredentialsUnavailable）在界面上完全不可见，只能靠读代码猜（2026-09-14 实测）。
        detail = _scrub(str(exc), pat) or type(exc).__name__
        raise RemotePublishError(
            "remote_publish_rolled_back",
            f"首次发布失败（{type(exc).__name__}：{detail}），已恢复到没有远端的状态",
        ) from exc
    return RemotePublishResult(
        remote_url=safe_url, workspace_id=workspace_id, branch=validation.branch, head=head
    )


__all__ = [
    "RemotePublishError",
    "RemotePublishResult",
    "RemotePublishValidation",
    "publish_workspace_to_remote",
    "validate_publish_target",
]
