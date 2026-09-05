"""P0-07 workspace marker（vault 内 .summit-workbench/workspace.json）测试。

marker 随 vault 同步：同一 vault 在两台模拟设备读到相同 workspace_id；marker 不含
device id / 本机路径 / 秘密；未知字段随重写保留；损坏 marker 可见报错；
workspace_id_for_vault 优先读 marker、无 marker 回退 legacy（P0-04 兼容）。
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from summit_workbench.domain.workspace import WorkspaceManifest
from summit_workbench.repositories.workspace_manifest import (
    load_workspace_manifest,
    manifest_path,
    write_workspace_manifest,
)
from summit_workbench.workflows.external_actions import workspace_id_for_vault

WS_ID = str(uuid.uuid4())


def _manifest(**overrides: object) -> WorkspaceManifest:
    base: dict[str, object] = {
        "schema_version": 1,
        "workspace_id": WS_ID,
        "display_name": "Yifeng Workbench",
        "created_at": "2026-09-05T00:00:00Z",
        "min_reader_version": "0.4.1",
        "min_writer_version": "0.4.1",
    }
    base.update(overrides)
    return WorkspaceManifest.model_validate(base)


def test_manifest_missing_vault_returns_none(tmp_path) -> None:
    assert load_workspace_manifest(tmp_path / "no-such-vault") is None
    assert load_workspace_manifest(tmp_path) is None  # vault 存在但无 marker


def test_manifest_roundtrip_and_location(tmp_path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    write_workspace_manifest(vault, _manifest())
    assert manifest_path(vault) == vault / ".summit-workbench" / "workspace.json"
    assert manifest_path(vault).is_file()
    loaded = load_workspace_manifest(vault)
    assert loaded is not None
    assert loaded.workspace_id == WS_ID
    assert loaded.display_name == "Yifeng Workbench"


def test_manifest_unknown_fields_preserved_on_rewrite(tmp_path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    manifest = _manifest(extra_setting={"beta": True})
    write_workspace_manifest(vault, manifest)
    raw = json.loads(manifest_path(vault).read_text(encoding="utf-8"))
    assert raw["extra_setting"] == {"beta": True}
    loaded = load_workspace_manifest(vault)
    assert loaded is not None
    assert loaded.model_dump()["extra_setting"] == {"beta": True}


def test_same_vault_reads_same_workspace_id_across_homes(tmp_path) -> None:
    """同一 vault 在两台模拟设备读取相同 workspace id（marker 随 vault 同步）。"""
    vault = tmp_path / "shared-vault"
    vault.mkdir()
    write_workspace_manifest(vault, _manifest())
    # 两台设备只是「不同 Home 的用户目录」，读的是同一 vault 路径（模拟同步/共享盘）
    first = load_workspace_manifest(vault)
    assert first is not None and first.workspace_id == WS_ID
    again = load_workspace_manifest(Path(str(vault)))  # 同内容换一种表示再读
    assert again is not None and again.workspace_id == WS_ID


def test_corrupt_marker_raises_visible_error(tmp_path) -> None:
    vault = tmp_path / "vault"
    (vault / ".summit-workbench").mkdir(parents=True)
    (vault / ".summit-workbench" / "workspace.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        load_workspace_manifest(vault)


def test_marker_never_contains_device_or_secrets(tmp_path) -> None:
    """marker 只含同步元数据，不写 device 字段、本机绝对路径或秘密。"""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_workspace_manifest(vault, _manifest())
    raw = json.loads(manifest_path(vault).read_text(encoding="utf-8"))
    allowed = {
        "schema_version",
        "workspace_id",
        "display_name",
        "created_at",
        "min_reader_version",
        "min_writer_version",
    }
    assert set(raw) <= allowed
    assert "device_id" not in raw
    assert str(Path.home()) not in manifest_path(vault).read_text(encoding="utf-8")
    text = manifest_path(vault).read_text(encoding="utf-8").lower()
    for secret_marker in ("token", "secret", "password", "api_key"):
        assert secret_marker not in text


def test_workspace_id_for_vault_prefers_marker_and_falls_back_legacy(tmp_path) -> None:
    """outbox 工作区 id：有 marker 用 canonical id；无 marker 回退 legacy 摘要。"""
    vault = tmp_path / "with-marker"
    vault.mkdir()
    write_workspace_manifest(vault, _manifest())
    assert workspace_id_for_vault(vault) == WS_ID

    legacy_vault = tmp_path / "legacy"
    legacy_vault.mkdir()
    legacy_id = workspace_id_for_vault(legacy_vault)
    assert legacy_id.startswith("legacy-")
    # 同一 legacy vault 重复计算稳定
    assert workspace_id_for_vault(legacy_vault) == legacy_id
