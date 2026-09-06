"""P0-07 workspace 领域模型与兼容契约测试。

覆盖：WorkspaceManifest/LocalProfile/DeviceIdentity/DeviceRole/Compatibility 严格解析、
UUID v4 校验、版本键比较、schema 兼容映射（read-write / read-only-upgrade-required /
cannot-open），未知字段前向兼容且可随 model_dump 回写不丢失。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from summit_workbench.domain.workspace import (
    Compatibility,
    DeviceIdentity,
    DeviceRole,
    LocalProfile,
    WorkspaceManifest,
    app_at_least,
    evaluate_manifest_compatibility,
    release_key,
)

UUID_V4 = str(uuid.uuid4())


def _manifest(**overrides: object) -> WorkspaceManifest:
    base: dict[str, object] = {
        "schema_version": 2,
        "workspace_id": UUID_V4,
        "display_name": "Yifeng Workbench",
        "created_at": "2026-09-05T00:00:00Z",
        "min_reader_version": "0.4.1",
        "min_writer_version": "0.4.1",
    }
    base.update(overrides)
    return WorkspaceManifest.model_validate(base)


# ---- 模型严格解析 ----


def test_manifest_requires_uuid_v4_workspace_id() -> None:
    with pytest.raises(ValidationError):
        _manifest(workspace_id="not-a-uuid")
    parsed = _manifest()
    assert parsed.workspace_id == UUID_V4


def test_manifest_created_at_parsed_as_utc_datetime() -> None:
    manifest = _manifest()
    assert manifest.created_at == datetime(2026, 9, 5, tzinfo=UTC)


def test_manifest_unknown_fields_survive_dump() -> None:
    """未知字段前向兼容：解析容忍，model_dump 回写不丢失（不写回丢字段）。"""
    manifest = _manifest(future_field={"nested": 1})
    assert manifest.model_dump()["future_field"] == {"nested": 1}


def test_local_profile_rejects_unknown_role_and_parses_paths() -> None:
    base: dict[str, object] = {
        "schema_version": 1,
        "workspace_id": UUID_V4,
        "display_name": "Studio",
        "work_root": "/tmp/work",
        "vault_dir": "/tmp/work/_vault",
        "device_role": "secondary",
        "created_at": "2026-09-05T00:00:00Z",
    }
    with pytest.raises(ValidationError):
        LocalProfile.model_validate({**base, "device_role": "primary-writer"})
    profile = LocalProfile.model_validate(base)
    assert profile.device_role is DeviceRole.SECONDARY
    assert str(profile.work_root) == "/tmp/work"


def test_device_identity_requires_uuid_and_name() -> None:
    with pytest.raises(ValidationError):
        DeviceIdentity.model_validate({"device_id": "x", "device_name": "Studio"})
    identity = DeviceIdentity.model_validate(
        {
            "schema_version": 1,
            "device_id": UUID_V4,
            "device_name": "Studio",
            "created_at": "2026-09-05T00:00:00Z",
        }
    )
    assert identity.device_id == UUID_V4


def test_role_enum_values() -> None:
    assert DeviceRole.AUTOMATION_PRIMARY.value == "automation-primary"
    assert DeviceRole.SECONDARY.value == "secondary"


# ---- 版本比较 ----


def test_release_key_parses_semver_release_only() -> None:
    assert release_key("0.4.1") == (0, 4, 1)
    assert release_key("0.5.0") == (0, 5, 0)
    assert release_key("0.5.0-alpha.1") == (0, 5, 0)  # 预发布后缀只参与正式位比较
    assert release_key("1.2.10") > release_key("1.2.9")
    assert release_key("0.10.0") > release_key("0.9.9")
    with pytest.raises(ValueError):
        release_key("abc")


def test_app_at_least_compares_versions() -> None:
    assert app_at_least("0.4.1", "0.4.1") is True
    assert app_at_least("0.5.0", "0.4.1") is True
    assert app_at_least("0.4.1", "0.5.0") is False
    assert app_at_least("0.4.10", "0.4.9") is True


# ---- schema 兼容映射（P0-07 对齐结论） ----


def test_current_schema_and_version_is_read_write() -> None:
    assert evaluate_manifest_compatibility(_manifest(), "0.4.1") is Compatibility.READ_WRITE


def test_above_min_writer_but_below_min_reader_is_read_only() -> None:
    manifest = _manifest(min_reader_version="0.4.1", min_writer_version="0.5.0")
    assert (
        evaluate_manifest_compatibility(manifest, "0.4.1")
        is Compatibility.READ_ONLY_UPGRADE_REQUIRED
    )


def test_below_min_reader_is_cannot_open() -> None:
    manifest = _manifest(min_reader_version="0.5.0", min_writer_version="0.5.0")
    assert evaluate_manifest_compatibility(manifest, "0.4.1") is Compatibility.CANNOT_OPEN


def test_future_schema_version_is_read_only_protected() -> None:
    """更高 schema_version（未来已知形状）：只读保护，不猜字段语义（§2.4）。"""
    manifest = _manifest(schema_version=3, min_reader_version="0.4.1", min_writer_version="0.4.1")
    assert (
        evaluate_manifest_compatibility(manifest, "0.4.1")
        is Compatibility.READ_ONLY_UPGRADE_REQUIRED
    )


def test_unknown_schema_version_is_cannot_open() -> None:
    """损坏/未知的 schema_version（≤0 或非数）：cannot-open。"""
    manifest = _manifest(schema_version=0, min_reader_version="0.4.1", min_writer_version="0.4.1")
    assert evaluate_manifest_compatibility(manifest, "0.4.1") is Compatibility.CANNOT_OPEN
    with pytest.raises(ValidationError):
        _manifest(schema_version="not-a-number")
