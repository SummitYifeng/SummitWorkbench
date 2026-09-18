"""Git 远程凭据（P0-09）：workspace 作用域 Keychain + 身份映射。

- 凭据只经 workspace-scoped Keychain（P0-07 secrets API）读写；
- **绝不**把凭据写进 remote URL、磁盘、日志、``repr``、异常或 fixture；
  :func:`strip_credentials` 负责把 URL 里的 userinfo 剥掉后再落日志；
- :class:`GitCredentials` 只承载 username + :class:`SecretStr` 密码，可安全转成
  dulwich ``Credentials``（生产 HTTPS 后端的回调来源；真实 HTTPS 门在 P0-10/P0-13）；
- :func:`profile_identity`：Git author = profile 显示名 + 用户邮箱（缺省本地占位，
  绝不复制开发者 identity）。
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from pydantic import SecretStr

from summit_workbench.config.secrets import (
    delete_workspace_credential,
    resolve_workspace_credential,
    store_workspace_credential,
    workspace_account,
    workspace_credential_service,
)
from summit_workbench.domain.workspace import LocalProfile
from summit_workbench.repositories.git_backend import CommitIdentity

_PLACEHOLDER_EMAIL = "wb@local"


def normalize_git_username(username: str) -> str:
    """Normalize a public Git hosting username before profile/Keychain use."""
    normalized = username.strip().casefold()
    if not normalized or len(normalized) > 200:
        raise ValueError("Git 用户名不能为空或过长")
    return normalized


def strip_credentials(url: str) -> str:
    """把 URL 中的 userinfo（user:password@）剥掉，返回可安全展示的 URL。"""
    parts = urlsplit(url)
    if parts.username is None and parts.password is None:
        return url
    host = parts.hostname or ""
    if parts.port is not None:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))


def git_account(host: str, username: str) -> str:
    """workspace 作用域 git account 名（``git:<host>:<user>``，不含秘密）。"""
    return workspace_account("git", host, username)


def resolve_git_credentials(workspace_id: str, host: str, username: str) -> GitCredentials:
    """从 workspace 作用域 Keychain 读取某远端凭据（缺失报 CredentialError）。"""
    password = resolve_workspace_credential(workspace_id, git_account(host, username))
    return GitCredentials(workspace_id, host, username, password)


def store_git_credentials(workspace_id: str, host: str, username: str, password: SecretStr) -> None:
    """把某远端凭据写入 workspace 作用域 Keychain（只写作用域命名）。"""
    store_workspace_credential(workspace_id, git_account(host, username), password)


def delete_git_credentials(workspace_id: str, host: str, username: str) -> None:
    """删除一次转换写入的 workspace-scoped Git credential。"""
    delete_workspace_credential(workspace_id, git_account(host, username))


def profile_identity(profile: LocalProfile) -> CommitIdentity:
    """从本机 profile 派生 Git 身份：显示名 + 用户邮箱；缺省本地占位。"""
    return CommitIdentity(
        name=profile.display_name,
        email=profile.user_email or _PLACEHOLDER_EMAIL,
    )


@dataclass(frozen=True)
class GitCredentials:
    """单个远端的一次性凭据：username + SecretStr 密码，repr/日志不泄密。"""

    workspace_id: str
    host: str
    username: str
    password: SecretStr

    @property
    def service(self) -> str:
        """对应 Keychain service（workspace 作用域）。"""
        return workspace_credential_service(self.workspace_id)

    @property
    def account(self) -> str:
        return git_account(self.host, self.username)

    def as_dulwich_credentials(self) -> GitCredentials:
        """给 dulwich HTTP 客户端使用的凭据载体（0.22 无独立 Credentials 类）。

        由 P0-10 的 HTTPS 接线把 username/password 传入 HttpGitClient/porcelain；
        本对象 repr/str 绝不泄露密码。
        """
        return self

    def __repr__(self) -> str:  # noqa: D105 - 明确不泄露内容
        return f"GitCredentials(service={self.service!r}, account={self.account!r})"
