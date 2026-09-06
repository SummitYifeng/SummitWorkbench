"""Phase 3 contract checks for the native WKWebView panel shell."""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_NATIVE = _ROOT / "native" / "SummitWorkbench"


def _source(name: str) -> str:
    return (_NATIVE / name).read_text(encoding="utf-8")


def test_production_native_shell_is_webkit_and_single_window() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in _NATIVE.glob("*.swift"))
    assert "import WebKit" in source
    assert "websiteDataStore = .default()" in source
    assert 'name: "wbLifecycle"' in source
    assert "applicationShouldTerminateAfterLastWindowClosed" in source
    assert "LSMultipleInstancesProhibited" in (_ROOT / "scripts/build-macos-app.sh").read_text(
        encoding="utf-8"
    )


def test_service_supervisor_has_identity_gate_and_recovery_states() -> None:
    source = _source("ServiceSupervisor.swift")
    runtime = _source("RuntimeRecord.swift")
    assert "apiProtocol >= panelAPIProtocol" in _source("Models.swift")
    assert "frontendBuild != configuration.manifest.frontendBuild" in source
    assert "service_crash_loop" in source
    assert "service_restart_scheduled" in source
    assert "terminateOwnedProcessBeforeRetry" in source
    assert "desiredStop" in source
    assert "RuntimeRecord" in source
    assert "dateDecodingStrategy = .iso8601" in runtime


def test_navigation_policy_rejects_non_panel_loopback() -> None:
    source = _source("PanelWindowController.swift")
    assert 'url.scheme?.lowercased() == "http"' in source
    assert 'url.host == "127.0.0.1"' in source
    assert "NSWorkspace.shared.open(url)" in source
    assert "decisionHandler(.cancel)" in source


def test_build_script_compiles_native_sources_and_writes_manifest() -> None:
    source = (_ROOT / "scripts" / "build-macos-app.sh").read_text(encoding="utf-8")
    assert "native/SummitWorkbench/*.swift" in source
    assert "-framework WebKit" in source
    assert "build-manifest.json" in source
    assert "native/SummitWorkbench/*.swift" in source
    assert "summit_launcher.swift" not in source


def test_web_native_bridge_reports_ready_and_supports_native_quit() -> None:
    bridge = (_ROOT / "web" / "src" / "lifecycle" / "native-bridge.ts").read_text(encoding="utf-8")
    main = (_ROOT / "web" / "src" / "main.ts").read_text(encoding="utf-8")
    assert "clientReady" in bridge
    assert "postMessage" in bridge
    assert "notifyClientReady(CLIENT_BUILD, remote.server_instance)" in main
    assert "sendNativeMessage({ type: 'quit' })" in main


def test_settings_doctor_declares_json_and_sync_export_supports_native_save() -> None:
    bridge = (_ROOT / "web" / "src" / "lifecycle" / "native-bridge.ts").read_text(encoding="utf-8")
    main = (_ROOT / "web" / "src" / "main.ts").read_text(encoding="utf-8")
    native = _source("Models.swift") + "\n" + _source("LifecycleCoordinator.swift")

    doctor = main[main.index("async function runSettingsDoctor") :]
    export = main[main.index("async function exportSyncSnapshot") :]
    assert "headers: { 'Content-Type': 'application/json' }" in doctor
    assert "saveTextFile" in bridge
    assert "sendNativeMessage({" in export
    assert "type: 'saveTextFile'" in export
    assert "document.body.appendChild(link)" in export
    assert "window.setTimeout(() =>" in export
    assert "URL.revokeObjectURL" in export
    assert "saveTextFile" in native
    assert "NSSavePanel" in native
