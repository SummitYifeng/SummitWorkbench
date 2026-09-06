"""Smoke test for a PyInstaller-backed SummitWorkbench.app bundle."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from pathlib import Path
from urllib.request import Request, urlopen

import pytest


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


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
    assert server.is_file() and server.stat().st_mode & 0o111
    assert static_dir.is_dir()
    static_meta = json.loads((static_dir / "build-meta.json").read_text(encoding="utf-8"))
    assert manifest["frontend_build"] == static_meta["frontend_build"]

    port = _free_port()
    work_root = tmp_path / "work"
    work_root.mkdir()
    environment = {
        "HOME": str(tmp_path / "home"),
        "PATH": "/usr/bin:/bin",
        "WORK_ROOT": str(work_root),
        "WB_RUNTIME_RECORD": str(tmp_path / "runtime.json"),
        "WB_PANEL_MODE": "production",
        "WB_STATIC_DIR": str(static_dir),
        "WB_PROMPTS_DIR": str(resources / "prompts"),
        "WB_SESSION_TOKEN": "integration-session-token",
    }
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
    finally:
        process.terminate()
        process.wait(timeout=5)
