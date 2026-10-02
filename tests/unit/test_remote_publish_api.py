"""Work library remote configuration and publish APIs are retired."""

from __future__ import annotations

from fastapi.testclient import TestClient

from summit_workbench.webapp.app import WebContext, create_app


def test_remote_configuration_and_publish_routes_are_retired(tmp_path) -> None:
    client = TestClient(
        create_app(WebContext(tmp_path / "vault", tmp_path, "UTC"), static_dir=tmp_path)
    )
    for path in ("/api/settings/git/remote/preview", "/api/settings/git/remote/apply"):
        assert client.post(path, json={}).status_code == 404
    assert client.post("/api/remote/publish").status_code == 404
