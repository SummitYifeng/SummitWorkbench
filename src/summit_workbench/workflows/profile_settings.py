"""Settings/profile operations for the configured-workspace UI (P0-11B)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from pydantic import SecretStr

from summit_workbench import __version__
from summit_workbench.config.app_support import app_support_dir, runtime_dir
from summit_workbench.config.git_credentials import strip_credentials
from summit_workbench.config.locking import workspace_lock
from summit_workbench.config.paths import resolve_work_paths
from summit_workbench.config.secrets import (
    CredentialError,
    delete_workspace_credential,
    resolve_workspace_credential,
    store_workspace_credential,
    workspace_account,
)
from summit_workbench.domain.workspace import (
    Compatibility,
    LocalProfile,
    evaluate_manifest_compatibility,
)
from summit_workbench.repositories.git import GitRepo
from summit_workbench.repositories.local_sync_state import load_sync_state
from summit_workbench.repositories.onboarding_draft import clear_onboarding_draft
from summit_workbench.repositories.profile_registry import (
    active_profile_id,
    drop_profile,
    load_profile,
    profile_ids,
    save_profile,
    set_active_profile,
)
from summit_workbench.repositories.workspace_manifest import load_workspace_manifest


class ProfileSettingsError(RuntimeError):
    """A profile operation was rejected without changing the vault."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ProfileSummary:
    workspace_id: str
    display_name: str
    workspace_short_code: str
    path: str
    compatibility: Compatibility
    device_role: str
    active: bool
    provider_status: dict[str, str]
    sync_summary: dict[str, object]
    remote_url: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "workspace_id": self.workspace_id,
            "workspace_short_code": self.workspace_short_code,
            "display_name": self.display_name,
            "path": self.path,
            "compatibility": self.compatibility.value,
            "device_role": self.device_role,
            "active": self.active,
            "provider_status": self.provider_status,
            "sync_summary": self.sync_summary,
            "remote_url": self.remote_url,
        }


@dataclass(frozen=True)
class ProfileSwitchPlan:
    plan_id: str
    target_workspace_id: str
    from_workspace_id: str | None


def list_profile_summaries(*, home: Path) -> list[ProfileSummary]:
    active = active_profile_id(home=home)
    summaries: list[ProfileSummary] = []
    for workspace_id in profile_ids(home=home):
        profile = load_profile(workspace_id, home=home)
        if profile is None:
            continue
        compatibility = _compatibility(profile)
        is_active = workspace_id == active
        summaries.append(
            ProfileSummary(
                workspace_id=workspace_id,
                workspace_short_code=workspace_id.split("-")[0],
                display_name=profile.display_name,
                # Other profiles never expose their absolute local path to the UI.
                path=str(profile.vault_dir) if is_active else profile.vault_dir.name,
                compatibility=compatibility,
                device_role=profile.device_role.value,
                active=is_active,
                provider_status=_provider_status(profile),
                sync_summary=_sync_summary(workspace_id, home=home),
                remote_url=_remote_url(profile),
            )
        )
    return summaries


def _remote_url(profile: LocalProfile) -> str | None:
    """Read the origin URL without network access or userinfo leakage."""
    try:
        url = GitRepo(profile.vault_dir, backend_kind="dulwich").remote_url("origin")
    except Exception:
        return profile.git_remote_url
    return strip_credentials(url) if url else profile.git_remote_url


def prepare_profile_switch(*, home: Path, target_workspace_id: str) -> ProfileSwitchPlan:
    profile = load_profile(target_workspace_id, home=home)
    if profile is None:
        raise ProfileSettingsError("profile_not_found", "目标工作台不在本机 profile 列表中")
    compatibility = _compatibility(profile)
    if compatibility is Compatibility.CANNOT_OPEN:
        raise ProfileSettingsError("workspace_not_compatible", "目标工作台无法由当前版本打开")
    return ProfileSwitchPlan(
        plan_id=str(uuid4()),
        target_workspace_id=target_workspace_id,
        from_workspace_id=active_profile_id(home=home),
    )


