"""P0-11B profile settings/switching safety tests."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from summit_workbench.config.profiles import resolve_active_workspace
from summit_workbench.config.secrets import CredentialError
from summit_workbench.domain.workspace import DeviceRole, LocalProfile, WorkspaceManifest
from summit_workbench.domain.workspace_contract import WorkspaceContractManifest
from summit_workbench.repositories.profile_registry import (
    active_profile_id,
    save_profile,
    set_active_profile,
)
from summit_workbench.repositories.workspace_contract import write_workspace_contract
from summit_workbench.repositories.workspace_manifest import write_workspace_manifest
from summit_workbench.webapp.app import WebContext, create_app
from summit_workbench.webapp.mutation_runtime import MutationRuntime
from summit_workbench.workflows.local_mutation import LocalMutationOutcome, MutationBlocked
from summit_workbench.workflows.profile_settings import (
    commit_profile_switch,
    list_profile_summaries,
    prepare_profile_switch,
    provider_status_for_profile,
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
    write_workspace_contract(vault, WorkspaceContractManifest(workspace_id=workspace_id))
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


def test_provider_status_detects_shared_model_keychain_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = _profile(tmp_path, "keychain")

    def resolve(workspace_id: str, account: str):
        assert workspace_id == profile.workspace_id
        if account == "llm:shared:shared":
            from pydantic import SecretStr

            return SecretStr("present")
        raise CredentialError("missing")

    monkeypatch.setattr(
        "summit_workbench.workflows.profile_settings.resolve_workspace_credential", resolve
    )
    assert provider_status_for_profile(profile)["model"] == "configured-keychain"


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
    assert blocked.json()["code"] == "workspace_switch_in_progress"
    committed = client.post(
        "/api/settings/profile/commit", json={"plan_id": prepared.json()["plan_id"]}
    )
    assert committed.status_code == 200
    assert committed.json()["restart_required"] is True
    assert active_profile_id(home=tmp_path) == second.workspace_id

    preview = client.post("/api/settings/profile/remove", json={"workspace_id": first.workspace_id})
    assert preview.status_code == 409
    assert preview.json()["code"] == "confirmation_required"


def test_profile_switch_waits_for_active_local_mutation(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    runtime = MutationRuntime(WebContext(vault, tmp_path, "UTC"), operation_id=lambda _req: "op")
    mutation_started = threading.Event()
    release_mutation = threading.Event()
    switch_finished = threading.Event()
    switch_results: list[bool] = []

    def mutation(_operation_id: str) -> LocalMutationOutcome[str]:
        mutation_started.set()
        assert release_mutation.wait(timeout=2)
        return LocalMutationOutcome("saved", ())

    writer = threading.Thread(target=lambda: runtime.run("test/write", mutation))
    writer.start()
    assert mutation_started.wait(timeout=2)

    def switch() -> None:
        switch_results.append(runtime.begin_profile_switch(timeout=2))
        switch_finished.set()

    switcher = threading.Thread(target=switch)
    switcher.start()
    assert not switch_finished.wait(timeout=0.05)
    with pytest.raises(MutationBlocked, match="正在切换"):
        runtime.run("test/late-write", lambda _operation_id: LocalMutationOutcome("late", ()))

    release_mutation.set()
    assert switch_finished.wait(timeout=2)
    writer.join(timeout=2)
    switcher.join(timeout=2)
    assert switch_results == [True]


def test_retired_automation_settings_routes_are_not_registered(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    profile = _profile(tmp_path, "automation-retired")
    set_active_profile(profile.workspace_id, home=tmp_path)
    context = resolve_active_workspace(home=tmp_path, allow_env_fallback=False)
    client = TestClient(create_app(WebContext.from_active_workspace(context)))

    assert client.get("/api/settings/automation").status_code == 404
    assert client.put("/api/settings/automation", json={}).status_code == 404
    assert client.post("/api/settings/automation/run", json={}).status_code == 404


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
        settings={"capability": "review", "model_id": "local-model", "base_url": "http://model"},
        secret="do-not-persist",
    )
    assert result["secret_saved"] is True
    assert calls == [(profile.workspace_id, "llm:review:shared", "do-not-persist")]
    raw = (
        tmp_path
        / "Library/Application Support/SummitWorkbench/profiles"
        / profile.workspace_id
        / "config.toml"
    ).read_text(encoding="utf-8")
    assert "do-not-persist" not in raw
    assert "local-model" in raw


def test_model_parameters_endpoint_reports_effective_values_without_secrets(
    tmp_path: Path, monkeypatch
) -> None:
    """只读参数接口：摊开每个任务真正生效的参数，且绝不回显任何凭据。

    动机（2026-09-18）：长逐字稿结构化失败的真因在 max_output_tokens / thinking，
    而设置页只看得到 model / base_url —— 用户没有任何地方能看到生效值。
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    profile = _profile(tmp_path, "a")
    set_active_profile(profile.workspace_id, home=tmp_path)
    context = resolve_active_workspace(home=tmp_path, allow_env_fallback=False)
    client = TestClient(create_app(WebContext.from_active_workspace(context)))

    response = client.get("/api/settings/model-parameters")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert "max_output_tokens" in body["note"]
    capabilities = [item["capability"] for item in body["items"]]
    assert capabilities == ["meeting", "review", "ranking", "capture", "digest"]
    by_cap = {item["capability"]: item for item in body["items"]}
    # 每个任务都带用途说明，界面才能解释「这行是干嘛的」。
    assert by_cap["digest"]["purpose"]
    # 绝不出现凭据字段（本接口是 workspace 级只读视图，不得泄漏 Keychain 内容）。
    serialized = response.text
    for forbidden in ("sk-", "api_key", "password", "secret", "credential_account"):
        assert forbidden not in serialized
