"""Initialize, validate and connect portable workspaces without Git."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from summit_workbench.domain.workspace_contract import (
    WorkspaceContractError,
    WorkspaceContractManifest,
    check_workspace_compatibility,
)
from summit_workbench.repositories._atomic import atomic_write_text

_STATE_DIR = ".summit-workbench"
_MANIFEST = "manifest.json"


def _workspace_conventions_template() -> Path:
    module_path = Path(__file__).resolve()
    for parent in module_path.parents:
        candidate = parent / "templates" / "workspace" / "conventions.md"
        if candidate.is_file():
            return candidate
    return module_path.parents[3] / "templates" / "workspace" / "conventions.md"


def load_contract_manifest(root: Path) -> WorkspaceContractManifest:
    path = root / _STATE_DIR / _MANIFEST
    if not path.is_file():
        raise WorkspaceContractError("所选文件夹没有 SWB 工作库契约；请新建工作库或选兼容工作库")
    conventions_path = root / "conventions.md"
    if not conventions_path.is_file():
        raise WorkspaceContractError("工作库缺少可读的 conventions.md 契约说明")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        manifest = WorkspaceContractManifest.model_validate(data)
        check_workspace_compatibility(manifest)
        if not conventions_path.read_text(encoding="utf-8").strip():
            raise WorkspaceContractError("工作库 conventions.md 为空")
        return manifest
    except (OSError, UnicodeError, ValueError) as exc:
        if isinstance(exc, WorkspaceContractError):
            raise
        raise WorkspaceContractError(f"工作库契约损坏：{path}") from exc


def initialize_workspace(root: Path, *, display_name: str = "工作库") -> WorkspaceContractManifest:
    """Initialize only an empty folder; all files use existing atomic write helper."""
    root = root.expanduser().resolve()
    if not root.exists():
        root.mkdir(parents=True)
    if not root.is_dir() or not root.exists():
        raise WorkspaceContractError("工作库位置必须是可读写的文件夹")
    if any(root.iterdir()):
        raise WorkspaceContractError("此文件夹已有内容，SWB 不会覆盖；请选择空文件夹或使用导入")
    if not root.stat().st_mode & 0o200:
        raise WorkspaceContractError("工作库文件夹不可写")
    manifest = WorkspaceContractManifest(workspace_id=str(uuid4()))
    write_workspace_contract(root, manifest)
    return manifest


def write_workspace_contract(
    root: Path,
    manifest: WorkspaceContractManifest,
    *,
    replace_conventions: bool = False,
    preserve_conventions: bool = False,
) -> Path:
    """Write a frozen manifest into a caller-prepared staging directory."""
    root = root.expanduser().resolve()
    manifest_path = root / _STATE_DIR / _MANIFEST
    if manifest_path.exists():
        raise WorkspaceContractError("工作库契约已存在，不会覆盖身份")
    conventions_path = root / "conventions.md"
    if conventions_path.exists() and not (replace_conventions or preserve_conventions):
        raise WorkspaceContractError("conventions.md 已存在；请显式选择模板升级")
    conventions = _workspace_conventions_template().read_text(encoding="utf-8")
    atomic_write_text(
        manifest_path,
        json.dumps(manifest.model_dump(), indent=2) + "\n",
        ensure_parents=True,
    )
    try:
        if not (preserve_conventions and conventions_path.exists()):
            atomic_write_text(conventions_path, conventions, ensure_parents=True)
    except BaseException:
        manifest_path.unlink(missing_ok=True)
        try:
            manifest_path.parent.rmdir()
        except OSError:
            pass
        raise
    return manifest_path


def connect_workspace(root: Path) -> WorkspaceContractManifest:
    """Connect an existing folder without changing it."""
    resolved = root.expanduser().resolve()
    if not resolved.is_dir():
        raise WorkspaceContractError("所选位置不是可访问的文件夹")
    return load_contract_manifest(resolved)
