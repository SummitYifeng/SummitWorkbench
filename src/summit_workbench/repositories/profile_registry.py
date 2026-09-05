"""本机 profile registry / device identity 存储（P0-07）。

- ``registry.json`` 只存 profile 索引与 active workspace id（本机、不同步）；
- 每个 workspace 的本地档案独立存放在 ``profiles/<workspace_id>/config.toml``
  （TOML，扁平字段，原子写；含本机路径、设备角色等非同步信息）；
- ``device.json`` 存本机安装级 device id，首次运行生成一次、之后稳定。

写入全部走 P0-06 原子原语（唯一临时文件 + fsync），本机文件 0600、目录 0700。
profile 配置只含非秘密项；凭据一律以 workspace 作用域 Keychain 引用承载（secrets.py）。
"""

from __future__ import annotations

import json
import os
import socket
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, ValidationError

from summit_workbench.config.app_support import (
    PROFILE_DIR_MODE,
    PROFILE_FILE_MODE,
    app_support_dir,
    device_file,
    profile_config_file,
    profile_dir,
    profiles_dir,
    registry_file,
)
from summit_workbench.domain.workspace import DeviceIdentity, LocalProfile
from summit_workbench.repositories._atomic import atomic_write_text

_REGISTRY_SCHEMA_VERSION = 1

_PROFILE_TOML_KEYS = (
    "schema_version",
    "workspace_id",
    "display_name",
    "work_root",
    "vault_dir",
    "device_role",
    "created_at",
    "last_opened_at",
    "timezone",
    "user_email",
    "git_username",
)


class ProfileRegistry(BaseModel):
    """本机 profile 索引：只存 id 列表与 active workspace id（不存路径等详情）。"""

    model_config = ConfigDict(extra="ignore")

    schema_version: int = _REGISTRY_SCHEMA_VERSION
    active_workspace_id: str | None = None
    profiles: list[str] = []


# ---- 目录/文件辅助 ----


def _ensure_dir(path: Path, mode: int = PROFILE_DIR_MODE) -> None:
    """按约定权限建目录（umask 之外的权限差用 chmod 补足，保证 0700）。"""
    path.mkdir(mode=mode, parents=True, exist_ok=True)
    os.chmod(path, mode)


def _app_support_tree(home: Path | None) -> None:
    root = app_support_dir(home)
    _ensure_dir(root)
    _ensure_dir(profiles_dir(home))


# ---- registry.json ----


def load_registry(home: Path | None = None) -> ProfileRegistry:
    """读本机 registry；文件缺失时返回空默认（尚未 onboarding 是正常态）。"""
    path = registry_file(home)
    if not path.is_file():
        return ProfileRegistry()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return ProfileRegistry.model_validate(raw)
    except (ValueError, ValidationError) as exc:
        raise ValueError(f"registry.json 损坏，请检查 {path}") from exc


def save_registry(registry: ProfileRegistry, home: Path | None = None) -> Path:
    """原子写本机 registry（0600）。"""
    _app_support_tree(home)
    path = registry_file(home)
    payload = registry.model_dump(mode="json")
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    atomic_write_text(path, text, new_mode=PROFILE_FILE_MODE)
    return path


def set_active_profile(workspace_id: str | None, home: Path | None = None) -> Path:
    """把某 workspace 设为 active（None 则清除 active，索引保留）。"""
    registry = load_registry(home)
    registry.active_workspace_id = workspace_id
    if workspace_id is not None and workspace_id not in registry.profiles:
        registry.profiles.append(workspace_id)
    return save_registry(registry, home=home)


def profile_ids(home: Path | None = None) -> list[str]:
    """本机已建档的 workspace id 列表。"""
    return list(load_registry(home).profiles)


def active_profile_id(home: Path | None = None) -> str | None:
    return load_registry(home).active_workspace_id


def drop_profile(workspace_id: str, home: Path | None = None) -> bool:
    """删除本机某 workspace 的 profile（索引项 + 独立配置 + active 指向）。

    用于 onboarding 失败回滚 / 显式移除本机档案。**绝不删除 vault 或其它用户目录**，
    只清理本机 Application Support 内由本模块创建的内容；返回是否确实删除了内容。
    """
    removed = False
    registry = load_registry(home)
    if workspace_id in registry.profiles or registry.active_workspace_id == workspace_id:
        registry.profiles = [item for item in registry.profiles if item != workspace_id]
        if registry.active_workspace_id == workspace_id:
            registry.active_workspace_id = None
        save_registry(registry, home=home)
        removed = True
    config = profile_config_file(workspace_id, home)
    if config.is_file():
        config.unlink()
        removed = True
    directory = profile_dir(workspace_id, home)
    if directory.is_dir():
        try:
            directory.rmdir()  # 只删空目录；若已写入 runtime 等内容则保留
        except OSError:
            pass
    return removed


