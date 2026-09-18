"""Validated identity for the frontend build served by the web application."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Literal, cast
from uuid import uuid4

from summit_workbench import __version__

PRODUCT_ID = "com.summitworkbench.panel"
API_PROTOCOL = 3
BuildMode = Literal["production", "development-managed", "development-external"]
_SHA256_LENGTH = 64


class BuildInfoError(ValueError):
    """Raised when the static frontend build metadata is missing or invalid."""


@dataclass(frozen=True)
class WebBuildInfo:
    """Immutable metadata for one compiled frontend artifact."""

    schema_version: int
    product_id: str
    frontend_build: str
    git_revision: str | None
    source_hash: str
    built_at: str
    index_sha256: str
    assets: dict[str, str]

    @classmethod
    def from_static_dir(cls, static_dir: Path) -> WebBuildInfo:
        meta_path = static_dir / "build-meta.json"
        index_path = static_dir / "index.html"
        if not meta_path.is_file():
            raise BuildInfoError("build-meta.json is missing")
        if not index_path.is_file():
            raise BuildInfoError("index.html is missing")
        try:
            raw = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BuildInfoError("build-meta.json is not valid UTF-8 JSON") from exc
        if not isinstance(raw, dict):
            raise BuildInfoError("build-meta.json must contain a JSON object")

        schema_version = _required_int(raw, "schema_version")
        if schema_version != 1:
            raise BuildInfoError(f"unsupported build metadata schema: {schema_version}")
        product_id = _required_str(raw, "product_id")
        if product_id != PRODUCT_ID:
            raise BuildInfoError(f"unexpected product_id: {product_id}")
        frontend_build = _required_str(raw, "frontend_build")
        git_revision = _optional_str(raw, "git_revision")
        source_hash = _required_sha256(raw, "source_hash")
        built_at = _required_str(raw, "built_at")
        try:
            datetime.fromisoformat(built_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise BuildInfoError("built_at must be an ISO-8601 timestamp") from exc
        index_sha256 = _required_sha256(raw, "index_sha256")
        assets_raw = raw.get("assets")
        if not isinstance(assets_raw, dict) or not assets_raw:
            raise BuildInfoError("assets must be a non-empty object")
        assets: dict[str, str] = {}
        for name, digest in assets_raw.items():
            if not isinstance(name, str) or not _is_safe_asset_name(name):
                raise BuildInfoError(f"invalid asset path: {name!r}")
            if not isinstance(digest, str) or not _is_sha256(digest):
                raise BuildInfoError(f"invalid asset hash for {name}")
            asset_path = static_dir / Path(*PurePosixPath(name).parts)
            if not asset_path.is_file():
                raise BuildInfoError(f"asset is missing: {name}")
            if _sha256(asset_path) != digest:
                raise BuildInfoError(f"asset hash mismatch: {name}")
            assets[name] = digest

        if _sha256(index_path) != index_sha256:
            raise BuildInfoError("index.html hash mismatch")
        return cls(
            schema_version=schema_version,
            product_id=product_id,
            frontend_build=frontend_build,
            git_revision=git_revision,
            source_hash=source_hash,
            built_at=built_at,
            index_sha256=index_sha256,
            assets=assets,
        )

    def version_payload(
        self,
        *,
        server_instance: str,
        started_at: str,
        mode: BuildMode,
        workspace_id: str | None = None,
        device_id: str | None = None,
        port: int | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "product_id": self.product_id,
            "api_protocol": API_PROTOCOL,
            "frontend_build": self.frontend_build,
            "server_version": __version__,
            "server_instance": server_instance,
            "started_at": started_at,
            "mode": mode,
            "git_revision": self.git_revision,
        }
        build_number = discover_build_number()
        if build_number is not None:
            payload["build"] = build_number
        if workspace_id is not None:
            payload["workspace_id"] = workspace_id
        if device_id is not None:
            payload["device_id"] = device_id
        if port is not None:
            payload["port"] = port
        return payload


def new_server_instance() -> str:
    return str(uuid4())


def _required_str(raw: dict[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise BuildInfoError(f"{key} must be a non-empty string")
    return value


def _optional_str(raw: dict[str, object], key: str) -> str | None:
    """可选溯源字段：缺失或空串都归一为 ``None``（不报错）。

    ``git_revision`` 属于此列：工作树脏时构建器**刻意**写空串，表示「这份产物不对应
    任何提交」。旧实现用 ``_required_str`` 读它，会让脏树构建出的包直接 503（2026-09-18
    真机：4 个 webapi 测试红了才发现）。消费方本就按可选处理（非空才追加）。
    """
    value = raw.get(key)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise BuildInfoError(f"{key} must be a string when present")
    return value


def _required_int(raw: dict[str, object], key: str) -> int:
    value = raw.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise BuildInfoError(f"{key} must be an integer")
    return value


def _required_sha256(raw: dict[str, object], key: str) -> str:
    value = _required_str(raw, key)
    if not _is_sha256(value):
        raise BuildInfoError(f"{key} must be a SHA-256 hex digest")
    return value


def _is_sha256(value: str) -> bool:
    return len(value) == _SHA256_LENGTH and all(c in "0123456789abcdef" for c in value)


def _is_safe_asset_name(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        name.startswith("assets/")
        and not path.is_absolute()
        and ".." not in path.parts
        and len(path.parts) > 1
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mode_from_environment(value: str | None) -> BuildMode:
    if value in {"production", "development-managed", "development-external"}:
        return cast(BuildMode, value)
    return "development-external"


def _discover_build_manifest() -> dict[str, object] | None:
    """Locate the App bundle ``build-manifest.json`` (build number lives there).

    The frontend ``build-meta.json`` only carries ``frontend_build``/``git_revision``;
    the numeric release ``build`` is written by the release script into
    ``Contents/Resources/build-manifest.json``.  In a frozen onedir server the
    executable sits at ``Contents/Resources/server/SummitWorkbenchServer``, so its
    parent's parent is ``Contents/Resources``.  This lookup is best-effort and
    never fails the preflight by itself.
    """
    candidates: list[Path] = []
    env = os.environ.get("WB_BUILD_MANIFEST")
    if env:
        candidates.append(Path(env))
    exe = Path(sys.executable).resolve()
    candidates.append(exe.parent.parent / "build-manifest.json")
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            raw = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(raw, dict):
            return raw
    return None


def discover_build_number() -> str | None:
    """Return the release build number, or ``None`` when not packaged/released."""
    manifest = _discover_build_manifest()
    if manifest is None:
        return None
    build = manifest.get("build")
    if build is None or build == "":
        return None
    return str(build)
