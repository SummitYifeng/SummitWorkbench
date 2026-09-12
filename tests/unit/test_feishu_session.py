"""FeishuSession 测试：刷新时轮换并回写 refresh_token；缺凭据时显式提示重新授权。"""

from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from summit_workbench.config.secrets import CredentialError, CredentialRef
from summit_workbench.providers.feishu import session as session_mod
from summit_workbench.providers.feishu.config import FeishuConfig
from summit_workbench.providers.feishu.errors import FeishuAuthError, FeishuConfigError
from summit_workbench.providers.feishu.session import FeishuSession

CFG = FeishuConfig(app_id="app1", redirect_uri="http://localhost/cb")


def _mock_client(payload) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_access_token_refreshes_and_persists_rotated_rt(tmp_path, monkeypatch):
    monkeypatch.setenv("WORK_ROOT", str(tmp_path))  # 工作区锁隔离到 tmp，勿触真实 home
    stored: dict[str, str] = {}

    def fake_resolve(ref: CredentialRef) -> SecretStr:
        # app_secret 与当前 refresh_token 都来自 Keychain
        return SecretStr("app-secret" if "app-secret" in ref.service else "old-rt")

    def fake_store(ref: CredentialRef, value: SecretStr) -> None:
        stored[ref.service] = value.get_secret_value()

    monkeypatch.setattr(session_mod, "resolve_credential", fake_resolve)
    monkeypatch.setattr(session_mod, "store_credential", fake_store)

    client = _mock_client(
        {"access_token": "new-access", "expires_in": 7200, "refresh_token": "rotated-rt"}
    )
    token = FeishuSession(CFG).access_token(client=client)

    assert token.get_secret_value() == "new-access"
    # 轮换出的新 refresh_token 已回写 Keychain
    assert stored["summit-workbench-feishu-refresh-token"] == "rotated-rt"


def test_access_token_without_stored_rt_asks_reauthorize(tmp_path, monkeypatch):
    monkeypatch.setenv("WORK_ROOT", str(tmp_path))

    def fake_resolve(ref: CredentialRef) -> SecretStr:
        if "refresh-token" in ref.service:
            raise CredentialError("not found")
        return SecretStr("app-secret")

    monkeypatch.setattr(session_mod, "resolve_credential", fake_resolve)

    with pytest.raises(FeishuAuthError) as ei:
        FeishuSession(CFG).access_token(client=_mock_client({}))
    assert ei.value.needs_reauthorize is True


def test_complete_authorization_requires_offline_access(tmp_path, monkeypatch):
    monkeypatch.setenv("WORK_ROOT", str(tmp_path))
    monkeypatch.setattr(session_mod, "resolve_credential", lambda ref: SecretStr("app-secret"))
    monkeypatch.setattr(session_mod, "store_credential", lambda ref, value: None)

    # 返回不含 refresh_token → 未授予 offline_access → 显式报错
    client = _mock_client({"access_token": "a", "expires_in": 7200})
    with pytest.raises(FeishuAuthError) as ei:
        FeishuSession(CFG).complete_authorization("code", client=client)
    assert "offline_access" in str(ei.value)


def test_complete_authorization_stores_refresh_token(tmp_path, monkeypatch):
    monkeypatch.setenv("WORK_ROOT", str(tmp_path))
    stored: dict[str, str] = {}
    monkeypatch.setattr(session_mod, "resolve_credential", lambda ref: SecretStr("app-secret"))
    monkeypatch.setattr(
        session_mod,
        "store_credential",
        lambda ref, value: stored.__setitem__(ref.service, value.get_secret_value()),
    )

    client = _mock_client({"access_token": "a", "expires_in": 7200, "refresh_token": "first-rt"})
    FeishuSession(CFG).complete_authorization("code", client=client)
    assert stored["summit-workbench-feishu-refresh-token"] == "first-rt"


