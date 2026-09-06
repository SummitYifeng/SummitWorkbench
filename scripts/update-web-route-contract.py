#!/usr/bin/env python3
"""Regenerate the P1-03 Web route contract from the explicit app factory."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from summit_workbench.webapp.app_factory import AppContext, create_app
from summit_workbench.webapp.route_contract import route_contract

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="swb-route-contract-") as directory:
        root = Path(directory)
        application = create_app(
            AppContext(root / "vault", root / "work", "UTC"),
            static_dir=root / "static",
        )
        target = ROOT / "docs/contracts/web-route-contract.json"
        target.write_text(
            json.dumps(route_contract(application), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
