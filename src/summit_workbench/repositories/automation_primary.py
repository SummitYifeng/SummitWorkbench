"""同步的 automation-primary 唯一声明（P0-10C）。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from summit_workbench.repositories._atomic import atomic_write_text
from summit_workbench.repositories.workspace_manifest import load_workspace_manifest

_FILENAME = "automation-primary.json"


class AutomationPrimaryClaim(BaseModel):
    """vault 内同步的主设备声明；generation 只允许显式递增。"""

    schema_version: int = 1
    workspace_id: str
    device_id: str = Field(min_length=1, max_length=200)
    generation: int = Field(ge=1)
    claimed_at: str


class AutomationPrimaryError(RuntimeError):
    """主设备声明冲突/损坏的稳定错误。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def automation_primary_path(vault_dir: Path) -> Path:
    return vault_dir / ".summit-workbench" / _FILENAME


def load_automation_primary(vault_dir: Path) -> AutomationPrimaryClaim | None:
    path = automation_primary_path(vault_dir)
    if not path.is_file():
        return None
    try:
        return AutomationPrimaryClaim.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, ValidationError) as exc:
        raise AutomationPrimaryError(
            "primary_state_corrupt", "automation-primary 声明损坏"
        ) from exc


def claim_automation_primary(
    vault_dir: Path,
    workspace_id: str,
    device_id: str,
    *,
    expected_generation: int | None = None,
    takeover: bool = False,
) -> AutomationPrimaryClaim:
    """声明或显式接管主设备；旧心跳/旧 device 不会自动抢主。"""
    manifest = load_workspace_manifest(vault_dir)
    if manifest is None or manifest.workspace_id != workspace_id:
        raise AutomationPrimaryError("workspace_mismatch", "workspace marker 与主设备声明不一致")
    if not device_id.strip():
        raise AutomationPrimaryError("device_id_invalid", "device id 不能为空")
    existing = load_automation_primary(vault_dir)
    if existing is None:
        if expected_generation is not None or takeover:
            raise AutomationPrimaryError(
                "primary_generation_conflict", "首次声明不接受 takeover generation"
            )
        claim = AutomationPrimaryClaim(
            workspace_id=workspace_id,
            device_id=device_id,
            generation=1,
            claimed_at=datetime.now(UTC).isoformat(),
        )
    elif existing.workspace_id != workspace_id:
        raise AutomationPrimaryError("workspace_mismatch", "已有主设备声明属于另一个 workspace")
    elif existing.device_id == device_id:
        if expected_generation is not None and expected_generation != existing.generation:
            raise AutomationPrimaryError(
                "primary_generation_conflict", "主设备声明 generation 已变化"
            )
        if takeover:
            raise AutomationPrimaryError("primary_takeover_invalid", "当前主设备无需 takeover")
        return existing
    elif not takeover:
        raise AutomationPrimaryError(
            "primary_already_claimed", "已有其它 device 是 automation-primary"
        )
    elif expected_generation != existing.generation:
        raise AutomationPrimaryError(
            "primary_generation_conflict", "takeover 必须基于当前 generation"
        )
    else:
        claim = AutomationPrimaryClaim(
            workspace_id=workspace_id,
            device_id=device_id,
            generation=existing.generation + 1,
            claimed_at=datetime.now(UTC).isoformat(),
        )
    path = automation_primary_path(vault_dir)
    atomic_write_text(
        path,
        json.dumps(claim.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        ensure_parents=True,
    )
    return claim
