"""P0-07 workspace 作用域凭据 API 测试。

Keychain service = ``com.summitworkbench.credentials.<workspace_id>``，account 形如
``llm:<provider>:<name>`` / ``feishu:<app_id>:app_secret`` / ``git:<host>:<user>``。
语义：两个 workspace 的同 provider 凭据引用不串用；本层只写 workspace 作用域命名
（旧命名读取仅保留为显式迁移入口）；provider 接线留 P0-08（本包只锁 API 与存储语义）。
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from summit_workbench.config import secrets as secrets_mod
from summit_workbench.config.secrets import (
    CredentialError,
    CredentialRef,
    resolve_legacy_credential_for_migration,
    resolve_workspace_credential,
    store_workspace_credential,
    workspace_account,
    workspace_credential_ref,
    workspace_credential_service,
)


def _fake_keychain(monkeypatch: pytest.MonkeyPatch) -> dict[tuple[str, str], str]:
    """把 Keychain 替换成内存 dict：key=(service, account)，value=秘密。"""
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


def test_workspace_service_and_account_naming() -> None:
    assert workspace_credential_service("W-1") == "com.summitworkbench.credentials.W-1"
    assert workspace_credential_service("W-2") != workspace_credential_service("W-1")
    assert workspace_account("llm", "deepseek", "shared") == "llm:deepseek:shared"
    assert workspace_account("feishu", "cli_abc", "app_secret") == "feishu:cli_abc:app_secret"
    assert workspace_account("git", "github.com", "yifeng") == "git:github.com:yifeng"


def test_two_workspaces_same_provider_refs_do_not_collide(monkeypatch) -> None:
    _fake_keychain(monkeypatch)
    store_workspace_credential(
        "W-A", workspace_account("llm", "deepseek", "shared"), SecretStr("key-a")
    )
    store_workspace_credential(
        "W-B", workspace_account("llm", "deepseek", "shared"), SecretStr("key-b")
    )
    assert (
        resolve_workspace_credential(
            "W-A", workspace_account("llm", "deepseek", "shared")
        ).get_secret_value()
        == "key-a"
    )
    assert (
        resolve_workspace_credential(
            "W-B", workspace_account("llm", "deepseek", "shared")
        ).get_secret_value()
        == "key-b"
    )
    # 不同 workspace 互不可见：只写过 A，读 B 报 CredentialError
    with pytest.raises(CredentialError):
        resolve_workspace_credential("W-A", workspace_account("git", "github.com", "nobody"))
    with pytest.raises(CredentialError):
        resolve_workspace_credential("W-C", workspace_account("llm", "deepseek", "shared"))


def test_store_always_uses_workspace_scoped_service(monkeypatch) -> None:
    store = _fake_keychain(monkeypatch)
    store_workspace_credential(
        "W-1", workspace_account("feishu", "app1", "refresh_token"), SecretStr("rt")
    )
    assert list(store.keys()) == [
        ("com.summitworkbench.credentials.W-1", "feishu:app1:refresh_token")
    ]


def test_ref_helpers_produce_scoped_ref() -> None:
    ref = workspace_credential_ref("W-1", workspace_account("llm", "deepseek", "shared"))
    assert ref.service == "com.summitworkbench.credentials.W-1"
    assert ref.account == "llm:deepseek:shared"


def test_legacy_read_only_as_explicit_migration(monkeypatch) -> None:
    """旧命名读取只经显式迁移入口；普通 workspace 解析不含旧命名回退。"""
    store = _fake_keychain(monkeypatch)
    legacy = CredentialRef(service="summit-workbench-feishu-app-secret", account="app1")
    store[(legacy.service, legacy.account)] = "old-secret"
    # 显式迁移入口可读旧命名
    value = resolve_legacy_credential_for_migration(legacy)
    assert value.get_secret_value() == "old-secret"
    # 普通 workspace 作用域解析不会读旧命名 → 报错
    with pytest.raises(CredentialError):
        resolve_workspace_credential("W-1", workspace_account("feishu", "app1", "app_secret"))
    # 迁移后写入必须落到 workspace 作用域命名
    store_workspace_credential(
        "W-1", workspace_account("feishu", "app1", "app_secret"), SecretStr("new-secret")
    )
    assert store[("com.summitworkbench.credentials.W-1", "feishu:app1:app_secret")] == "new-secret"
