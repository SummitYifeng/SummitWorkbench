"""Portable workspace manifest and compatibility rules for contract v1."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

WORKSPACE_FORMAT = "summit-workbench-workspace"
SUPPORTED_CONTRACT_VERSION = 1


class WorkspaceContractError(ValueError):
    """The selected folder is not a compatible SWB workspace."""


class WorkspaceContractManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    format: str = WORKSPACE_FORMAT
    workspace_id: Annotated[str, Field(min_length=36, max_length=36)]
    contract_version: Annotated[int, Field(ge=1)] = SUPPORTED_CONTRACT_VERSION
    min_reader_version: Annotated[int, Field(ge=1)] = SUPPORTED_CONTRACT_VERSION
    min_writer_version: Annotated[int, Field(ge=1)] = SUPPORTED_CONTRACT_VERSION

    @field_validator("format")
    @classmethod
    def _known_format(cls, value: str) -> str:
        if value != WORKSPACE_FORMAT:
            raise ValueError("unknown workspace format")
        return value

    @field_validator("workspace_id")
    @classmethod
    def _uuid4(cls, value: str) -> str:
        try:
            parsed = UUID(value)
        except ValueError as exc:
            raise ValueError("workspace_id must be UUID v4") from exc
        if parsed.version != 4 or str(parsed) != value.lower():
            raise ValueError("workspace_id must be canonical UUID v4")
        return str(parsed)


def check_workspace_compatibility(
    manifest: WorkspaceContractManifest,
    *,
    reader_version: int = SUPPORTED_CONTRACT_VERSION,
    writer_version: int = SUPPORTED_CONTRACT_VERSION,
) -> None:
    """Raise when the app must not connect or write the workspace."""
    if manifest.contract_version > reader_version:
        raise WorkspaceContractError("工作库契约版本高于本应用支持版本，请升级应用")
    if manifest.min_reader_version > reader_version:
        raise WorkspaceContractError("此工作库要求更新版本的应用才能打开")
    if manifest.min_writer_version > writer_version:
        raise WorkspaceContractError("此工作库要求更新版本的应用才能写入")
    if manifest.contract_version != SUPPORTED_CONTRACT_VERSION:
        raise WorkspaceContractError("工作库契约版本不受支持")
