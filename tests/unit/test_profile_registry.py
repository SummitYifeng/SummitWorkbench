"""P0-07 profile registry / device identity 存储测试。

覆盖：registry.json 只存索引与 active workspace id（原子写）；profile config 独立存放
且原子写；本机文件 0600、目录 0700；device.json 首次生成后稳定、两个模拟 Home 不同 id、
重复加载不改写；同一 workspace 的 profile 在不同 Home 互不污染。
"""

from __future__ import annotations

import stat
import uuid
from pathlib import Path

from summit_workbench.config.app_support import app_support_dir
from summit_workbench.domain.workspace import DeviceRole, LocalProfile
from summit_workbench.repositories.profile_registry import (
    ensure_device_identity,
    load_device_identity,
    load_profile,
    load_registry,
    save_profile,
    set_active_profile,
)


def _home(tmp_path: Path, name: str = "home") -> Path:
    return tmp_path / name


def _profile(
    workspace_id: str,
    work_root: Path,
    *,
    role: DeviceRole = DeviceRole.SECONDARY,
) -> LocalProfile:
    return LocalProfile.model_validate(
        {
            "schema_version": 1,
            "workspace_id": workspace_id,
            "display_name": f"WS {workspace_id}",
            "work_root": str(work_root),
            "vault_dir": str(work_root / "_vault"),
            "device_role": role.value,
            "created_at": "2026-09-05T00:00:00Z",
        }
    )


def test_missing_registry_loads_empty_default(tmp_path) -> None:
    registry = load_registry(_home(tmp_path))
    assert registry.schema_version == 1
    assert registry.active_workspace_id is None
    assert registry.profiles == []


def test_registry_only_stores_index_and_active_id(tmp_path) -> None:
    home = _home(tmp_path)
    set_active_profile("W-A", home=home)
    set_active_profile("W-B", home=home)
    text = (app_support_dir(home) / "registry.json").read_text(encoding="utf-8")
    assert '"profiles"' in text
    assert '"active_workspace_id": "W-B"' in text
    registry = load_registry(home)
    assert registry.active_workspace_id == "W-B"
    assert set(registry.profiles) == {"W-A", "W-B"}


def test_set_active_none_clears_active_but_keeps_index(tmp_path) -> None:
    home = _home(tmp_path)
    set_active_profile("W-A", home=home)
    set_active_profile(None, home=home)
    registry = load_registry(home)
    assert registry.active_workspace_id is None
    assert registry.profiles == ["W-A"]


def test_local_files_are_0600_and_dirs_0700(tmp_path) -> None:
    home = _home(tmp_path)
    profile = _profile("workspace-1", tmp_path / "work-1")
    save_profile(profile, home=home)
    set_active_profile("W-1", home=home)
    for path in (
        app_support_dir(home) / "registry.json",
        app_support_dir(home) / "profiles" / "workspace-1" / "config.toml",
    ):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600, path
    profile_dir = app_support_dir(home) / "profiles" / "workspace-1"
    assert stat.S_IMODE(profile_dir.stat().st_mode) == 0o700
    # 原子写不留 .tmp 残留（P0-06 原语）
    assert not [p for p in profile_dir.iterdir() if p.suffix == ".tmp"]


def test_profile_config_roundtrip_and_isolation_between_homes(tmp_path) -> None:
    home_a = _home(tmp_path, "home-a")
    home_b = _home(tmp_path, "home-b")
    profile = _profile("workspace-1", tmp_path / "work-a")
    save_profile(profile, home=home_a)

    loaded = load_profile("workspace-1", home=home_a)
    assert loaded is not None
    assert loaded.workspace_id == profile.workspace_id
    assert loaded.work_root == profile.work_root
    assert loaded.display_name == profile.display_name
    # 同一 workspace 在另一台机器（另一 Home）不存在：本机 profile 不串用
    assert load_profile("workspace-1", home=home_b) is None


def test_two_profiles_coexist_without_cross_reading(tmp_path) -> None:
    home = _home(tmp_path)
    save_profile(_profile("workspace-A", tmp_path / "work-a"), home=home)
    save_profile(_profile("workspace-B", tmp_path / "work-b"), home=home)
    a = load_profile("workspace-A", home=home)
    b = load_profile("workspace-B", home=home)
    assert a is not None and b is not None
    assert a.work_root != b.work_root
    assert b.vault_dir == tmp_path / "work-b" / "_vault"


def test_device_identity_generated_once_and_stable(tmp_path) -> None:
    home = _home(tmp_path)
    first = ensure_device_identity(home, device_name="Studio")
    assert isinstance(uuid.UUID(first.device_id), uuid.UUID)  # UUID v4 形态
    second = ensure_device_identity(home, device_name="Renamed-Later")
    assert second.device_id == first.device_id  # 已有则稳定，不重新生成
    assert second.device_name == "Studio"  # 也不被后来的名字改写
    device_text = (app_support_dir(home) / "device.json").read_text(encoding="utf-8")
    assert first.device_id in device_text


def test_device_identity_differs_between_two_homes(tmp_path) -> None:
    home_a = _home(tmp_path, "studio-home")
    home_b = _home(tmp_path, "air-home")
    a = ensure_device_identity(home_a, device_name="Studio")
    b = ensure_device_identity(home_b, device_name="Air")
    assert a.device_id != b.device_id


def test_device_identity_file_is_0600(tmp_path) -> None:
    home = _home(tmp_path)
    ensure_device_identity(home, device_name="Studio")
    device_path = app_support_dir(home) / "device.json"
    assert stat.S_IMODE(device_path.stat().st_mode) == 0o600


def test_load_device_identity_missing_returns_none(tmp_path) -> None:
    assert load_device_identity(_home(tmp_path)) is None
