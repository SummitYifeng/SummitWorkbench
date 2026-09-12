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
    assert "terminateOwnedServer" in runtime
    assert "orphan_service_termination" in source
    assert "desiredStop" in source
    assert "RuntimeRecord" in source
    assert "dateDecodingStrategy = .iso8601" in runtime


def test_service_supervisor_pins_runtime_record_path_for_the_child() -> None:
    """子进程的 runtime 记录路径必须显式传给服务端。

    服务端默认从 ``Path.home()``（认 ``$HOME``）推导记录路径，而 App 用
    ``NSHomeDirectory()``（不认 ``$HOME``）去读。正常启动下两者一致；但 ``$HOME`` 与账户
    家目录不同时（例如从终端以自定义 HOME 启动），服务端写下的记录 App 永远找不到，
    启动就卡在 ``readiness_timeout`` 循环里。显式传 ``WB_RUNTIME_RECORD`` 消除该隐式假设。
    """
    source = _source("ServiceSupervisor.swift")
    runtime = _source("RuntimeRecord.swift")
    # 必须用 App 自己读取记录的那个 URL，否则等于没对齐。
    assert 'environment["WB_RUNTIME_RECORD"] = RuntimeRecord.url.path' in source
    assert "static var url: URL" in runtime
    assert "NSHomeDirectory()" in runtime


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
    main = (_ROOT / "web" / "src" / "legacy-main.ts").read_text(encoding="utf-8")
    assert "clientReady" in bridge
    assert "postMessage" in bridge
    assert "notifyClientReady(CLIENT_BUILD, remote.server_instance)" in main
    assert "sendNativeMessage({ type: 'quit' })" in main


def test_settings_doctor_declares_json_and_sync_export_supports_native_save() -> None:
    bridge = (_ROOT / "web" / "src" / "lifecycle" / "native-bridge.ts").read_text(encoding="utf-8")
    main = (_ROOT / "web" / "src" / "legacy-main.ts").read_text(encoding="utf-8")
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


def test_p101_automation_manager_handles_all_smappservice_states() -> None:
    manager = _source("AutomationServiceManager.swift")
    policy = _source("AutomationServicePolicy.swift")
    assert "case .notRegistered, .notFound:" in manager
    assert "case .enabled:" in manager
    assert "case .requiresApproval:" in manager
    assert "AutomationServiceControlling" in manager
    assert "SMAppServiceController" in policy
    assert "automation_registration_waiting_approval" in manager
    assert '"status": statusDescription(service.status)' in manager
    assert '"domain": (error as NSError).domain' in manager
    assert 'helperBundle.bundleIdentifier == "com.summitworkbench.panel.automation"' in manager


def test_p101_native_state_behavior_test_is_in_repository() -> None:
    script = (_ROOT / "scripts" / "test-native-automation.sh").read_text(encoding="utf-8")
    test = (_ROOT / "native" / "tests" / "AutomationServiceManagerTests.swift").read_text(
        encoding="utf-8"
    )
    conftest = (_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert "AutomationServiceManagerTests.swift" in script
    assert "helperValidator: {}" in test
    assert "AutomationServiceStatus.notFound" in test
    assert 'monkeypatch.setenv("HOME", str(fake_home))' in conftest


def test_p101_uses_smappservice_and_preserves_native_bridge_controls() -> None:
    all_native = "\n".join(path.read_text(encoding="utf-8") for path in _NATIVE.glob("*.swift"))
    build = (_ROOT / "scripts" / "build-macos-app.sh").read_text(encoding="utf-8")
    bridge = (_ROOT / "web" / "src" / "lifecycle" / "native-bridge.ts").read_text(encoding="utf-8")
    assert "import ServiceManagement" in all_native
    assert "SMAppService.loginItem" in all_native
    assert "automationSettingsChanged" in all_native
    assert "automationSettingsChanged" in bridge
    assert "Contents/Library/LoginItems" in build
    assert "codesign" in build
