"""脱敏诊断包内容生成（P1-05）。"""

from __future__ import annotations

import io
import json
import platform
import sys
import tomllib
import zipfile
from pathlib import Path
from typing import Any

from summit_workbench import __version__
from summit_workbench.observability.structured_logging import StructuredLogger, short_id
from summit_workbench.repositories.workspace_manifest import load_workspace_manifest
from summit_workbench.webapp.build_info import BuildInfoError, WebBuildInfo


def _config_keys(path: Path) -> list[str]:
    if not path.is_file():
        return []
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return []
    keys: list[str] = []

    def visit(prefix: str, value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                visit(f"{prefix}.{key}" if prefix else str(key), child)
        else:
            keys.append(prefix)

    visit("", raw)
    return sorted(keys)


def diagnostic_snapshot(
    context: Any,
    *,
    static_dir: Path,
    log_path: Path | None = None,
) -> dict[str, object]:
    """生成只含状态/计数/键名的诊断快照，不读取 vault 正文。"""
    try:
        build = WebBuildInfo.from_static_dir(static_dir)
        build_info: dict[str, object] = {
            "frontend_build": build.frontend_build,
            "git_revision": build.git_revision,
            "built_at": build.built_at,
        }
    except BuildInfoError as exc:
        build_info = {"error_code": "invalid_build_manifest", "detail": str(exc)}

    try:
        manifest = load_workspace_manifest(context.vault_dir)
        schema_state = "valid"
    except ValueError:
        manifest = None
        schema_state = "invalid"
    logger = StructuredLogger(log_path, component="diagnostics")
    snapshot: dict[str, object] = {
        "schema_version": 1,
        "app_version": __version__,
        "architecture": platform.machine(),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "build": build_info,
        "workspace": {
            "workspace_id": short_id(context.workspace_id),
            "device_id": short_id(
                context.active_workspace.device_id if context.active_workspace else None
            ),
            "schema_version": manifest.schema_version if manifest else None,
            "schema_state": schema_state,
            "compatibility": str(context.compatibility),
        },
        "status_summary": _status_summary(context),
        "sync_counters": _sync_counters(context),
        "config_keys": _config_keys(context.provider_config_file()),
        "signature": {"mode": "internal-ad-hoc", "notarized": False},
        "recent_errors": [item for item in logger.recent() if item.get("level") == "error"],
    }
    return snapshot


def bundle_bytes(snapshot: dict[str, object]) -> bytes:
    """把快照放进 zip；包内不包含日志原文、vault 文件或凭据。"""
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "diagnostics.json", json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
        )
    return output.getvalue()


def _status_summary(context: Any) -> dict[str, object]:
    try:
        from summit_workbench.domain.pipeline import ProcessingState
        from summit_workbench.observability.status import build_status

        status = build_status(context.vault_dir, config_file=context.provider_config_file())
        return {
            "total_meetings": status.total_meetings,
            "succeeded": status.succeeded,
            "failed": status.count(ProcessingState.FAILED),
            "pending_review": status.backlog.count,
            "budget_over_soft_limit": status.budget.over_soft_limit,
        }
    except Exception:
        return {"state": "unavailable"}


def _sync_counters(context: Any) -> dict[str, object]:
    try:
        from summit_workbench.workflows import sync_coordinator

        snapshot = sync_coordinator.current_snapshot(
            context.vault_dir,
            home=context.active_workspace.home if context.active_workspace else None,
            workspace_id=context.workspace_id,
            backend_kind=context.git_backend_kind,
            context=context.active_workspace,
        )
        return {
            "state": snapshot.state,
            "ahead": snapshot.ahead,
            "behind": snapshot.behind,
            "pending_commits": snapshot.pending_commits,
        }
    except Exception:
        return {"state": "unavailable"}


__all__ = ["bundle_bytes", "diagnostic_snapshot"]
