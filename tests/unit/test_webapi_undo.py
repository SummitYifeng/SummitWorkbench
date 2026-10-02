"""Work library Git undo routes are retired together with their commit history."""

from __future__ import annotations

from fastapi.testclient import TestClient

from summit_workbench.webapp.app import WebContext, create_app


def test_git_undo_routes_are_retired(tmp_path) -> None:
    client = TestClient(
        create_app(WebContext(tmp_path / "vault", tmp_path, "UTC"), static_dir=tmp_path)
    )
    for method, path in (
        ("GET", "/api/undo/history"),
        ("GET", "/api/undo/diff"),
        ("POST", "/api/undo/revert"),
    ):
        response = client.post(path, json={}) if method == "POST" else client.get(path)
        assert response.status_code == 404
