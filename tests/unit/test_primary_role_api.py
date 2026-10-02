"""Main/secondary device role control plane was removed from the product."""

from __future__ import annotations

from fastapi.testclient import TestClient

from summit_workbench.webapp.app import WebContext, create_app


def test_device_role_claim_and_downgrade_routes_are_retired(tmp_path) -> None:
    client = TestClient(
        create_app(WebContext(tmp_path / "vault", tmp_path, "UTC"), static_dir=tmp_path)
    )
    assert client.post("/api/sync/primary/claim", json={"device_id": "test"}).status_code == 404
    assert client.post("/api/sync/primary/downgrade").status_code == 404
