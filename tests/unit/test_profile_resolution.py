"""P0-07 active profile 解析入口测试（config/profiles.py）。

解析优先级：registry active profile（权威）> env WORK_ROOT（development/test 兼容，
仅无 profile 时）> onboarding-required。空安装不访问/创建 ``~/Documents/Work``；
不因解析调用而创建 Application Support 目录。
"""

from __future__ import annotations

from pathlib import Path

from summit_workbench.config.app_support import app_support_dir
from summit_workbench.config.profiles import (
    ProfileResolutionState,
    resolve_workspace,
)
from summit_workbench.domain.workspace import DeviceRole, LocalProfile
from summit_workbench.repositories.profile_registry import save_profile, set_active_profile


def _profile(workspace_id: str, home: Path, *, work_name: str = "work") -> LocalProfile:
    work_root = home / work_name
    return LocalProfile.model_validate(
        {
            "schema_version": 1,
            "workspace_id": workspace_id,
            "display_name": workspace_id,
            "work_root": str(work_root),
            "vault_dir": str(work_root / "_vault"),
            "device_role": DeviceRole.SECONDARY.value,
            "created_at": "2026-09-05T00:00:00Z",
        }
    )


def test_empty_install_is_onboarding_required_and_touches_nothing(tmp_path, monkeypatch) -> None:
    """空安装：无 profile、无 WORK_ROOT → onboarding-required，不碰真实目录。"""
    monkeypatch.delenv("WORK_ROOT", raising=False)
    home = tmp_path / "fake-home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "nonexistent.toml"))

    resolution = resolve_workspace()
    assert resolution.state is ProfileResolutionState.ONBOARDING_REQUIRED
    assert resolution.profile is None
    assert resolution.paths is None
    assert resolution.reason  # 可解释的原因
    # 解析本身不得创建任何目录（App Support 或默认 ~/Documents/Work）
    assert not (home / "Library" / "Application Support" / "SummitWorkbench").exists()
    assert not (home / "Documents" / "Work").exists()


def test_env_work_root_is_dev_fallback_when_no_profile(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "dev-work"))
    home = tmp_path / "fake-home"
    monkeypatch.setenv("HOME", str(home))
    resolution = resolve_workspace()
    assert resolution.state is ProfileResolutionState.ENV_COMPAT
    assert resolution.profile is None
    assert resolution.paths is not None
    assert resolution.paths.work_root == tmp_path / "dev-work"
    assert resolution.paths.vault_dir == tmp_path / "dev-work" / "_vault"
    assert resolution.paths.lock_root == tmp_path / "dev-work"


def test_active_profile_wins_over_env(tmp_path, monkeypatch) -> None:
    """有 active profile 时以 profile 为准，env WORK_ROOT 只是 dev 回退。"""
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "env-work"))  # 误导性 env
    home = tmp_path / "real-home"
    monkeypatch.setenv("HOME", str(home))
    profile = _profile("workspace-active", home)
    save_profile(profile, home=home)
    set_active_profile("workspace-active", home=home)

    resolution = resolve_workspace()
    assert resolution.state is ProfileResolutionState.ACTIVE
    assert resolution.profile is not None
    assert resolution.profile.workspace_id == "workspace-active"
    assert resolution.paths is not None
    assert resolution.paths.work_root == home / "work"
    assert resolution.paths.vault_dir == home / "work" / "_vault"
    assert resolution.paths.lock_root == resolution.paths.vault_dir.parent


def test_onboarding_when_env_fallback_disabled(tmp_path, monkeypatch) -> None:
    """显式关闭 env 回退且无 profile → onboarding-required（production 语义）。"""
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "env-work"))
    home = tmp_path / "fake-home"
    monkeypatch.setenv("HOME", str(home))
    resolution = resolve_workspace(allow_env_fallback=False)
    assert resolution.state is ProfileResolutionState.ONBOARDING_REQUIRED


def test_registry_missing_on_home_b_is_onboarding(tmp_path, monkeypatch) -> None:
    """profile 只存在于 home A；home B（同一机器别的 Home）→ onboarding-required。"""
    home_a = tmp_path / "home-a"
    home_b = tmp_path / "home-b"
    save_profile(_profile("workspace-A", home_a), home=home_a)
    set_active_profile("workspace-A", home=home_a)
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "unrelated"))
    monkeypatch.setenv("HOME", str(home_b))
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "nonexistent.toml"))
    # 允许 env 回退时 B 是 env-compat（B 上没有 A 的 profile，但也不读 A 的 registry）
    resolution = resolve_workspace(allow_env_fallback=False)
    assert resolution.state is ProfileResolutionState.ONBOARDING_REQUIRED
    assert (app_support_dir(home_a) / "registry.json").is_file()  # A 不受影响


def test_active_profile_paths_lock_root_matches_vault_container(tmp_path, monkeypatch) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    profile = _profile("workspace-lock", home, work_name="CustomRoot")
    save_profile(profile, home=home)
    set_active_profile("workspace-lock", home=home)
    resolution = resolve_workspace()
    assert resolution.state is ProfileResolutionState.ACTIVE
    assert resolution.paths is not None
    # lock_root = vault 容器（P0-06 单一解析规则），与 work root 形态一致
    assert resolution.paths.lock_root == resolution.paths.vault_dir.parent == home / "CustomRoot"
