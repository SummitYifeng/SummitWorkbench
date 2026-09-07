"""Read-only P1-07D acceptance preflight for a production workspace."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from summit_workbench import __version__
from summit_workbench.config.app_support import backups_dir
from summit_workbench.config.git_credentials import resolve_git_credentials, strip_credentials
from summit_workbench.config.tls_trust import ca_bundle_path
from summit_workbench.domain.workspace import (
    Compatibility,
    DeviceRole,
    evaluate_manifest_compatibility,
)
from summit_workbench.repositories.git import GitRepo
from summit_workbench.repositories.git_backend import (
    AheadBehind,
    GitError,
    GitRemoteSchemeUnsupported,
    classify_git_error,
    production_backend_kind,
    require_https_remote,
)
from summit_workbench.repositories.profile_registry import load_profile
from summit_workbench.repositories.workspace_manifest import load_workspace_manifest
from summit_workbench.workflows.workspace_migration import default_migration_registry


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class AcceptancePreflightReport:
    ok: bool
    workspace_id: str
    app_version: str
    checks: tuple[PreflightCheck, ...]
    text: str


def _check(name: str, status: str, detail: str) -> PreflightCheck:
    return PreflightCheck(name=name, status=status, detail=detail)


def _remote_summary(url: str | None) -> str:
    if not url:
        return "未配置"
    safe = strip_credentials(url)
    parsed = urlsplit(safe)
    return f"{parsed.scheme or 'scp'}://{parsed.hostname or 'unknown'}"


def _proxy_detected() -> str:
    """只报告是否存在代理（布尔语义），绝不回显代理 URL/凭据。"""
    for key in ("https_proxy", "http_proxy", "all_proxy"):
        if os.environ.get(key):
            return "detected"
    return "none"


def acceptance_preflight(
    vault_dir: Path,
    *,
    home: Path,
    workspace_id: str,
    app_version: str = __version__,
    backend_kind: str = "dulwich",
    build_number: str | None = None,
    frontend_build: str | None = None,
    git_revision: str | None = None,
) -> AcceptancePreflightReport:
    """Run non-destructive checks; fetch only updates remote-tracking refs."""
    checks: list[PreflightCheck] = []
    profile = load_profile(workspace_id, home=home)
    repo = GitRepo(
        vault_dir,
        backend_kind=backend_kind,
        workspace_id=workspace_id,
        username=profile.git_username if profile is not None else None,
    )
    system_repo = GitRepo(vault_dir, backend_kind="system", workspace_id=workspace_id)
    remote_url: str | None = None

    identity = [f"version={app_version}"]
    if build_number:
        identity.append(f"build={build_number}")
    if frontend_build:
        identity.append(f"frontend_build={frontend_build}")
    if git_revision:
        identity.append(f"git_revision={git_revision}")
    identity.append(f"production backend={production_backend_kind()}")
    checks.append(_check("app/build", "pass", "; ".join(identity)))
    checks.append(
        _check(
            "production-backend",
            "pass" if backend_kind == production_backend_kind() else "fail",
            f"selected={backend_kind}",
        )
    )

    try:
        remote_url = repo.remote_url("origin")
    except GitError:
        pass
    try:
        require_https_remote(remote_url or "")
        checks.append(_check("remote-scheme", "pass", _remote_summary(remote_url)))
    except GitRemoteSchemeUnsupported:
        checks.append(
            _check(
                "remote-scheme",
                "fail",
                "remote_scheme_unsupported; production requires HTTPS",
            )
        )

    remote_host = urlsplit(strip_credentials(remote_url)).hostname if remote_url else ""
    credential_available = False
    if profile is None:
        checks.append(_check("credentials", "fail", "active profile missing"))
    elif remote_url and remote_url.startswith("https://") and profile.git_username:
        try:
            resolve_git_credentials(workspace_id, remote_host or "", profile.git_username)
            credential_available = True
            checks.append(
                _check(
                    "credentials",
                    "pass",
                    f"workspace-scoped Keychain configured for {remote_host}",
                )
            )
        except Exception:
            checks.append(
                _check(
                    "credentials",
                    "fail",
                    "git_credentials_unavailable: workspace-scoped Git credential unavailable",
                )
            )
    else:
        checks.append(_check("credentials", "fail", "HTTPS username/PAT is not configured"))

    try:
        system_dirty = system_repo.is_dirty()
    except GitError:
        system_dirty = None
    try:
        dulwich_dirty = repo.is_dirty()
    except GitError:
        dulwich_dirty = None
    checks.append(
        _check(
            "dirty-consistency",
            "pass" if system_dirty is False and dulwich_dirty is False else "fail",
            f"system={system_dirty}; dulwich={dulwich_dirty}",
        )
    )

    counts: AheadBehind | None = None
    if remote_url and remote_url.startswith("https://"):
        try:
            repo.fetch()
            counts = repo.ahead_behind()
            checks.append(_check("fetch", "pass", "HTTPS fetch completed"))
        except GitError as exc:
            code = classify_git_error(exc)
            detail = (
                f"error_code={code}; backend={backend_kind}; operation=fetch; "
                f"host={remote_host or 'unknown'}; "
                f"credential_found={str(credential_available).lower()}; "
                f"ca_bundle_built={str(ca_bundle_path() is not None).lower()}; "
                f"ssl_verify=on; proxy={_proxy_detected()}"
            )
            checks.append(_check("fetch", "fail", detail))
    else:
        checks.append(_check("fetch", "blocked", "remote_scheme_unsupported"))
    try:
        branch = repo.current_branch()
        upstream = repo.has_upstream()
        if counts is None and upstream:
            counts = repo.ahead_behind()
        detail = f"branch={branch}; upstream={upstream}"
        if counts is not None:
            detail += f"; ahead={counts.ahead}; behind={counts.behind}"
        checks.append(_check("branch/upstream", "pass" if upstream else "fail", detail))
        if counts is not None:
            checks.append(
                _check(
                    "ahead-behind",
                    "pass" if counts == AheadBehind(ahead=0, behind=0) else "fail",
                    f"ahead={counts.ahead}; behind={counts.behind}",
                )
            )
    except GitError:
        checks.append(_check("branch/upstream", "fail", "branch or upstream unavailable"))

    manifest = load_workspace_manifest(vault_dir)
    if manifest is None:
        checks.append(_check("schema-path", "fail", "workspace marker missing"))
    else:
        compatibility = evaluate_manifest_compatibility(manifest, app_version)
        try:
            path = default_migration_registry().path(manifest.schema_version, 2)
            path_detail = " -> ".join(str(step.from_version) for step in path) + " -> 2"
            status = "pass" if compatibility is Compatibility.READ_WRITE or path else "fail"
        except Exception:
            path_detail = f"schema={manifest.schema_version}; no complete path to 2"
            status = "fail"
        checks.append(_check("schema-path", status, path_detail))

    backup_root = backups_dir(home=home)
    backup_parent = backup_root if backup_root.is_dir() else backup_root.parent
    checks.append(
        _check(
            "backup-writable",
            "pass" if backup_parent.is_dir() and os.access(backup_parent, os.W_OK) else "fail",
            "migration backup destination is writable"
            if backup_parent.is_dir()
            else "backup parent missing",
        )
    )
    role = profile.device_role if profile is not None else None
    checks.append(
        _check(
            "automation-role",
            "pass" if role in {DeviceRole.AUTOMATION_PRIMARY, DeviceRole.SECONDARY} else "fail",
            role.value if role is not None else "profile missing",
        )
    )

    failed = [item for item in checks if item.status == "fail"]
    lines = [
        "SummitWorkbench P1-07D acceptance preflight",
        f"app={app_version}; backend={backend_kind}; workspace={workspace_id.split('-')[0]}",
    ]
    lines.extend(f"[{item.status.upper()}] {item.name}: {item.detail}" for item in checks)
    lines.append("RESULT: " + ("PASS" if not failed else "FAIL"))
    return AcceptancePreflightReport(
        ok=not failed,
        workspace_id=workspace_id,
        app_version=app_version,
        checks=tuple(checks),
        text="\n".join(lines),
    )


__all__ = ["AcceptancePreflightReport", "PreflightCheck", "acceptance_preflight"]
