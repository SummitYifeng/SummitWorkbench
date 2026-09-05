"""Workspace / Profile / Device 领域模型（P0-07）。

把「用户知识库」「本机安装」「设备角色」从固定路径中显式建模：

- :class:`WorkspaceManifest`：随 vault 同步的 workspace 身份与兼容版本（vault 内
  ``.summit-workbench/workspace.json``，进入 Git）。
- :class:`LocalProfile`：本机对某个 workspace 的本地档案（work root / vault 路径、
  设备角色、最后打开时间），只存在于本机 Application Support，不同步。
- :class:`DeviceIdentity`：本机安装级身份（device id），首次运行生成一次、之后稳定。
- :class:`DeviceRole`：本设备在该 workspace 的角色（automation-primary / secondary）。
- :class:`Compatibility` 与 :func:`evaluate_manifest_compatibility`：App 版本与
  workspace schema 的兼容判定。

原则（P0-07）：UUID v4 身份；Pydantic 严格解析已知字段、容忍未知字段且重写不丢失；
marker 绝不携带 device id、本机绝对路径或秘密；版本比较只看正式发布位（忽略预发布后缀）。
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# 本包实现的 workspace schema 版本；高于它按「只读保护、不猜字段」处理（§2.4）。
SUPPORTED_WORKSPACE_SCHEMA = 1
# 本机 profile / device 存储 schema 版本。
LOCAL_SCHEMA_VERSION = 1

_RELEASE_SUFFIX_RE = re.compile(r"[-+].*$")


class DeviceRole(StrEnum):
    """本设备在该 workspace 中的角色（P0-10 用来门控自动化定时写者）。"""

    AUTOMATION_PRIMARY = "automation-primary"
    SECONDARY = "secondary"


class Compatibility(StrEnum):
    """App 对某 workspace marker 的兼容结论。"""

    READ_WRITE = "read-write"
    READ_ONLY_UPGRADE_REQUIRED = "read-only-upgrade-required"
    CANNOT_OPEN = "cannot-open"


def release_key(version: str) -> tuple[int, ...]:
    """把 ``X.Y.Z[-suffix]`` 版本解析成可比较的正式位元组（预发布/构建后缀忽略）。

    例如 ``0.5.0`` 与 ``0.5.0-alpha.1`` 都得到 ``(0, 5, 0)``：门控语义只看正式发布位。
    """
    release = _RELEASE_SUFFIX_RE.sub("", version.strip())
    try:
        return tuple(int(part) for part in release.split("."))
    except ValueError as exc:
        raise ValueError(f"无法解析版本号：{version!r}") from exc


def app_at_least(app_version: str, minimum: str) -> bool:
    """``app_version >= minimum``（按正式发布位比较）。"""
    return release_key(app_version) >= release_key(minimum)


class WorkspaceManifest(BaseModel):
    """vault 内同步的 workspace 身份 marker（§2.4）。

    未知字段容忍并随 :meth:`model_dump` 保留（前向兼容，重写不丢字段）。
    """

    model_config = ConfigDict(extra="allow")

    schema_version: Annotated[int, Field(ge=0)] = SUPPORTED_WORKSPACE_SCHEMA
    workspace_id: Annotated[str, Field(min_length=8, max_length=64)]
    display_name: Annotated[str, Field(min_length=1, max_length=200)]
    created_at: datetime
    min_reader_version: str
    min_writer_version: str

    @field_validator("workspace_id")
    @classmethod
    def _workspace_id_is_uuid(cls, value: str) -> str:
        # 只接受标准 UUID 形态；不要求严格 v4 以容忍校验器版本差异，但拒绝非 UUID。
        try:
            parsed = UUID(value)
        except ValueError as exc:
            raise ValueError("workspace_id 必须是 UUID 字符串") from exc
        if parsed.version != 4:
            raise ValueError("workspace_id 必须是 UUID v4")
        return str(parsed)


class LocalProfile(BaseModel):
    """本机对某 workspace 的本地档案（profiles/<id>/config.toml，不同步）。

    包含本机路径与设备角色等**非同步**信息；provider 非秘密配置后续由 P0-08 并入。
    """

    model_config = ConfigDict(extra="allow")

    schema_version: int = LOCAL_SCHEMA_VERSION
    workspace_id: Annotated[str, Field(min_length=8, max_length=64)]
    display_name: Annotated[str, Field(min_length=1, max_length=200)]
    work_root: Path
    vault_dir: Path
    device_role: DeviceRole = DeviceRole.SECONDARY
    created_at: datetime
    last_opened_at: datetime | None = None
    timezone: Annotated[str, Field(min_length=1, max_length=64)] = "Asia/Shanghai"
    # P0-09：Git author 邮箱（可选；缺省在提交时用本地占位 wb@local，绝不复制开发者 identity）
    user_email: Annotated[str, Field(max_length=254)] | None = None


class DeviceIdentity(BaseModel):
    """本机安装级身份（device.json，不同步）。移动路径/重签名不改变 id。"""

    model_config = ConfigDict(extra="allow")

    schema_version: int = LOCAL_SCHEMA_VERSION
    device_id: Annotated[str, Field(min_length=8, max_length=64)]
    device_name: Annotated[str, Field(min_length=1, max_length=200)]
    created_at: datetime

    @field_validator("device_id")
    @classmethod
    def _device_id_is_uuid_v4(cls, value: str) -> str:
        try:
            parsed = UUID(value)
        except ValueError as exc:
            raise ValueError("device_id 必须是 UUID 字符串") from exc
        if parsed.version != 4:
            raise ValueError("device_id 必须是 UUID v4")
        return str(parsed)


def evaluate_manifest_compatibility(manifest: WorkspaceManifest, app_version: str) -> Compatibility:
    """按「App 版本 + workspace schema」给出兼容结论（P0-07 对齐结论）。

    规则：
    - ``schema_version`` 超出本包支持范围：未来整数版本 → 只读保护（不猜字段语义，
      §2.4）；损坏/未知（≤0）→ cannot-open。
    - schema 为当前版本时按 min_reader/min_writer 门控：
      ``app < min_reader_version`` → cannot-open；``app < min_writer_version`` →
      read-only-upgrade-required；否则 read-write。
    """
    if manifest.schema_version > SUPPORTED_WORKSPACE_SCHEMA:
        return Compatibility.READ_ONLY_UPGRADE_REQUIRED
    if manifest.schema_version < SUPPORTED_WORKSPACE_SCHEMA:
        return Compatibility.CANNOT_OPEN
    if not app_at_least(app_version, manifest.min_reader_version):
        return Compatibility.CANNOT_OPEN
    if not app_at_least(app_version, manifest.min_writer_version):
        return Compatibility.READ_ONLY_UPGRADE_REQUIRED
    return Compatibility.READ_WRITE
