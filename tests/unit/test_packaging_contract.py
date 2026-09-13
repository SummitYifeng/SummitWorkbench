"""Phase 4 packaging contract checks."""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def test_packaging_spec_collects_runtime_and_project_data() -> None:
    spec = (_ROOT / "packaging" / "SummitWorkbenchServer.spec").read_text(encoding="utf-8")
    assert 'collect_submodules("summit_workbench")' in spec
    assert 'collect_submodules("dulwich")' in spec
    assert '"dulwich.client"' in spec
    assert '"certifi"' in spec
    assert '"prompts"' in spec
    assert '"templates"' in spec
    assert 'name="SummitWorkbenchServer"' in spec


def test_server_entry_requires_bundle_static_directory() -> None:
    source = (_ROOT / "src/summit_workbench/webapp/server_entry.py").read_text(encoding="utf-8")
    assert "--static-dir" in source
    assert "create_app(" in source
    assert "bind_host=args.host" in source
    assert "port=args.port" in source
    assert "uvicorn.Server" in source


def test_p012_server_entry_uses_dynamic_port_and_runtime_identity() -> None:
    source = (_ROOT / "src/summit_workbench/webapp/server_entry.py").read_text(encoding="utf-8")
    assert "default=0" in source
    assert "socket.socket" in source
    assert "write_runtime_record" in source
    assert "server.run(sockets=sockets)" in source
    assert "_bind_feishu_callback_socket" in source


def test_p012_native_manifest_does_not_own_a_fixed_port() -> None:
    source = (_ROOT / "native/SummitWorkbench/Models.swift").read_text(encoding="utf-8")
    assert "struct BuildManifest" in source
    assert "let port: Int\n" not in source
    assert "runtime.json" in (_ROOT / "native/SummitWorkbench/RuntimeRecord.swift").read_text(
        encoding="utf-8"
    )


def test_build_and_install_scripts_are_self_contained_and_atomic() -> None:
    build = (_ROOT / "scripts/build-macos-app.sh").read_text(encoding="utf-8")
    install = (_ROOT / "scripts/install-macos-app.sh").read_text(encoding="utf-8")
    assert "PyInstaller" in build
    assert "Resources/server" in build
    assert "Resources/web/static" in build
    assert "codesign --verify --deep --strict" in build
    assert "--runtime-record" in build
    assert "BACKUP_APP" in install
    assert "STAGED_APP" in install
    assert "--replace-running" in install


def test_install_script_finds_runtime_records_where_the_app_writes_them() -> None:
    """runtime record 有两个合法落点，安装脚本必须都查。

    打包 App 写 `<app_support>/runtime.json`（原生启动器经 `WB_RUNTIME_RECORD` 注入），
    `wb web` CLI 写 `<app_support>/profiles/*/runtime/runtime.json`。安装脚本一度只查后者，
    后果是：正在运行的 App 检测不到（绕过安全检查直接替换运行中的 App），以及服务其实已就绪
    却误报「未在 readiness 窗口内启动」并把 `.previous` 留在原地（2026-09-13 装 build 35 实测）。
    """
    install = (_ROOT / "scripts/install-macos-app.sh").read_text(encoding="utf-8")
    swift = (_ROOT / "native/SummitWorkbench/RuntimeRecord.swift").read_text(encoding="utf-8")
    # Swift 侧的候选集合：先根、再 profiles/**
    assert "candidateURLs" in swift
    assert 'appendingPathComponent("profiles")' in swift
    # bash 侧必须提供同口径的候选集合，且各处调用点都用它
    assert "runtime_records()" in install
    assert '"$RUNTIME_ROOT/runtime.json"' in install
    assert 'find "$RUNTIME_ROOT/profiles"' in install
    # 旧的「只查 profiles 下一处」的写法不得回归
    assert 'RUNTIME_FILE="$(find "$RUNTIME_ROOT/profiles"' not in install
    assert install.count("runtime_records") >= 4  # 定义 1 处 + 调用点


def test_p013_release_contract_is_versioned_arm64_internal_safe() -> None:
    build = (_ROOT / "scripts/build-macos-app.sh").read_text(encoding="utf-8")
    release = (_ROOT / "scripts/release-macos.sh").read_text(encoding="utf-8")
    verify = (_ROOT / "scripts/verify-macos-release.sh").read_text(encoding="utf-8")
    entitlements = (_ROOT / "packaging/entitlements.plist").read_text(encoding="utf-8")
    assert "pyproject.toml" in build
    assert "BUILD_NUMBER" in build
    assert "datetime.now" not in build
    assert "ARCH" in build
    assert '"$ARCH-apple-macosx13.0"' in build
    assert "INTERNAL-DEV" in build
    assert "x86_64" not in release
    assert "--timestamp=none" in build
    assert "not-applicable" in release
    assert "create-dmg" in release or "hdiutil" in release
    assert "shasum" in release or "shasum" in verify
    assert "SBOM" in release or "sbom" in release.lower()
    assert 'APP="$RELEASE_TMP/package/SummitWorkbench.app"' in release
    assert "codesign --verify --strict" in verify
    assert "spctl --assess" in verify
    assert "secret" in verify.lower()
    assert "com.apple.security.cs.disable-library-validation" not in entitlements


def test_p101_packages_a_self_contained_worker_and_native_helper() -> None:
    build = (_ROOT / "scripts" / "build-macos-app.sh").read_text(encoding="utf-8")
    spec = (_ROOT / "packaging" / "SummitWorkbenchWorker.spec").read_text(encoding="utf-8")
    helper = (_ROOT / "native" / "SummitWorkbench" / "AutomationHelperMain.swift").read_text(
        encoding="utf-8"
    )
    manager = (_ROOT / "native" / "SummitWorkbench" / "AutomationServiceManager.swift").read_text(
        encoding="utf-8"
    )
    policy = (_ROOT / "native" / "SummitWorkbench" / "AutomationServicePolicy.swift").read_text(
        encoding="utf-8"
    )
    assert "SummitWorkbenchWorker.spec" in build
    assert "Contents/Helpers/SummitWorkbenchWorker" in build
    assert "worker_entry.py" in spec
    assert "Process()" in helper
    assert "SMAppService.loginItem" in (manager + "\n" + policy)
    assert "launchctl" not in manager
