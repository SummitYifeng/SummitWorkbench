"""P0-07 Application Support 布局路径测试。

``~/Library/Application Support/SummitWorkbench/`` 下：registry.json / device.json /
profiles/<workspace_id>/config.toml / runtime；日志在 ``~/Library/Logs/SummitWorkbench/``。
路径一律从 home 派生，绝不硬编码用户名（NFR-3）。
"""

from __future__ import annotations

from pathlib import Path

from summit_workbench.config.app_support import (
    app_support_dir,
    device_file,
    logs_dir,
    profile_config_file,
    profile_dir,
    profiles_dir,
    registry_file,
    runtime_dir,
)


def _home(tmp_path: Path) -> Path:
    return tmp_path / "fake-home"


def test_app_support_dir_under_home_library(tmp_path) -> None:
    home = _home(tmp_path)
    assert app_support_dir(home) == home / "Library" / "Application Support" / "SummitWorkbench"


def test_registry_and_device_files_live_under_app_support(tmp_path) -> None:
    home = _home(tmp_path)
    root = app_support_dir(home)
    assert registry_file(home) == root / "registry.json"
    assert device_file(home) == root / "device.json"


def test_profile_files_are_per_workspace_id(tmp_path) -> None:
    home = _home(tmp_path)
    assert profiles_dir(home) == app_support_dir(home) / "profiles"
    assert profile_dir("W-1", home) == app_support_dir(home) / "profiles" / "W-1"
    assert profile_config_file("W-1", home) == profile_dir("W-1", home) / "config.toml"
    assert profile_dir("W-2", home) != profile_dir("W-1", home)
    assert runtime_dir("W-1", home) == profile_dir("W-1", home) / "runtime"


def test_logs_dir_under_library_logs(tmp_path) -> None:
    home = _home(tmp_path)
    assert logs_dir(home) == home / "Library" / "Logs" / "SummitWorkbench"


def test_paths_contain_no_hardcoded_username(tmp_path) -> None:
    home = _home(tmp_path)
    for path in (
        app_support_dir(home),
        registry_file(home),
        device_file(home),
        profile_config_file("W-1", home),
    ):
        assert "/Users/" not in str(path)