def commit_profile_switch(*, home: Path, plan: ProfileSwitchPlan) -> dict[str, object]:
    profile = load_profile(plan.target_workspace_id, home=home)
    if profile is None:
        raise ProfileSettingsError("profile_not_found", "目标工作台不在本机 profile 列表中")
    if _compatibility(profile) is Compatibility.CANNOT_OPEN:
        raise ProfileSettingsError("workspace_not_compatible", "目标工作台无法由当前版本打开")
    set_active_profile(plan.target_workspace_id, home=home)
    return {
        "ok": True,
        "workspace_id": plan.target_workspace_id,
        "from_workspace_id": plan.from_workspace_id,
        "restart_required": True,
    }


def remove_local_profile(*, home: Path, workspace_id: str, confirmed: bool) -> dict[str, object]:
    profile = load_profile(workspace_id, home=home)
    if profile is None:
        raise ProfileSettingsError("profile_not_found", "目标工作台不在本机 profile 列表中")
    if not confirmed:
        raise ProfileSettingsError(
            "confirmation_required", "请确认只移除本机 profile/runtime，不删除 vault"
        )
    was_active = active_profile_id(home=home) == workspace_id
    removed = drop_profile(workspace_id, home=home)
    runtime = runtime_dir(workspace_id, home=home)
    runtime_file = runtime / "runtime.json"
    if runtime_file.is_file():
        runtime_file.unlink()
        removed = True
    try:
        runtime.rmdir()
    except OSError:
        pass
    clear_onboarding_draft(home=home)
    return {
        "ok": removed,
        "workspace_id": workspace_id,
        "active": was_active,
        "restart_required": was_active,
        "deleted": ["local_profile", "runtime", "onboarding_draft"],
        "vault_deleted": False,
        "remote_changed": False,
        "keychain_changed": False,
    }


def _provider_settings_lock_root(home: Path, workspace_id: str) -> Path:
    """provider 设置读-改-写的锁根：每 workspace 一把，独立于 vault 锁。

    刻意不放在 profile 目录里：``workspace_lock`` 会创建锁文件所在目录，放在 profile 下
    会让「工作台不存在」的失败顺带造出一个空 profile 目录。
    """
    return app_support_dir(home) / "locks" / workspace_id


def update_provider_settings(
    *, home: Path, workspace_id: str, provider: str, settings: dict[str, object], secret: str | None
) -> dict[str, object]:
    """保存某 provider 的设置；整段读-改-写持有 per-workspace 锁。

    provider 段是**读-改-写**，而向导会先后写模型段与飞书段（模型验证与授权回调可能几乎
    同时到达）。没有互斥时后写者会基于自己读到的旧快照落盘，静默丢掉另一段——现象就是
    「授权明明成功，设置页却显示未连接」。这里把 load→改→save 整段串行化；锁在**线程内
    可重入**，同线程嵌套调用不会自锁。
    """
    with workspace_lock(_provider_settings_lock_root(home, workspace_id)):
        return _apply_provider_settings(
            home=home,
            workspace_id=workspace_id,
            provider=provider,
            settings=settings,
            secret=secret,
        )


