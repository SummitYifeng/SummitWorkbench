"""P0-11B profile settings/switching safety tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from summit_workbench.config.profiles import resolve_active_workspace
from summit_workbench.domain.automation import AutomationRunStatus
from summit_workbench.domain.workspace import DeviceRole, LocalProfile, WorkspaceManifest
from summit_workbench.repositories.profile_registry import (
    active_profile_id,
    save_profile,
    set_active_profile,
)
from summit_workbench.repositories.workspace_manifest import write_workspace_manifest
from summit_workbench.webapp.app import WebContext, create_app
from summit_workbench.workflows.automation_worker import WorkerResult
from summit_workbench.workflows.profile_settings import (
    commit_profile_switch,
    list_profile_summaries,
    prepare_profile_switch,
    remove_local_profile,
    update_provider_settings,
)


def _profile(home: Path, label: str) -> LocalProfile:
    workspace_id = str(uuid4())
    vault = home / f"vault-{label}"
    vault.mkdir(parents=True)
    profile = LocalProfile(
        workspace_id=workspace_id,
        display_name=f"Workspace {label}",
        work_root=home,
        vault_dir=vault,
        device_role=DeviceRole.SECONDARY,
        created_at=datetime.now(UTC),
    )
    save_profile(profile, home=home)
    write_workspace_manifest(
        vault,
        WorkspaceManifest(
            workspace_id=workspace_id,
            display_name=profile.display_name,
            created_at=datetime.now(UTC),
            min_reader_version="0.1.0",
            min_writer_version="0.1.0",
        ),
    )
    return profile


def test_profiles_are_summarized_with_only_active_absolute_path(tmp_path: Path) -> None:
    first = _profile(tmp_path, "a")
    second = _profile(tmp_path, "b")
    set_active_profile(second.workspace_id, home=tmp_path)
    set_active_profile(first.workspace_id, home=tmp_path)

    summaries = {item.workspace_id: item for item in list_profile_summaries(home=tmp_path)}
    assert summaries[first.workspace_id].active is True
    assert summaries[first.workspace_id].path == str(first.vault_dir)
    assert summaries[second.workspace_id].path == second.vault_dir.name
    assert summaries[first.workspace_id].workspace_short_code == first.workspace_id.split("-")[0]


def test_switch_prepare_commit_changes_only_active_profile(tmp_path: Path) -> None:
    first = _profile(tmp_path, "a")
    second = _profile(tmp_path, "b")
    set_active_profile(second.workspace_id, home=tmp_path)
    set_active_profile(first.workspace_id, home=tmp_path)
    before = (second.vault_dir / ".summit-workbench" / "workspace.json").read_bytes()

    plan = prepare_profile_switch(home=tmp_path, target_workspace_id=second.workspace_id)
    result = commit_profile_switch(home=tmp_path, plan=plan)
    assert result["restart_required"] is True
    assert active_profile_id(home=tmp_path) == second.workspace_id
    assert (second.vault_dir / ".summit-workbench" / "workspace.json").read_bytes() == before


def test_remove_profile_never_deletes_vault_or_changes_remote(tmp_path: Path) -> None:
    first = _profile(tmp_path, "a")
    second = _profile(tmp_path, "b")
    set_active_profile(first.workspace_id, home=tmp_path)
    vault = second.vault_dir
    marker = vault / "keep.md"
    marker.write_text("keep", encoding="utf-8")
    runtime = (
        tmp_path
        / "Library/Application Support/SummitWorkbench/profiles"
        / second.workspace_id
        / "runtime"
    )
    runtime.mkdir(parents=True)
    (runtime / "runtime.json").write_text("{}", encoding="utf-8")

    result = remove_local_profile(home=tmp_path, workspace_id=second.workspace_id, confirmed=True)
    assert result["vault_deleted"] is False
    assert result["remote_changed"] is False
    assert result["keychain_changed"] is False
    assert marker.read_text(encoding="utf-8") == "keep"
    assert not (runtime / "runtime.json").exists()


def test_settings_api_exposes_prepare_commit_and_safe_remove(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    first = _profile(tmp_path, "a")
    second = _profile(tmp_path, "b")
    set_active_profile(second.workspace_id, home=tmp_path)
    set_active_profile(first.workspace_id, home=tmp_path)
    context = resolve_active_workspace(home=tmp_path, allow_env_fallback=False)
    client = TestClient(create_app(WebContext.from_active_workspace(context)))

    listed = client.get("/api/settings/profiles")
    assert listed.status_code == 200
    assert {item["workspace_id"] for item in listed.json()["profiles"]} == {
        first.workspace_id,
        second.workspace_id,
    }
    prepared = client.post(
        "/api/settings/profile/prepare", json={"workspace_id": second.workspace_id}
    )
    assert prepared.status_code == 200
    blocked = client.post("/api/capture", json={"text": "must wait for switch"})
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "sync_diverged"
    committed = client.post(
        "/api/settings/profile/commit", json={"plan_id": prepared.json()["plan_id"]}
    )
    assert committed.status_code == 200
    assert committed.json()["restart_required"] is True
    assert active_profile_id(home=tmp_path) == second.workspace_id

    preview = client.post("/api/settings/profile/remove", json={"workspace_id": first.workspace_id})
    assert preview.status_code == 409
    assert preview.json()["code"] == "confirmation_required"


def test_automation_settings_api_roundtrips_and_validates_schedule(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    profile = _profile(tmp_path, "automation")
    set_active_profile(profile.workspace_id, home=tmp_path)
    context = resolve_active_workspace(home=tmp_path, allow_env_fallback=False)
    client = TestClient(create_app(WebContext.from_active_workspace(context)))

    listed = client.get("/api/settings/automation")
    assert listed.status_code == 200
    assert listed.json()["workspace_id"] == profile.workspace_id
    assert listed.json()["jobs"]["brief"]["enabled"] is False
    assert listed.json()["jobs"]["meeting-sync"]["supported"] is False
    assert listed.json()["jobs"]["meeting-sync"]["unavailable_reason"]

    saved = client.put(
        "/api/settings/automation",
        json={
            "job": "brief",
            "enabled": True,
            "hour": 9,
            "minute": 15,
            "weekdays": [0, 1, 2, 3, 4],
        },
    )
    assert saved.status_code == 200
    assert saved.json()["job"]["hour"] == 9
    assert saved.json()["job"]["weekdays"] == [0, 1, 2, 3, 4]

    reread = client.get("/api/settings/automation")
    assert reread.json()["jobs"]["brief"]["enabled"] is True
    assert reread.json()["jobs"]["brief"]["minute"] == 15

    invalid = client.put(
        "/api/settings/automation",
        json={"job": "brief", "enabled": True, "hour": 24, "minute": 0, "weekdays": []},
    )
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "validation_error"


def test_automation_manual_run_is_skipped_on_secondary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    profile = _profile(tmp_path, "secondary-automation")
    set_active_profile(profile.workspace_id, home=tmp_path)
    context = resolve_active_workspace(home=tmp_path, allow_env_fallback=False)
    client = TestClient(create_app(WebContext.from_active_workspace(context)))

    # secondary 的「立即运行」是预期跳过，不是错误：200 + ok=true + status=not-primary。
    response = client.post("/api/settings/automation/run", json={"job": "brief"})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["status"] == "not-primary"


def test_automation_manual_run_forces_execution_after_same_day_run(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    profile = _profile(tmp_path, "manual-automation")
    set_active_profile(profile.workspace_id, home=tmp_path)
    context = resolve_active_workspace(home=tmp_path, allow_env_fallback=False)
    client = TestClient(create_app(WebContext.from_active_workspace(context)))
    calls: list[bool] = []

    def fake_run(context, job, *, force=False, **_kwargs):
        calls.append(force)
        return WorkerResult(job, AutomationRunStatus.SUCCESS, published="committed")

    monkeypatch.setattr("summit_workbench.workflows.automation_worker.run_automation_job", fake_run)
    response = client.post("/api/settings/automation/run", json={"job": "brief"})

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert calls == [True]


def test_unsupported_meeting_sync_cannot_enable_or_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    profile = _profile(tmp_path, "unsupported-meeting")
    set_active_profile(profile.workspace_id, home=tmp_path)
    context = resolve_active_workspace(home=tmp_path, allow_env_fallback=False)
    client = TestClient(create_app(WebContext.from_active_workspace(context)))

    saved = client.put(
        "/api/settings/automation",
        json={
            "job": "meeting-sync",
            "enabled": True,
            "hour": 8,
            "minute": 30,
            "weekdays": list(range(7)),
        },
    )
    assert saved.status_code == 409
    assert saved.json()["code"] == "automation_not_supported"

    run = client.post("/api/settings/automation/run", json={"job": "meeting-sync"})
    assert run.status_code == 409
    assert run.json()["code"] == "automation_not_supported"


def test_provider_secret_is_scoped_and_never_written_to_profile(
    tmp_path: Path, monkeypatch
) -> None:
    profile = _profile(tmp_path, "provider")
    calls: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        "summit_workbench.workflows.profile_settings.store_workspace_credential",
        lambda workspace, account, value: calls.append(
            (workspace, account, value.get_secret_value())
        ),
    )

    result = update_provider_settings(
        home=tmp_path,
        workspace_id=profile.workspace_id,
        provider="model",
        settings={"capability": "qa", "model_id": "local-model", "base_url": "http://model"},
        secret="do-not-persist",
    )
    assert result["secret_saved"] is True
    assert calls == [(profile.workspace_id, "llm:qa:shared", "do-not-persist")]
    raw = (
        tmp_path
        / "Library/Application Support/SummitWorkbench/profiles"
        / profile.workspace_id
        / "config.toml"
    ).read_text(encoding="utf-8")
    assert "do-not-persist" not in raw
    assert "local-model" in raw
