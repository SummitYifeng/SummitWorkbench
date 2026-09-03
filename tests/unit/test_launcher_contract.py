"""Phase 2 contract checks for the temporary Chrome-based macOS launcher."""

from __future__ import annotations

from pathlib import Path

_LAUNCHER = Path(__file__).resolve().parents[2] / "scripts" / "summit_launcher.swift"


def _source() -> str:
    return _LAUNCHER.read_text(encoding="utf-8")


def test_cold_start_uses_readiness_before_opening_panel() -> None:
    source = _source()
    assert 'panelURL.appendingPathComponent("api/version")' in source
    assert "startServerIfNeeded { [weak self] version in" in source
    assert "self?.migrateAndOpenPanel(version)" in source
    assert source.index("startServerIfNeeded { [weak self] version in") < source.index(
        "private func openPanel(_ version: VersionPayload)"
    )


def test_reopen_coalesces_readiness_and_uses_canonical_build_url() -> None:
    source = _source()
    assert "applicationShouldHandleReopen" in source
    assert "readinessInFlight" in source
    assert 'URLQueryItem(name: "build", value: version.frontend_build)' in source


def test_first_migration_is_strict_and_recoverable() -> None:
    source = _source()
    assert "chrome-window-refresh-v1.done" in source
    assert 'command.contains("--user-data-dir=\\(panelProfilePath)")' in source
    assert '!command.contains("--type=")' in source
    assert "kill(pid, SIGTERM)" in source
    assert "timeIntervalSince(startedAt) >= 5.0" in source