def _apply_provider_settings(
    *, home: Path, workspace_id: str, provider: str, settings: dict[str, object], secret: str | None
) -> dict[str, object]:
    """Persist non-secret provider settings and write an optional secret once to scoped Keychain."""
    profile = load_profile(workspace_id, home=home)
    if profile is None:
        raise ProfileSettingsError("profile_not_found", "目标工作台不在本机 profile 列表中")
    allowed = {
        "model": {
            "capability",
            "model_id",
            "base_url",
            "credential_account",
            "credential_capability",
            "timeout_seconds",
            "max_output_tokens",
            "context_window_tokens",
            "context_safety_ratio",
            "pricing",
        },
        "feishu": {"app_id", "redirect_uri", "scopes", "secret_kind"},
        "git": {"host", "git_username", "secret_kind"},
    }.get(provider)
    if allowed is None or set(settings) - allowed:
        raise ProfileSettingsError("invalid_provider_settings", "provider 设置包含不支持或秘密字段")

    extras = dict(profile.model_extra or {})
    section_name = "models" if provider == "model" else provider
    section = (
        dict(extras.get(section_name, {})) if isinstance(extras.get(section_name), dict) else {}
    )
    if provider == "model":
        capability = str(settings.get("capability", "shared"))
        capability_section = (
            dict(section.get(capability, {})) if isinstance(section.get(capability), dict) else {}
        )
        capability_section.update(
            {k: v for k, v in settings.items() if k not in {"capability", "secret_kind"}}
        )
        section[capability] = capability_section
    else:
        section.update({k: v for k, v in settings.items() if k != "secret_kind"})

    update: dict[str, object] = {section_name: section}
    if provider == "git" and "git_username" in settings:
        update["git_username"] = settings["git_username"]

    account: str | None = None
    previous_secret: SecretStr | None = None
    if secret:
        if provider == "model":
            credential_capability = str(
                settings.get("credential_capability", settings.get("capability", "shared"))
            )
            account = workspace_account(
                "llm",
                credential_capability,
                str(settings.get("credential_account", "shared")),
            )
        elif provider == "feishu":
            account = workspace_account(
                "feishu",
                str(settings.get("app_id", "")),
                str(settings.get("secret_kind", "app_secret")),
            )
        else:
            account = workspace_account(
                "git", str(settings.get("host", "")), str(settings.get("git_username", ""))
            )
        if not account or account.endswith(":"):
            raise ProfileSettingsError(
                "invalid_provider_settings", "secret 需要完整的 provider 标识"
            )
        try:
            previous_secret = resolve_workspace_credential(workspace_id, account)
        except CredentialError:
            previous_secret = None
        try:
            store_workspace_credential(workspace_id, account, SecretStr(secret))
        except Exception as exc:
            raise ProfileSettingsError("credential_store_failed", "凭据暂时无法保存") from exc
    try:
        save_profile(profile.model_copy(update=update), home=home)
    except Exception as exc:
        if secret and account:
            try:
                if previous_secret is None:
                    delete_workspace_credential(workspace_id, account)
                else:
                    store_workspace_credential(workspace_id, account, previous_secret)
            except Exception:
                pass
        raise ProfileSettingsError("provider_settings_failed", "设置暂时无法保存") from exc
    return {
        "ok": True,
        "provider": provider,
        "credential_account": account,
        "secret_saved": bool(secret),
    }


def _compatibility(profile: LocalProfile) -> Compatibility:
    try:
        manifest = load_workspace_manifest(
            resolve_work_paths(work_root=profile.work_root, vault_dir=profile.vault_dir).vault_dir
        )
    except Exception:
        return Compatibility.CANNOT_OPEN
    if manifest is None:
        return Compatibility.CANNOT_OPEN
    return evaluate_manifest_compatibility(manifest, __version__)


def _provider_status(profile: LocalProfile) -> dict[str, str]:
    extras = profile.model_extra or {}
    return {
        "model": "configured" if isinstance(extras.get("models"), dict) else "not-configured",
        "feishu": "configured" if isinstance(extras.get("feishu"), dict) else "not-configured",
        "git": "configured" if profile.git_username else "not-configured",
    }


def _sync_summary(workspace_id: str, *, home: Path) -> dict[str, object]:
    """Return only the short, local sync facts needed by the settings list."""
    try:
        snapshot = load_sync_state(workspace_id, home=home)
    except ValueError:
        return {"state": "error", "pending_commits": None}
    if snapshot is None:
        return {"state": "not-checked", "pending_commits": None}
    return {
        "state": snapshot.state.value,
        "pending_commits": snapshot.pending_commits,
        "last_sync_at": snapshot.last_sync_at,
    }
