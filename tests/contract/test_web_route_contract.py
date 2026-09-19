"""P1-03 route contract snapshot：拆分不得改变 Web API 表面。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.routing import APIRoute

from summit_workbench.webapp.app_factory import AppContext, create_app
from summit_workbench.webapp.route_contract import route_contract


def test_web_route_contract_snapshot_is_unchanged(tmp_path: Path) -> None:
    app = create_app(AppContext(tmp_path / "vault", tmp_path / "work", "UTC"), static_dir=tmp_path)
    root = Path(__file__).resolve().parents[2]
    expected = json.loads(
        (root / "docs/contracts/web-route-contract.json").read_text(encoding="utf-8")
    )

    assert route_contract(app) == expected


def test_sync_route_registration_order_is_stable(tmp_path: Path) -> None:
    app = create_app(AppContext(tmp_path / "vault", tmp_path / "work", "UTC"), static_dir=tmp_path)
    actual = [
        route.path
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith("/api/sync")
    ]
    assert actual == [
        "/api/sync/status",
        "/api/sync/conflict/explain",
        "/api/sync/conflict/plan",
        "/api/sync/conflict/details",
        "/api/sync/conflict/validate",
        "/api/sync/conflict/export",
        "/api/sync/conflict/selection/validate",
        "/api/sync/conflict/recover",
        "/api/sync/export",
        "/api/sync/primary/claim",
        "/api/sync/primary/downgrade",
        "/api/sync/run",
    ]
