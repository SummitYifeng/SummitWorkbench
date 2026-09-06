"""签名更新 feed 的无副作用解析与兼容性筛选（P1-07）。"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

from summit_workbench.domain.workspace import release_key

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_VERSION_RE = re.compile(r"^\d+(?:\.\d+){0,3}(?:[-+][A-Za-z0-9.-]+)?$")


class UpdateFeedError(ValueError):
    """feed 不可解析、不可验证或不适用于当前 App。"""


def signing_payload(artifact: Mapping[str, Any], *, product_id: str) -> bytes:
    """返回 Python/Swift 共同使用的稳定签名正文；不包含 signature 字段。"""
    fields = (
        product_id,
        _required_str(artifact, "version"),
        _required_str(artifact, "build"),
        _required_str(artifact, "architecture"),
        _required_str(artifact, "minimum_macos"),
        _required_str(artifact, "download_url"),
        _required_str(artifact, "sha256"),
        str(_required_int(artifact, "size")),
        _required_str(artifact, "release_notes"),
    )
    return "\n".join(fields).encode("utf-8")


def select_compatible_update(
    payload: Mapping[str, Any],
    *,
    current_version: str,
    current_build: str,
    architecture: str = "arm64",
    macos_version: tuple[int, int, int] = (13, 0, 0),
) -> dict[str, Any] | None:
    """返回最高兼容且更新的 artifact；不执行下载、不写 vault。"""
    if (
        payload.get("schema_version") != 1
        or payload.get("product_id") != "com.summitworkbench.panel"
    ):
        raise UpdateFeedError("update feed schema 或 product_id 无效")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        raise UpdateFeedError("update feed artifacts 无效")

    candidates: list[dict[str, Any]] = []
    current_release = release_key(current_version)
    try:
        current_build_number = int(current_build)
    except ValueError as exc:
        raise UpdateFeedError("当前 build 无效") from exc
    for raw in artifacts:
        if not isinstance(raw, dict):
            continue
        try:
            version = _required_str(raw, "version")
            build = _required_str(raw, "build")
            minimum = _required_str(raw, "minimum_macos")
            if not _VERSION_RE.fullmatch(version) or raw.get("architecture") != architecture:
                continue
            if _parse_version(minimum) > macos_version:
                continue
            if not _is_newer(version, build, current_release, current_build_number):
                continue
            url = _required_str(raw, "download_url")
            if urlparse(url).scheme != "https" or not _HEX64.fullmatch(
                _required_str(raw, "sha256")
            ):
                continue
            if _required_int(raw, "size") <= 0:
                continue
            signature = raw.get("signature")
            if not isinstance(signature, str) or not signature:
                continue
            candidates.append(raw)
        except (UpdateFeedError, ValueError):
            continue
    return (
        max(
            candidates,
            key=lambda item: (release_key(str(item["version"])), int(str(item["build"]))),
        )
        if candidates
        else None
    )


def _is_newer(
    version: str, build: str, current_release: tuple[int, ...], current_build: int
) -> bool:
    try:
        build_number = int(build)
    except ValueError:
        return False
    release = release_key(version)
    return release > current_release or (
        release == current_release and build_number > current_build
    )


def _parse_version(value: str) -> tuple[int, int, int]:
    parts = release_key(value)
    if len(parts) > 3:
        raise UpdateFeedError("minimum_macos 无效")
    normalized = (*parts, 0, 0)
    return normalized[0], normalized[1], normalized[2]


def _required_str(value: Mapping[str, Any], key: str) -> str:
    raw = value.get(key)
    if not isinstance(raw, str) or not raw:
        raise UpdateFeedError(f"update feed 缺少 {key}")
    return raw


def _required_int(value: Mapping[str, Any], key: str) -> int:
    raw = value.get(key)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise UpdateFeedError(f"update feed 缺少 {key}")
    return raw


__all__ = ["UpdateFeedError", "select_compatible_update", "signing_payload"]
