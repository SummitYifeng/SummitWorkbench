"""P0-10 Web /api/sync/* 与 automation 门 / capture guard / /api/state 摘要测试。

临时 HOME、临时目录；不触真实远端或 ~/Documents/Work。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
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
