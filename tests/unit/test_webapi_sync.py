"""The work library no longer exposes Git synchronization or device-role routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from summit_workbench.webapp.app import WebContext, create_app


def test_git_sync_conflict_and_role_routes_are_retired(tmp_path) -> None:
    client = TestClient(
        create_app(WebContext(tmp_path / "vault", tmp_path, "UTC"), static_dir=tmp_path)
    )
    retired = (
        ("GET", "/api/sync/status"),
        ("POST", "/api/sync/run"),
        ("POST", "/api/sync/conflict/recover"),
        ("POST", "/api/sync/primary/claim"),
        ("POST", "/api/sync/primary/downgrade"),
    )
    for method, path in retired:
        response = client.post(path, json={}) if method == "POST" else client.get(path)
        assert response.status_code == 404
