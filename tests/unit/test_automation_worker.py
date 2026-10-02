"""Background automation retirement prevents writes after the App closes."""

from __future__ import annotations

from pathlib import Path


def test_background_worker_has_no_cli_or_launchd_entrypoint() -> None:
    root = Path(__file__).resolve().parents[2]
    cli = (root / "src/summit_workbench/cli/main.py").read_text(encoding="utf-8")
    installer = (root / "scripts/install-launchd.sh").read_text(encoding="utf-8")
    lifecycle = (root / "native/SummitWorkbench/LifecycleCoordinator.swift").read_text(
        encoding="utf-8"
    )
    assert "add_typer(worker_app)" not in cli
    assert "automation_worker" not in cli
    assert "后台定时写入已退役" in installer
    assert "LegacyAutomationRetirement.retire()" in lifecycle
    assert "run_automation_job" not in lifecycle
