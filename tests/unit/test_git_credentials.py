"""P0-09 git 凭据与身份测试。

凭据绝不进入 remote URL / repr / 异常 / fixture（canary 锁定）；读写只走
workspace-scoped Keychain；Git author 用 profile 显示名 + 用户邮箱（缺省本地占位）。
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from summit_workbench.config import secrets as secrets_mod
from summit_workbench.config.git_credentials import (
    GitCredentials,
    git_account,
    profile_identity,
    resolve_git_credentials,
    store_git_credentials,
    strip_credentials,
)
from summit_workbench.config.secrets import CredentialError, CredentialRef
from summit_workbench.domain.workspace import DeviceRole, LocalProfile


def _profile(user_email: str | None) -> LocalProfile:
    return LocalProfile.model_validate(
        {
            "schema_version": 1,
            "workspace_id": "workspace-1",
            "display_name": "我的工作台",
            "work_root": "/tmp/work",
            "vault_dir": "/tmp/work/_vault",
            "device_role": DeviceRole.SECONDARY.value,
            "created_at": "2026-09-05T00:00:00Z",
            "user_email": user_email,
        }
    )


def _fake_keychain(monkeypatch: pytest.MonkeyPatch) -> dict[tuple[str, str], str]:
    store: dict[tuple[str, str], str] = {}

    def fake_resolve(ref: CredentialRef) -> SecretStr:
        try:
            return SecretStr(store[(ref.service, ref.account)])
        except KeyError as exc:
            raise CredentialError(f"未找到 {ref}") from exc

    def fake_store(ref: CredentialRef, value: SecretStr) -> None:
        store[(ref.service, ref.account)] = value.get_secret_value()

    monkeypatch.setattr(secrets_mod, "resolve_credential", fake_resolve)
    monkeypatch.setattr(secrets_mod, "store_credential", fake_store)
    return store


def test_strip_credentials_removes_userinfo() -> None:
    assert (
        strip_credentials("https://alice:" + "s3cret" + "@github.com/yifeng/ws.git")
        == "https://github.com/yifeng/ws.git"
    )
    assert (
        strip_credentials("https://github.com/yifeng/ws.git") == "https://github.com/yifeng/ws.git"
    )


def test_account_naming_and_scoped_service() -> None:
    assert git_account("github.com", "yifeng") == "git:github.com:yifeng"
    cred = GitCredentials("workspace-1", "github.com", "yifeng", SecretStr("pw"))
    assert cred.service == "com.summitworkbench.credentials.workspace-1"
    assert cred.account == "git:github.com:yifeng"


def test_credentials_repr_and_dulwich_hide_secret() -> None:
    cred = GitCredentials("workspace-1", "github.com", "yifeng", SecretStr("s3cr3t-token"))
    assert "s3cr3t-token" not in repr(cred)
    assert "s3cr3t-token" not in str(cred)
    carried = cred.as_dulwich_credentials()
    assert "s3cr3t-token" not in repr(carried)
    assert carried.password.get_secret_value() == "s3cr3t-token"


def test_git_credential_store_and_resolve_are_workspace_scoped(monkeypatch) -> None:
    store = _fake_keychain(monkeypatch)
    store_git_credentials("workspace-1", "github.com", "yifeng", SecretStr("pat-a"))
    store_git_credentials("workspace-2", "github.com", "yifeng", SecretStr("pat-b"))
    assert list(store.keys()) == [
        ("com.summitworkbench.credentials.workspace-1", "git:github.com:yifeng"),
        ("com.summitworkbench.credentials.workspace-2", "git:github.com:yifeng"),
    ]
    got = resolve_git_credentials("workspace-1", "github.com", "yifeng")
    assert got.password.get_secret_value() == "pat-a"
    with pytest.raises(CredentialError):
        resolve_git_credentials("workspace-3", "github.com", "yifeng")
    # 秘密绝不进入异常文本
    try:
        resolve_git_credentials("workspace-3", "github.com", "yifeng")
    except CredentialError as exc:
        assert "pat" not in str(exc)


def test_profile_identity_uses_display_name_and_email_placeholder() -> None:
    with_email = profile_identity(_profile("me@example.com"))
    assert with_email.name == "我的工作台"
    assert with_email.email == "me@example.com"
    without = profile_identity(_profile(None))
    assert without.email == "wb@local"  # 本地占位，绝不复制开发者 identity
