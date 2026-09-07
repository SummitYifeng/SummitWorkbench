"""P0-10 Web /api/sync/* 与 automation 门 / capture guard / /api/state 摘要测试。

临时 HOME、临时目录；不触真实远端或 ~/Documents/Work。
"""

from __future__ import annotations

import json
import uuid
import zipfile
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from summit_workbench.domain.workspace import DeviceRole, LocalProfile
from summit_workbench.repositories.profile_registry import save_profile, set_active_profile
from summit_workbench.webapp.app import WebContext, create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("HOME", str(tmp_path / "fake-home"))
    monkeypatch.delenv("WORK_ROOT", raising=False)
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "nonexistent.toml"))
    app = create_app(
        WebContext(tmp_path / "vault", tmp_path / "vault", "UTC"),
        static_dir=tmp_path / "no-static",
    )
    return TestClient(app)


def _profile(home: Path, role: DeviceRole) -> LocalProfile:
    workspace_id = str(uuid.uuid4())
    profile = LocalProfile.model_validate(
        {
            "schema_version": 1,
            "workspace_id": workspace_id,
            "display_name": "role-ws",
            "work_root": str(home / "work"),
            "vault_dir": str(home / "work" / "_vault"),
            "device_role": role.value,
            "created_at": datetime.now(UTC).isoformat(),
        }
    )
    save_profile(profile, home=home)
    set_active_profile(workspace_id, home=home)
    return profile


def test_sync_status_and_run_on_plain_vault(tmp_path, monkeypatch, client) -> None:
    status = client.get("/api/sync/status")
    assert status.status_code == 200
    data = status.json()
    assert data["ok"] is True
    assert data["state"] == "unconfigured"
    run = client.post("/api/sync/run")
    assert run.status_code == 200
    assert run.json()["ok"] is True


def test_conflict_explanation_is_read_only_and_classifies_paths(client) -> None:
    response = client.get(
        "/api/sync/conflict/explain",
        params={"paths": "_events/device-a/2026/09/e.json,logs/2026-09-07-001.md"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["conflict"]["manual_required"] is True
    assert [item["kind"] for item in payload["conflict"]["items"]] == [
        "append-only-event",
        "manual-markdown",
    ]


def test_conflict_recovery_plan_is_read_only_and_exposes_safe_stage(client) -> None:
    response = client.get(
        "/api/sync/conflict/plan",
        params={"paths": "_events/device-a/2026/09/e.json,_views/thread-a.json"},
    )

    assert response.status_code == 200
    plan = response.json()["recovery_plan"]
    assert plan["stage"] == "not-applicable"  # plain test vault is unconfigured
    assert plan["write_required"] is False
    assert "force-push" in plan["forbidden_actions"]


def test_conflict_details_is_not_applicable_outside_divergence(client) -> None:
    response = client.get("/api/sync/conflict/details")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "available": False,
        "state": "unconfigured",
        "reason": "当前 workspace 不在 diverged-protected 状态",
    }


def test_conflict_export_contains_only_recovery_manifest(client) -> None:
    response = client.get("/api/sync/conflict/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(BytesIO(response.content)) as archive:
        assert archive.namelist() == ["sync-recovery-manifest.json"]
        manifest = json.loads(archive.read(archive.namelist()[0]))
    assert manifest["kind"] == "sync-recovery-manifest"
    assert "vault body" in manifest["content_policy"]


def test_conflict_selection_validation_is_protected_outside_divergence(client) -> None:
    response = client.post(
        "/api/sync/conflict/selection/validate",
        json={
            "base_revision": "0" * 40,
            "local_revision": "1" * 40,
            "remote_revision": "2" * 40,
            "selections": {},
        },
    )

    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.json()["state"] == "unconfigured"


def test_conflict_recovery_is_protected_outside_divergence(client) -> None:
    response = client.post(
        "/api/sync/conflict/recover",
        json={
            "base_revision": "0" * 40,
            "local_revision": "1" * 40,
            "remote_revision": "2" * 40,
            "confirmed": True,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": False,
        "available": False,
        "state": "unconfigured",
        "reason": "当前 workspace 不在 diverged-protected 状态",
    }


def test_state_payload_includes_sync_summary(tmp_path, monkeypatch, client) -> None:
    state = client.get("/api/state")
    assert state.status_code == 200
    assert "sync_state" in state.json()
    assert state.json()["sync_state"] in {
        "unconfigured",
        "ready",
        "offline-local-ahead",
        "remote-ahead",
        "local-ahead",
        "diverged-protected",
        "dirty-protected",
        "auth-required",
        "error",
        "syncing",
    }


def test_run_brief_and_weekly_skipped_on_secondary(tmp_path, monkeypatch, client) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "fake-home"))
    _profile(tmp_path / "fake-home", DeviceRole.SECONDARY)
    for path in ("/api/run/brief", "/api/run/weekly"):
        resp = client.post(path)
        assert resp.status_code == 200, path
        body = resp.json()
        assert body["ok"] is True
        assert body["skipped"] is True
        assert body["code"] == "not_automation_primary"
    sync = client.post("/api/sync/run")
    assert sync.status_code == 200
    assert sync.json()["ok"] is True


def test_run_brief_allowed_on_primary_even_if_model_offline(tmp_path, monkeypatch, client) -> None:
    _profile(tmp_path / "fake-home", DeviceRole.AUTOMATION_PRIMARY)
    resp = client.post("/api/run/brief")
    # primary 允许执行；模型/飞书离线时按既有降级语义返回 200（ok=True 或可见失败），
    # 绝不是 403/not_automation_primary
    assert resp.status_code == 200
    assert "not_automation_primary" not in resp.text