def test_workspace_session_migrates_legacy_app_secret_before_authorization(tmp_path, monkeypatch):
    monkeypatch.setenv("WORK_ROOT", str(tmp_path))
    cfg = FeishuConfig(
        app_id="app1",
        redirect_uri="http://localhost/cb",
        workspace_id="workspace-1",
    )
    stored: dict[tuple[str, str], str] = {}

    def resolve(ref: CredentialRef) -> SecretStr:
        if ref == cfg.app_secret_ref:
            raise CredentialError("scoped app secret missing")
        if ref == cfg.legacy_app_secret_ref:
            return SecretStr("legacy-app-secret")
        raise CredentialError("unexpected credential")

    monkeypatch.setattr(session_mod, "resolve_credential", resolve)
    monkeypatch.setattr(session_mod, "resolve_legacy_credential_for_migration", resolve)
    monkeypatch.setattr(
        session_mod,
        "store_credential",
        lambda ref, value: stored.__setitem__((ref.service, ref.account), value.get_secret_value()),
    )

    client = _mock_client({"access_token": "a", "expires_in": 7200, "refresh_token": "first-rt"})
    FeishuSession(cfg).complete_authorization("code", client=client)

    assert stored[(cfg.app_secret_ref.service, cfg.app_secret_ref.account)] == "legacy-app-secret"
    assert stored[(cfg.refresh_token_ref.service, cfg.refresh_token_ref.account)] == "first-rt"


# ---- 内置默认 app_secret（分发包零预置授权）----


def _raise_missing(ref: CredentialRef) -> SecretStr:
    raise CredentialError("not found")


def test_app_secret_falls_back_to_bundled_when_keychain_empty(tmp_path, monkeypatch):
    """同事干净机器：Keychain 没有 app_secret，用包内内置默认值完成换取。"""
    monkeypatch.setenv("WORK_ROOT", str(tmp_path))
    bundled = tmp_path / "feishu-defaults.json"
    bundled.write_text(
        '{"app_id": "cli_bundled", "app_secret": "bundled-secret"}', encoding="utf-8"
    )
    monkeypatch.setenv("WB_FEISHU_DEFAULTS", str(bundled))
    monkeypatch.setattr(session_mod, "resolve_credential", _raise_missing)
    monkeypatch.setattr(session_mod, "resolve_legacy_credential_for_migration", _raise_missing)

    assert FeishuSession(CFG)._app_secret().get_secret_value() == "bundled-secret"


def test_keychain_app_secret_wins_over_bundled(tmp_path, monkeypatch):
    """用户/管理员自己存的 Keychain 条目始终优先于内置默认值。"""
    monkeypatch.setenv("WORK_ROOT", str(tmp_path))
    bundled = tmp_path / "feishu-defaults.json"
    bundled.write_text(
        '{"app_id": "cli_bundled", "app_secret": "bundled-secret"}', encoding="utf-8"
    )
    monkeypatch.setenv("WB_FEISHU_DEFAULTS", str(bundled))
    monkeypatch.setattr(session_mod, "resolve_credential", lambda ref: SecretStr("keychain-secret"))

    assert FeishuSession(CFG)._app_secret().get_secret_value() == "keychain-secret"


def test_app_secret_missing_everywhere_raises_config_error(tmp_path, monkeypatch):
    """没有内置默认值且 Keychain 为空时，保持原有的显式报错。"""
    monkeypatch.setenv("WORK_ROOT", str(tmp_path))
    monkeypatch.setenv("WB_FEISHU_DEFAULTS", str(tmp_path / "absent.json"))
    monkeypatch.setattr(session_mod, "resolve_credential", _raise_missing)
    monkeypatch.setattr(session_mod, "resolve_legacy_credential_for_migration", _raise_missing)

    with pytest.raises(FeishuConfigError) as excinfo:
        FeishuSession(CFG)._app_secret()
    assert "security add-generic-password" in str(excinfo.value)
