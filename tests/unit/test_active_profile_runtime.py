"""P0-07C production active-profile/runtime contract tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from summit_workbench.config.profiles import (
    ProfileResolutionState,
    resolve_active_workspace,
)
from summit_workbench.domain.workspace import Compatibility, LocalProfile, WorkspaceManifest
from summit_workbench.providers.feishu.config import load_feishu_config
from summit_workbench.providers.llm.config import load_model_config
from summit_workbench.repositories.profile_registry import (
    load_profile,
    save_profile,
    set_active_profile,
)
from summit_workbench.repositories.workspace_manifest import write_workspace_manifest
from summit_workbench.webapp.app import WebContext, create_app


def _profile(
    home: Path, workspace_id: str = "11111111-1111-4111-8111-111111111111"
) -> LocalProfile:
    work_root = home / "chosen-work"
    return LocalProfile.model_validate(
        {
            "schema_version": 1,
            "workspace_id": workspace_id,
            "display_name": "Chosen",
            "work_root": str(work_root),
            "vault_dir": str(work_root / "_vault"),
            "created_at": "2026-09-05T00:00:00Z",
            "provider_note": "must-survive",
        }
    )


def _manifest(workspace_id: str) -> WorkspaceManifest:
    return WorkspaceManifest.model_validate(
        {
            "schema_version": 2,
            "workspace_id": workspace_id,
            "display_name": "Chosen",
            "created_at": "2026-09-05T00:00:00Z",
            "min_reader_version": "0.5.0",
            "min_writer_version": "0.5.0",
        }
    )


def test_active_context_is_single_runtime_source_and_reads_marker(
    tmp_path: Path, monkeypatch
) -> None:
    home = tmp_path / "home"
    profile = _profile(home)
    profile.vault_dir.mkdir(parents=True)
    save_profile(profile, home=home)
    set_active_profile(profile.workspace_id, home=home)
    write_workspace_manifest(profile.vault_dir, _manifest(profile.workspace_id))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "wrong-env"))

    context = resolve_active_workspace(home=home, app_version="0.5.0")

    assert context.profile == profile
    assert context.paths is not None
    assert context.paths.vault_dir == profile.vault_dir
    assert context.workspace_id == profile.workspace_id
    assert context.compatibility is Compatibility.READ_WRITE
    expected_config = (
        home
        / "Library/Application Support/SummitWorkbench/profiles"
        / profile.workspace_id
        / "config.toml"
    )
    assert context.config_file == expected_config
    assert context.device_id


def test_empty_production_context_does_not_construct_default_vault(
    tmp_path: Path, monkeypatch
) -> None:
    home = tmp_path / "empty-home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "wrong-env"))

    context = resolve_active_workspace(home=home, allow_env_fallback=False)

    assert context.resolution.state is ProfileResolutionState.ONBOARDING_REQUIRED
    assert context.profile is None
    assert context.paths is None
    assert not (home / "Documents" / "Work").exists()


def test_unknown_profile_fields_survive_save_roundtrip(tmp_path: Path) -> None:
    home = tmp_path / "home"
    profile = _profile(home)
    save_profile(profile, home=home)

    loaded = profile.model_copy(update={"display_name": "Renamed"})
    save_profile(loaded, home=home)
    raw = (
        home
        / "Library/Application Support/SummitWorkbench/profiles"
        / profile.workspace_id
        / "config.toml"
    ).read_text()

    assert 'provider_note = "must-survive"' in raw
    reloaded = load_profile(profile.workspace_id, home=home)
    assert reloaded is not None
    assert reloaded.model_extra is not None
    assert "provider_note" in reloaded.model_extra


def test_provider_configs_use_active_profile_file_and_workspace_scope(tmp_path: Path) -> None:
    home = tmp_path / "home"
    profile = _profile(home)
    save_profile(profile, home=home)
    config_file = (
        home
        / "Library/Application Support/SummitWorkbench/profiles"
        / profile.workspace_id
        / "config.toml"
    )
    config_file.write_text(
        """[feishu]
app_id = "app-a"
redirect_uri = "http://localhost/cb"

[models.shared]
model_id = "model-a"
base_url = "https://model.example"
credential_account = "shared"
"""
    )

    feishu = load_feishu_config(config_file, workspace_id=profile.workspace_id)
    model = load_model_config("review", config_file, workspace_id=profile.workspace_id)

    assert feishu.app_secret_ref.service.endswith(profile.workspace_id)
    assert feishu.app_secret_ref.account == "feishu:app-a:app_secret"
    assert model.api_key_ref.service.endswith(profile.workspace_id)
    assert model.api_key_ref.account == "llm:review:shared"


def test_incompatible_active_profile_is_exposed_for_backend_gate(tmp_path: Path) -> None:
    home = tmp_path / "home"
    profile = _profile(home)
    profile.vault_dir.mkdir(parents=True)
    save_profile(profile, home=home)
    set_active_profile(profile.workspace_id, home=home)
    manifest = _manifest(profile.workspace_id).model_copy(update={"min_writer_version": "9.0.0"})
    write_workspace_manifest(profile.vault_dir, manifest)

    context = resolve_active_workspace(home=home, app_version="0.5.0")

    assert context.compatibility is Compatibility.READ_ONLY_UPGRADE_REQUIRED

    ctx = WebContext.from_active_workspace(context)
    assert ctx is not None
    client = TestClient(create_app(ctx, static_dir=tmp_path / "missing-static"))
    response = client.post("/api/capture", json={"text": "must be blocked"})
    assert response.status_code == 409
    assert response.json()["code"] == "workspace_read_only_upgrade_required"


def test_remote_normalization_is_allowed_before_schema_upgrade(
    tmp_path: Path,
) -> None:
    """HTTPS normalization must break the old-schema migration deadlock."""
    home = tmp_path / "home"
    profile = _profile(home)
    profile.vault_dir.mkdir(parents=True)
    save_profile(profile, home=home)
    set_active_profile(profile.workspace_id, home=home)
    write_workspace_manifest(
        profile.vault_dir,
        _manifest(profile.workspace_id).model_copy(update={"min_writer_version": "9.0.0"}),
    )

    context = resolve_active_workspace(home=home, app_version="0.5.0")
    assert context.compatibility is Compatibility.READ_ONLY_UPGRADE_REQUIRED
    ctx = WebContext.from_active_workspace(context)
    assert ctx is not None
    client = TestClient(create_app(ctx, static_dir=tmp_path / "missing-static"))

    response = client.post(
        "/api/settings/git/remote/apply",
        json={"plan_id": "missing-plan", "git_username": "user", "pat": "pat"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "normalization_plan_missing"


def test_cannot_open_profile_gets_restricted_control_plane(tmp_path: Path) -> None:
    home = tmp_path / "home"
    profile = _profile(home)
    save_profile(profile, home=home)
    set_active_profile(profile.workspace_id, home=home)
    context = resolve_active_workspace(home=home, app_version="0.5.0")

    assert context.compatibility is Compatibility.CANNOT_OPEN
    assert WebContext.from_active_workspace(context) is None
    app = create_app(None, static_dir=tmp_path / "missing-static")
    assert "/api/onboarding/status" in {getattr(route, "path", "") for route in app.routes}
