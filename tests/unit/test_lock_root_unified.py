"""P0-06 锁根统一测试：WorkspacePaths 是单一解析入口。

背景：此前 web/brief/Feishu 锁在 ``vault_dir.parent``，sync 锁在 ``work_root``，
Feishu session 又锁在默认 env ``resolve_work_root()``——自定义 vault 或仅配置文件
设置 work_root 时三者会分裂到不同的 ``.wb.lock``。本测试锁定：同一 workspace 的
web、brief、Feishu refresh、sync 解析出同一个 lock root（同一 ``.wb.lock`` 文件）。
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from summit_workbench.config.locking import lock_file_path
from summit_workbench.config.paths import resolve_work_paths
from summit_workbench.config.settings import load_settings
from summit_workbench.providers.feishu import session as session_mod
from summit_workbench.providers.feishu.config import FeishuConfig
from summit_workbench.providers.feishu.session import FeishuSession

CFG = FeishuConfig(app_id="app1", redirect_uri="http://localhost/cb")


def _mock_client(payload: dict[str, object]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _stub_keychain_and_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        session_mod,
        "resolve_credential",
        lambda ref: SecretStr("app-secret" if "app-secret" in ref.service else "old-rt"),
    )
    monkeypatch.setattr(session_mod, "store_credential", lambda ref, value: None)


def _no_config_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("WORK_ROOT", raising=False)
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "nonexistent.toml"))


def test_default_vault_lock_root_is_work_root(monkeypatch, tmp_path) -> None:
    """默认布局（vault=<work_root>/_vault）：lock_root == vault 容器 == work_root。"""
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "Work"))
    ws = load_settings().work_paths()
    assert ws.vault_dir == tmp_path / "Work" / "_vault"
    assert ws.lock_root == tmp_path / "Work"
    assert ws.lock_root == ws.vault_dir.parent
    assert lock_file_path(ws.lock_root) == tmp_path / "Work" / ".wb.lock"


def test_custom_vault_unifies_web_brief_feishu_sync_lock_root(tmp_path) -> None:
    """自定义 vault（非 _vault 名）下，web/brief/Feishu/sync 解析同一 .wb.lock。"""
    work = tmp_path / "Work"
    vault = work / "CustomVault"
    ws = resolve_work_paths(work_root=work, vault_dir=vault)
    assert ws.lock_root == work == vault.parent

    # web：WebContext.lock_root 来自同一解析入口
    from summit_workbench.webapp.app import WebContext

    ctx = WebContext(
        vault_dir=ws.vault_dir, work_root=ws.work_root, timezone="UTC", lock_root=ws.lock_root
    )
    assert ctx.lock_root == ws.lock_root

    # brief 写者：锁在 vault 容器（= lock_root）；sync：锁在 work_root（= lock_root）
    assert ws.vault_dir.parent == ws.lock_root
    canonical = lock_file_path(ws.lock_root)
    assert lock_file_path(ws.vault_dir.parent) == canonical  # brief/web 写者
    assert lock_file_path(ws.work_root) == canonical  # sync
    assert str(canonical).endswith(".wb.lock")


def test_web_pool_feishu_session_receives_ctx_lock_root(tmp_path, monkeypatch) -> None:
    """Web 面板的 Feishu session（含 refresh）从 WebContext 取 lock root，不再默认。"""
    captured: dict[str, object] = {}

    class FakeSession:
        def __init__(self, _cfg: object, lock_root: Path | None = None) -> None:
            captured["lock_root"] = lock_root

        def access_token(self) -> str:
            return "token"

    class FakeClient:
        def __init__(self, _cfg: object, _token: object) -> None:
            pass

        def close(self) -> None:
            pass

    monkeypatch.setattr("summit_workbench.providers.feishu.FeishuSession", FakeSession)
    monkeypatch.setattr("summit_workbench.providers.feishu.FeishuClient", FakeClient)
    monkeypatch.setattr("summit_workbench.providers.feishu.load_feishu_config", lambda: object())

    from summit_workbench.webapp.app import WebContext, create_app

    lock_root = tmp_path / "ws-root"
    ctx = WebContext(
        vault_dir=tmp_path / "ws-root" / "CustomVault",
        work_root=lock_root,
        timezone="UTC",
        lock_root=lock_root,
    )
    app = create_app(ctx, static_dir=tmp_path / "no-static")
    app.state.feishu_clients.user_client()
    assert captured["lock_root"] == lock_root


def test_brief_feishu_refresh_uses_workspace_lock_root(tmp_path, monkeypatch) -> None:
    """brief 流程构建飞书事实源时的 Feishu refresh 拿到工作区 lock root。"""
    captured: dict[str, object] = {}

    class FakeSession:
        def __init__(self, _cfg: object, lock_root: Path | None = None) -> None:
            captured["lock_root"] = lock_root

        def access_token(self) -> SecretStr:
            return SecretStr("token")

    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

    monkeypatch.setattr("summit_workbench.workflows.brief.runner.FeishuSession", FakeSession)
    monkeypatch.setattr("summit_workbench.workflows.brief.runner.FeishuClient", FakeClient)
    monkeypatch.setattr("summit_workbench.workflows.brief.runner.load_feishu_config", lambda: CFG)

    from summit_workbench.workflows.brief.runner import build_facts_source

    lock_root = tmp_path / "brief-root"
    facts, outcome = build_facts_source("2026-09-05", "UTC", lock_root=lock_root)
    assert captured["lock_root"] == lock_root
    assert outcome.reason is None
    assert facts is not None


def test_feishu_refresh_locks_configured_root_not_env_default(monkeypatch, tmp_path) -> None:
    """Feishu refresh 不再锁默认 env work root：lock_root 显式给定时以它为准。"""
    _no_config_file(monkeypatch, tmp_path)
    env_root = tmp_path / "env-root"
    monkeypatch.setenv("WORK_ROOT", str(env_root))  # 误导性 env 默认
    _stub_keychain_and_auth(monkeypatch)

    configured = tmp_path / "configured-workspace"
    client = _mock_client({"access_token": "t", "expires_in": 7200, "refresh_token": "rt2"})
    session = FeishuSession(CFG, lock_root=configured)
    token = session.access_token(client=client)
    assert token.get_secret_value() == "t"
    assert (configured / ".wb.lock").is_file()
    assert not (env_root / ".wb.lock").exists(), "不得再锁到默认/环境 work root"


def test_feishu_session_without_lock_root_falls_back_to_work_root_env(
    monkeypatch, tmp_path
) -> None:
    """未显式给 lock_root 时保持兼容：退回 WORK_ROOT 解析（CLI 机器级命令语义）。"""
    _no_config_file(monkeypatch, tmp_path)
    env_root = tmp_path / "env-root"
    monkeypatch.setenv("WORK_ROOT", str(env_root))
    _stub_keychain_and_auth(monkeypatch)

    client = _mock_client({"access_token": "t", "expires_in": 7200, "refresh_token": "rt2"})
    FeishuSession(CFG).access_token(client=client)
    assert (env_root / ".wb.lock").is_file()


def test_feishu_complete_authorization_uses_configured_lock_root(monkeypatch, tmp_path) -> None:
    """授权写回（complete_authorization）同样锁在配置的 lock root。"""
    _no_config_file(monkeypatch, tmp_path)
    env_root = tmp_path / "env-root"
    monkeypatch.setenv("WORK_ROOT", str(env_root))
    _stub_keychain_and_auth(monkeypatch)

    configured = tmp_path / "configured-workspace"
    client = _mock_client({"access_token": "t", "expires_in": 7200, "refresh_token": "rt-new"})
    tokens = FeishuSession(CFG, lock_root=configured).complete_authorization("code", client=client)
    assert tokens.refresh_token is not None
    assert tokens.refresh_token.get_secret_value() == "rt-new"
    assert (configured / ".wb.lock").is_file()
    assert not (env_root / ".wb.lock").exists()
