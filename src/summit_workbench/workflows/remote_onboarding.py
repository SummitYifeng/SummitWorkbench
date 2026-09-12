"""私有 HTTPS remote clone 的 staging/确认服务（P0-09C）。

远端 clone 是一个两阶段动作：先在目标同文件系统创建本次操作专属 staging，
校验 marker/兼容性，随后由用户确认才原子移动并创建 secondary profile。整个流程
不运行系统 Git；凭据仅通过 Dulwich backend 的短生命周期 callback 进入 HTTP 请求。
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from summit_workbench import __version__
from summit_workbench.config.git_credentials import GitCredentials
from summit_workbench.domain.onboarding import OnboardingFlow, OnboardingResult
from summit_workbench.domain.workspace import (
    Compatibility,
    DeviceRole,
    LocalProfile,
    WorkspaceManifest,
    evaluate_manifest_compatibility,
)
from summit_workbench.repositories.git_backend import (
    GitAuthError,
    GitBackend,
    GitCredentialsUnavailable,
    GitInvalidRevision,
    GitProxyError,
    GitRemoteUnavailable,
    GitTlsError,
)
from summit_workbench.repositories.profile_registry import (
    drop_profile,
    ensure_device_identity,
    load_registry,
    save_profile,
    save_registry,
    set_active_profile,
)
from summit_workbench.repositories.workspace_manifest import load_workspace_manifest


class RemoteCloneError(RuntimeError):
    """remote clone 的稳定、脱敏错误。"""

    def __init__(self, code: str, message: str, *, reasons: list[str] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.reasons = reasons or [message]


@dataclass(frozen=True)
class RemoteCloneStage:
    """一次待确认的 staging 结果；不包含任何密码。"""

    staging_dir: Path
    target_vault: Path
    remote_url: str
    workspace_id: str
    username: str
    manifest: WorkspaceManifest
    compatibility: Compatibility


BackendFactory = Callable[..., GitBackend]
CredentialResolver = Callable[[str, str, str], GitCredentials]


def validate_remote_url(url: str) -> str:
    """只接受不带 userinfo 的 HTTPS remote，并返回可安全持久化的 URL。"""
    try:
        parsed = urlsplit(url.strip())
    except ValueError as exc:
        raise RemoteCloneError("remote_url_invalid", "remote URL 无法解析") from exc
    if parsed.scheme.lower() != "https" or not parsed.hostname or not parsed.path:
        raise RemoteCloneError(
            "remote_scheme_unsupported",
            "remote clone 只支持 HTTPS URL（remote_scheme_unsupported）",
        )
    if parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
        raise RemoteCloneError("remote_url_userinfo", "remote URL 不允许包含账号或密码")
    try:
        host = parsed.hostname
        if parsed.port is not None:
            host = f"{host}:{parsed.port}"
    except ValueError as exc:
        raise RemoteCloneError("remote_url_invalid", "remote URL 端口无效") from exc
    return urlunsplit(("https", host, parsed.path, parsed.query, parsed.fragment))


def _default_backend_factory(
    path: Path,
    *,
    workspace_id: str,
    username: str,
    credential_resolver: CredentialResolver | None = None,
) -> GitBackend:
    from summit_workbench.repositories.dulwich_git import DulwichGitBackend

    return DulwichGitBackend(
        path,
        workspace_id=workspace_id,
        username=username,
        credential_resolver=credential_resolver,
    )


def _clean_stage(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def stage_remote_clone(
    url: str,
    target_vault: Path,
    *,
    workspace_id: str | None,
    username: str,
    home: Path | None = None,
    app_version: str | None = None,
    backend_factory: BackendFactory | None = None,
    credential_resolver: CredentialResolver | None = None,
) -> RemoteCloneStage:
    """clone 到目标同文件系统 staging，并完成 marker/兼容性检查。"""
    safe_url = validate_remote_url(url)
    if not username.strip() or len(username) > 200:
        raise RemoteCloneError("git_username_invalid", "Git 用户名不能为空或过长")
    if backend_factory is None and credential_resolver is None and not workspace_id:
        # 只有需要**从 Keychain 读取 workspace 作用域凭据**时才要求预期 id。空安装向导手里
        # 没有这个 id（它由远端 marker 决定），而它总是显式带上本次要用的 PAT
        # （credential_resolver），此时没有任何按作用域查找凭据的动作；下方的
        # ``workspace_id or ""`` 与 ``manifest.workspace_id`` 回填也早已支持 None。
        raise RemoteCloneError(
            "workspace_id_required",
            "私有 remote clone 需要预期 workspace id 才能读取作用域凭据",
        )
    target = target_vault.expanduser()
    if target.exists():
        raise RemoteCloneError("target_exists", "目标 vault 已存在，未覆盖")
    if not target.parent.is_dir():
        raise RemoteCloneError("target_parent_missing", "目标 vault 的父目录不存在")

    # mkdtemp 先占住唯一名称；移除空目录后交给 clone，让 Dulwich 按标准 clone
    # 语义创建目标并 checkout，而不是把一个预先存在的 staging 当成非空仓库。
    stage = Path(tempfile.mkdtemp(prefix=".summit-workbench-remote-", dir=target.parent))
    stage.rmdir()
    factory = backend_factory or _default_backend_factory
    try:
        backend = factory(
            stage,
            workspace_id=workspace_id or "",
            username=username,
            credential_resolver=credential_resolver,
        )
        backend.clone(safe_url, stage)
        manifest = load_workspace_manifest(stage)
        if manifest is None:
            raise RemoteCloneError(
                "remote_missing_marker",
                "远端没有 workspace marker；请在原设备显式升级后再连接",
            )
        if workspace_id is not None and manifest.workspace_id != workspace_id:
            raise RemoteCloneError("workspace_mismatch", "远端 workspace id 与预期不一致")
        compatibility = evaluate_manifest_compatibility(manifest, app_version or __version__)
        if compatibility is not Compatibility.READ_WRITE:
            raise RemoteCloneError(
                "workspace_incompatible",
                "远端 workspace 与当前 App 版本不兼容，请升级 App 后重试",
            )
        return RemoteCloneStage(
            staging_dir=stage,
            target_vault=target,
            remote_url=safe_url,
            workspace_id=manifest.workspace_id,
            username=username,
            manifest=manifest,
            compatibility=compatibility,
        )
    except RemoteCloneError:
        _clean_stage(stage)
        raise
    except GitAuthError as exc:
        _clean_stage(stage)
        raise RemoteCloneError(
            "remote_auth_required", "远端认证失败，请检查 workspace 凭据"
        ) from exc
    except GitTlsError as exc:
        _clean_stage(stage)
        raise RemoteCloneError("remote_tls_failed", "远端 TLS/证书校验失败") from exc
    except GitRemoteUnavailable as exc:
        _clean_stage(stage)
        raise RemoteCloneError("remote_unavailable", "远端不可达或仓库不存在") from exc
    except GitCredentialsUnavailable as exc:
        # 本机没有可用的 workspace 凭据，且调用方没有显式提供（空安装向导永远显式提供）。
        _clean_stage(stage)
        raise RemoteCloneError(
            "remote_credentials_unavailable", "远端凭据不可用：本机没有该工作区的 Git 凭据"
        ) from exc
    except GitProxyError as exc:
        # 系统代理这条链路不通。curl/git 不读 macOS 系统代理，只有 App 会走它，
        # 因此这类故障最容易被误判成"凭据或网络问题"。
        _clean_stage(stage)
        raise RemoteCloneError(
            "remote_proxy_failed", "本机代理无法连接远端；可临时关闭系统代理后重试"
        ) from exc
    except GitInvalidRevision as exc:
        _clean_stage(stage)
        raise RemoteCloneError("remote_branch_invalid", "远端没有可连接的有效分支") from exc
    except Exception as exc:  # noqa: BLE001 - service boundary must be stable and sanitized
        _clean_stage(stage)
        # 兜底也要留下可判定的线索：只带异常类名（不含 URL、路径或任何值）。
        raise RemoteCloneError(
            "remote_clone_failed",
            "远端 clone 失败，请检查凭据、网络或 TLS",
            reasons=[type(exc).__name__],
        ) from exc


def confirm_remote_clone(
    staged: RemoteCloneStage,
    *,
    home: Path | None = None,
    display_name: str | None = None,
    device_name: str | None = None,
    user_email: str | None = None,
) -> OnboardingResult:
    """用户确认后原子移动 staging，并创建 secondary profile。"""
    if not staged.staging_dir.is_dir():
        raise RemoteCloneError("staging_missing", "remote clone staging 已失效，请重新开始")
    if staged.target_vault.exists():
        raise RemoteCloneError("target_exists", "目标 vault 已存在，未覆盖")
    marker = load_workspace_manifest(staged.staging_dir)
    if marker is None or marker.workspace_id != staged.workspace_id:
        raise RemoteCloneError("remote_missing_marker", "staging 的 workspace marker 无效")

    original_registry = load_registry(home)
    profile_saved = False
    moved = False
    try:
        os_replace(staged.staging_dir, staged.target_vault)
        moved = True
        device = ensure_device_identity(home, device_name=device_name)
        profile = LocalProfile.model_validate(
            {
                "schema_version": 1,
                "workspace_id": staged.workspace_id,
                "display_name": display_name or marker.display_name,
                "work_root": str(staged.target_vault.parent),
                "vault_dir": str(staged.target_vault),
                "device_role": DeviceRole.SECONDARY.value,
                "created_at": marker.created_at.isoformat(),
                "user_email": user_email,
                "git_username": staged.username,
                "git_remote_url": staged.remote_url,
            }
        )
        save_profile(profile, home=home)
        profile_saved = True
        set_active_profile(staged.workspace_id, home=home)
        return OnboardingResult(
            flow=OnboardingFlow.CONNECT_LOCAL,
            workspace_id=staged.workspace_id,
            work_root=str(staged.target_vault.parent),
            vault_dir=str(staged.target_vault),
            device_id=device.device_id,
            display_name=profile.display_name,
            created_at=marker.created_at.isoformat(),
        )
    except RemoteCloneError:
        raise
    except Exception as exc:  # noqa: BLE001 - rollback boundary
        if profile_saved:
            drop_profile(staged.workspace_id, home=home)
        if moved and staged.target_vault.exists() and not staged.staging_dir.exists():
            os_replace(staged.target_vault, staged.staging_dir)
        save_registry(original_registry, home=home)
        raise RemoteCloneError(
            "remote_confirm_failed", "连接确认失败，已回滚本次 staging 与本机档案"
        ) from exc


def os_replace(source: Path, destination: Path) -> None:
    """可 monkeypatch 的原子移动点，便于验证中途失败回滚。"""
    import os

    os.replace(source, destination)


def cancel_remote_clone(staged: RemoteCloneStage) -> None:
    """取消只清理本次 staging，不触碰目标目录或本机 profile。"""
    _clean_stage(staged.staging_dir)
