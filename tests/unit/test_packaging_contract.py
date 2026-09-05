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
    assert "server.run(sockets=[sock])" in source


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
    assert "BACKUP_APP" in install
    assert "STAGED_APP" in install
    assert "--replace-running" in install
