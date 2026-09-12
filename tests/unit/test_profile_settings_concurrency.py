"""provider 设置的并发安全与授权后续落盘。

真实场景（2026-09-12 现场发现）：向导会先后写「模型」段与「飞书」段，而授权回调与模型
验证可能几乎同时到达。`update_provider_settings` 原本是无锁的读-改-写，后写者会基于自己
读到的旧快照落盘，**静默丢掉另一段**——现象是「授权明明成功，设置页却显示未连接」。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from summit_workbench.domain.workspace import LocalProfile
from summit_workbench.providers.feishu.session import FeishuSession
from summit_workbench.repositories.profile_registry import load_profile as real_load
from summit_workbench.repositories.profile_registry import save_profile
from summit_workbench.workflows.profile_settings import (
    ProfileSettingsError,
    update_provider_settings,
)
from summit_workbench.workflows.settings_connections import complete_feishu_authorization

WS = "ws-settings-concurrency"

MODEL_SETTINGS: dict[str, object] = {
    "capability": "shared",
    "credential_capability": "shared",
    "model_id": "deepseek-v4-flash",
    "base_url": "https://api.deepseek.com/v1",
    "credential_account": "shared",
}
FEISHU_SETTINGS: dict[str, object] = {
    "app_id": "cli_flow",
    "redirect_uri": "http://localhost:8765/callback",
    "scopes": ["offline_access"],
}


def _seed_profile(home: Path) -> Path:
    save_profile(
        LocalProfile.model_validate(
            {
                "schema_version": 1,
                "workspace_id": WS,
                "display_name": "并发测试",
                "work_root": str(home / "Work"),
                "vault_dir": str(home / "Work" / "_vault"),
                "created_at": "2026-09-12T00:00:00Z",
            }
        ),
        home=home,
    )
    return (
        home
        / "Library"
        / "Application Support"
        / "SummitWorkbench"
        / "profiles"
        / WS
        / "config.toml"
    )


def test_concurrent_provider_writes_keep_both_sections(tmp_path: Path, monkeypatch) -> None:
    """模型段与飞书段并发写入时，两段都必须留存（回归：曾静默丢失飞书段）。"""
    home = tmp_path / "home"
    config_file = _seed_profile(home)

    real_load_fn = real_load
    rival_started = threading.Event()
    rival = threading.Thread(
        target=lambda: update_provider_settings(
            home=home, workspace_id=WS, provider="model", settings=MODEL_SETTINGS, secret=None
        )
    )

    def load_then_race(workspace_id: str, home: Path | None = None) -> LocalProfile | None:
        profile = real_load_fn(workspace_id, home=home)
        if not rival_started.is_set():
            rival_started.set()
            # 在「已读取、尚未落盘」的窗口里放进对手写入。
            # 有互斥时对手会在这里被挡住，join 超时返回；没有互斥时对手会在窗口内写完。
            rival.start()
            rival.join(timeout=0.5)
        return profile

    monkeypatch.setattr("summit_workbench.workflows.profile_settings.load_profile", load_then_race)

    update_provider_settings(
        home=home, workspace_id=WS, provider="feishu", settings=FEISHU_SETTINGS, secret=None
    )
    rival.join(timeout=5)
    assert not rival.is_alive()

    text = config_file.read_text(encoding="utf-8")
    assert "[feishu]" in text, "飞书段被并发写入覆盖"
    assert "[models.shared]" in text, "模型段被并发写入覆盖"


def test_missing_profile_is_reported_without_creating_profile_dir(tmp_path: Path) -> None:
    """锁根不能落在 profile 目录下：失败路径不该造出一个空 profile。"""
    home = tmp_path / "home"
    with pytest.raises(ProfileSettingsError):
        update_provider_settings(
            home=home,
            workspace_id="ws-does-not-exist",
            provider="feishu",
            settings=FEISHU_SETTINGS,
            secret=None,
        )
    profile_dir = (
        home
        / "Library"
        / "Application Support"
        / "SummitWorkbench"
        / "profiles"
        / "ws-does-not-exist"
    )
    assert not profile_dir.exists()


def test_complete_feishu_authorization_persists_non_secret_settings(
    tmp_path: Path, monkeypatch
) -> None:
    """授权成功后必须把非秘密的飞书设置写进 profile，否则设置页会显示「未连接」。"""
    home = tmp_path / "home"
    config_file = _seed_profile(home)
    bundled = tmp_path / "feishu-defaults.json"
    bundled.write_text(
        json.dumps(
            {
                "app_id": "cli_bundled",
                "app_secret": "s",
                "redirect_uri": "http://localhost:8765/callback",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("WB_FEISHU_DEFAULTS", str(bundled))
    # 只替换网络层的令牌换取，其余（配置解析、profile 落盘）走真实代码
    monkeypatch.setattr(
        FeishuSession, "complete_authorization", lambda self, code, *, client=None: None
    )

    complete_feishu_authorization(
        config_file=config_file,
        workspace_id=WS,
        lock_root=None,
        code="fake-code",
        home=home,
    )

    text = config_file.read_text(encoding="utf-8")
    assert "[feishu]" in text
    assert 'app_id = "cli_bundled"' in text
    assert "offline_access" in text