# ---- profiles/<id>/config.toml ----


def _toml_value(value: object) -> str | None:
    """把扁平 profile 值序列化成 TOML 标量（字符串经 json.dumps 得到合法 basic string）。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, datetime):
        return json.dumps(value.isoformat())
    if isinstance(value, list):
        rendered = [_toml_value(item) for item in value]
        if all(item is not None for item in rendered):
            return "[" + ", ".join(item for item in rendered if item is not None) + "]"
        return None
    return json.dumps(str(value))


def _toml_key(key: str) -> str:
    """Render a TOML key without making unknown forward-compatible keys unsafe."""
    return key if key.replace("_", "").isalnum() and not key[:1].isdigit() else json.dumps(key)


def _toml_table_lines(table: dict[str, object], prefix: tuple[str, ...]) -> list[str]:
    """Render a small nested TOML table used by forward-compatible profile extras."""
    lines: list[str] = []
    scalars: list[tuple[str, object]] = []
    nested: list[tuple[str, dict[str, object]]] = []
    for key, value in table.items():
        if isinstance(value, dict):
            nested.append((key, value))
        else:
            scalars.append((key, value))
    for key, value in sorted(scalars):
        rendered = _toml_value(value)
        if rendered is not None:
            lines.append(f"{_toml_key(key)} = {rendered}")
    for key, child in sorted(nested):
        if lines:
            lines.append("")
        section = ".".join((*prefix, _toml_key(key)))
        lines.append(f"[{section}]")
        lines.extend(_toml_table_lines(child, (*prefix, _toml_key(key))))
    return lines


def profile_to_toml(profile: LocalProfile) -> str:
    """把 LocalProfile 序列化为 TOML，并保留未知的前向兼容字段。"""
    dump = profile.model_dump(mode="json")
    lines: list[str] = []
    for key in _PROFILE_TOML_KEYS:
        if key not in dump:
            continue
        rendered = _toml_value(dump[key])
        if rendered is None:
            continue
        lines.append(f"{key} = {rendered}")
    extras = {
        key: value
        for key, value in dump.items()
        if key not in _PROFILE_TOML_KEYS and value is not None
    }
    if extras:
        if lines:
            lines.append("")
        lines.extend(_toml_table_lines(extras, ()))
    return "\n".join(lines) + "\n"


def save_profile(profile: LocalProfile, home: Path | None = None) -> Path:
    """原子写某 workspace 的本机 profile 配置（目录 0700、文件 0600）。"""
    _app_support_tree(home)
    directory = profile_dir(profile.workspace_id, home)
    _ensure_dir(directory)
    path = profile_config_file(profile.workspace_id, home)
    atomic_write_text(path, profile_to_toml(profile), new_mode=PROFILE_FILE_MODE)
    return path


def load_profile(workspace_id: str, home: Path | None = None) -> LocalProfile | None:
    """读某 workspace 的本机 profile；不存在返回 None，损坏抛 ValueError。"""
    path = profile_config_file(workspace_id, home)
    if not path.is_file():
        return None
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        return LocalProfile.model_validate(raw)
    except (ValueError, ValidationError) as exc:
        raise ValueError(f"profile 配置损坏：{path}") from exc


# ---- device.json ----


def _write_device_identity(identity: DeviceIdentity, home: Path | None) -> Path:
    _app_support_tree(home)
    path = device_file(home)
    payload = identity.model_dump(mode="json")
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    atomic_write_text(path, text, new_mode=PROFILE_FILE_MODE)
    return path


def ensure_device_identity(
    home: Path | None = None, *, device_name: str | None = None
) -> DeviceIdentity:
    """读本机 device identity；首次运行（文件缺失）生成一次并原子落盘。

    之后永不重新生成（App 升级/重签名/移动路径都不改变 device id）；显式传入的
    ``device_name`` 只在首次生成时生效。
    """
    existing = load_device_identity(home)
    if existing is not None:
        return existing
    identity = DeviceIdentity.model_validate(
        {
            "schema_version": 1,
            "device_id": str(uuid4()),
            "device_name": device_name or socket.gethostname(),
            "created_at": datetime.now(UTC).isoformat(),
        }
    )
    _write_device_identity(identity, home)
    return identity


def load_device_identity(home: Path | None = None) -> DeviceIdentity | None:
    """读本机 device identity；文件缺失返回 None，损坏抛 ValueError。"""
    path = device_file(home)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return DeviceIdentity.model_validate(raw)
    except (ValueError, ValidationError) as exc:
        raise ValueError(f"device.json 损坏，请检查 {path}") from exc
