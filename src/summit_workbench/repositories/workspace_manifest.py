"""vault 内 workspace marker 读写（P0-07）。

marker 位于 ``<vault>/.summit-workbench/workspace.json``，**随 vault 进入 Git 同步**，
是 workspace 的唯一身份源：同一 vault 在任意设备读到同一 ``workspace_id``。
marker 绝不包含 device id、本机绝对路径或秘密（ADR 0029）。

- 缺失（旧 vault 尚未升级）→ ``None``，只能经 P0-08「升级现有工作区」显式生成；
- 内容损坏 → 抛 :class:`WorkspaceManifestError`（可见，不静默猜字段）；
- 写入走 P0-06 原子原语；未知字段随解析保留、重写不丢失（前向兼容）。
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from summit_workbench.domain.workspace import WorkspaceManifest
from summit_workbench.repositories._atomic import atomic_write_text

_MANIFEST_SUBDIR = ".summit-workbench"
_MANIFEST_FILENAME = "workspace.json"


class WorkspaceManifestError(ValueError):
    """workspace.json 缺失以外的读/写失败（损坏、schema 不符）。"""


def manifest_path(vault_dir: Path) -> Path:
    """vault 内 marker 的完整路径。"""
    return vault_dir / _MANIFEST_SUBDIR / _MANIFEST_FILENAME


def load_workspace_manifest(vault_dir: Path) -> WorkspaceManifest | None:
    """读 vault 的 workspace marker；旧 vault 无 marker 返回 None。

    文件存在但不可解析 / 校验失败时抛 :class:`WorkspaceManifestError`——
    marker 一旦存在就是身份真源，损坏必须可见，不能静默回退到猜测 id。
    """
    path = manifest_path(vault_dir)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return WorkspaceManifest.model_validate(raw)
    except (ValueError, ValidationError) as exc:
        raise WorkspaceManifestError(f"workspace marker 损坏：{path}") from exc


def write_workspace_manifest(vault_dir: Path, manifest: WorkspaceManifest) -> Path:
    """原子写 vault 的 workspace marker（父目录按需创建）。

    只由 P0-08 onboarding（create/upgrade/connect）调用；这里保留普通文件权限
    （marker 随 Git 同步，非本机敏感文件）。
    """
    path = manifest_path(vault_dir)
    text = json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
    atomic_write_text(path, text, ensure_parents=True)
    return path
