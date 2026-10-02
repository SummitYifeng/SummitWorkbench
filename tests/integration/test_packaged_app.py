"""Smoke test for a PyInstaller-backed SummitWorkbench.app bundle."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from pathlib import Path
from typing import cast
from urllib.request import Request, urlopen

import pytest


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _run_tls_diagnostic(executable: Path, environment: dict[str, str]) -> dict[str, object]:
    result = subprocess.run(
        [str(executable), "--tls-diagnostic"]
        if executable.name == "SummitWorkbenchServer"
        else [str(executable)],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert result.stderr == ""
    payload = cast(dict[str, object], json.loads(result.stdout))
    assert payload["ca_bundle_present"] is True
    assert payload["ca_bundle_source"] == "pyinstaller-bundle"
    assert payload["ssl_context_status"] == "ok"
    assert payload["ssl_context_verify_mode"] == "CERT_REQUIRED"
    assert payload["ssl_context_check_hostname"] is True
    assert payload["dulwich_transport_status"] == "ok"
    assert payload["dulwich_ca_bundle_present"] is True
    assert payload["dulwich_cert_reqs"] == "CERT_REQUIRED"
    return payload


@pytest.mark.integration
def test_packaged_server_runs_without_repository_python(tmp_path: Path) -> None:
    app_value = os.environ.get("WB_PACKAGED_APP")
    if not app_value:
        pytest.skip("set WB_PACKAGED_APP to run the packaged-app smoke test")
    app = Path(app_value).resolve()
    resources = app / "Contents" / "Resources"
    manifest = json.loads((resources / "build-manifest.json").read_text(encoding="utf-8"))
    static_dir = resources / "web" / "static"
    server = resources / "server" / "SummitWorkbenchServer"
    worker = app / "Contents" / "Helpers" / "SummitWorkbenchWorker"
    assert server.is_file() and server.stat().st_mode & 0o111
    assert not worker.exists()
    assert not (app / "Contents" / "Library" / "LoginItems").exists()
    assert static_dir.is_dir()
    static_meta = json.loads((static_dir / "build-meta.json").read_text(encoding="utf-8"))
    assert manifest["frontend_build"] == static_meta["frontend_build"]

    port = _free_port()
    work_root = tmp_path / "work"
    work_root.mkdir()
    empty_path = tmp_path / "empty-path"
    empty_path.mkdir()
    environment = {
        "HOME": str(tmp_path / "home"),
        "PATH": str(empty_path),
        "WORK_ROOT": str(work_root),
        "WB_RUNTIME_RECORD": str(tmp_path / "runtime.json"),
        "WB_PANEL_MODE": "production",
        "WB_STATIC_DIR": str(static_dir),
        "WB_PROMPTS_DIR": str(resources / "prompts"),
        "WB_SESSION_TOKEN": "integration-session-token",
    }
    diagnostic_environment = {
        "HOME": str(tmp_path / "home"),
        "PATH": "/usr/bin:/bin",
        "WB_PANEL_MODE": "production",
    }
    _run_tls_diagnostic(server, diagnostic_environment)
    process = subprocess.Popen(
        [
            str(server),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--work-root",
            str(work_root),
            "--static-dir",
            str(static_dir),
        ],
        cwd=tmp_path,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.monotonic() + 20
        payload: dict[str, object] | None = None
        while time.monotonic() < deadline:
            try:
                request = Request(
                    f"http://127.0.0.1:{port}/api/version",
                    headers={"X-WB-Session-Token": "integration-session-token"},
                )
                with urlopen(request, timeout=1) as response:
                    payload = json.load(response)
                    break
            except Exception:
                time.sleep(0.25)
        assert payload is not None, process.stdout.read() if process.stdout else ""
        assert payload["product_id"] == "com.summitworkbench.panel"
        assert payload["frontend_build"] == manifest["frontend_build"]
        protocol = payload["api_protocol"]
        assert isinstance(protocol, int) and protocol >= 2

        created_workspace = tmp_path / "created-workspace"
        create_request = Request(
            f"http://127.0.0.1:{port}/api/onboarding/create",
            data=json.dumps({"work_root": str(created_workspace)}).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-WB-Session-Token": "integration-session-token",
            },
        )
        with urlopen(create_request, timeout=5) as response:
            create_payload = json.load(response)
        assert create_payload["ok"] is True
        assert (created_workspace / "inbox.md").is_file()
        assert (created_workspace / "conventions.md").is_file()
        assert (created_workspace / ".summit-workbench" / "manifest.json").is_file()
        assert not (created_workspace / ".git").exists()
    finally:
        process.terminate()
        process.wait(timeout=5)
