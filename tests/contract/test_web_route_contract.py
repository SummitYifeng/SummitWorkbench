"""P1-03 route contract snapshot：拆分不得改变 Web API 表面。"""

from __future__ import annotations

from summit_workbench.webapp.app_factory import AppContext, create_app
from summit_workbench.webapp.route_contract import route_contract


def test_retired_git_product_routes_are_absent(tmp_path) -> None:
    app = create_app(AppContext(tmp_path / "vault", tmp_path / "work", "UTC"), static_dir=tmp_path)
    paths = {entry["path"] for entry in route_contract(app)}
    assert not any(
        path.startswith(("/api/sync", "/api/undo", "/api/settings/git/")) for path in paths
    )
    assert "/api/settings/model-parameters" in paths


def test_live_route_contract_snapshot_is_current(tmp_path) -> None:
    app = create_app(AppContext(tmp_path / "vault", tmp_path / "work", "UTC"), static_dir=tmp_path)
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    expected = json.loads((root / "docs/contracts/web-route-contract.json").read_text())
    assert route_contract(app) == expected
