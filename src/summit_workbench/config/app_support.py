"""Application Support 布局（P0-07）。

本机（不随 Git 同步）的 workspace/profile/device 状态统一放在
``~/Library/Application Support/SummitWorkbench/``：

.. code-block:: text

    <home>/Library/Application Support/SummitWorkbench/
    ├── registry.json                     # 本机 profile 索引（atomic, 0600）
    ├── device.json                       # 本机 device_id（atomic, 0600）
    ├── profiles/<workspace_id>/
    │   ├── config.toml                   # 本机路径与非秘密配置（atomic, 0600）
    │   └── runtime/                      # 端口/实例/会话等短期状态（P0-12 用）
    └── backups/                          # 配置/迁移/升级前快照（P0-08 起，不同步）

    <home>/Library/Logs/SummitWorkbench/  # 本机滚动日志

路径一律从 home 派生（默认 :func:`Path.home`，测试可传临时 home），绝不硬编码
用户名（NFR-3）。本机文件权限约定：文件 0600、目录 0700（P0-07）。
"""

from __future__ import annotations

from pathlib import Path

_APP_SUPPORT_DIRNAME = "SummitWorkbench"

# 本机敏感/个人文件与目录权限（P0-07 要求 8）。
PROFILE_FILE_MODE = 0o600
PROFILE_DIR_MODE = 0o700


def home_dir() -> Path:
    """当前用户 home 目录（默认值来源；测试通过显式 ``home`` 参数或 HOME env 隔离）。"""
    return Path.home()


def app_support_dir(home: Path | None = None) -> Path:
    """本机 SummitWorkbench 状态根（macOS Application Support）。"""
    return (home or home_dir()) / "Library" / "Application Support" / _APP_SUPPORT_DIRNAME


def logs_dir(home: Path | None = None) -> Path:
    """本机 SummitWorkbench 日志根。"""
    return (home or home_dir()) / "Library" / "Logs" / _APP_SUPPORT_DIRNAME


def registry_file(home: Path | None = None) -> Path:
    """本机 profile 索引文件（不同步）。"""
    return app_support_dir(home) / "registry.json"


def device_file(home: Path | None = None) -> Path:
    """本机 device 身份文件（不同步）。"""
    return app_support_dir(home) / "device.json"


def profiles_dir(home: Path | None = None) -> Path:
    """本机 profile 目录。"""
    return app_support_dir(home) / "profiles"


def profile_dir(workspace_id: str, home: Path | None = None) -> Path:
    """某 workspace 的本机 profile 目录（含该 workspace 的本地配置）。"""
    return profiles_dir(home) / workspace_id


def profile_config_file(workspace_id: str, home: Path | None = None) -> Path:
    """某 workspace 的本地 profile 配置文件（TOML，非秘密）。"""
    return profile_dir(workspace_id, home) / "config.toml"


def runtime_dir(workspace_id: str, home: Path | None = None) -> Path:
    """某 workspace 的短期运行时状态目录（端口/实例/会话，P0-12 用）。"""
    return profile_dir(workspace_id, home) / "runtime"


def backups_dir(home: Path | None = None) -> Path:
    """配置/迁移/升级前备份根目录（不同步；P0-08 onboarding 用）。"""
    return app_support_dir(home) / "backups"
