from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _openssl3() -> str:
    candidates = [
        Path("/opt/homebrew/opt/openssl@3/bin/openssl"),
        Path("/usr/local/opt/openssl@3/bin/openssl"),
        Path("/usr/bin/openssl"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            version = subprocess.check_output([str(candidate), "version"], text=True)
            if version.startswith("OpenSSL 3."):
                return str(candidate)
    raise AssertionError("P1-07C 真实签名测试需要 OpenSSL 3")


def test_generator_emits_sha256_size_signature_and_public_key(tmp_path: Path) -> None:
    key = tmp_path / "update-key.pem"
    dmg = tmp_path / "SummitWorkbench.dmg"
    output = tmp_path / "update-feed.json"
    dmg.write_bytes(b"offline-dmg-fixture")
    openssl = _openssl3()
    subprocess.run([openssl, "genpkey", "-algorithm", "ED25519", "-out", str(key)], check=True)

    subprocess.run(
        [
            str(ROOT / "scripts" / "generate-update-feed.py"),
            "--output",
            str(output),
            "--private-key",
            str(key),
            "--version",
            "0.4.2",
            "--build",
            "107",
            "--download-url",
            "https://updates.example.invalid/SummitWorkbench.dmg",
            "--dmg",
            str(dmg),
            "--release-notes",
            "fixture",
        ],
        check=True,
        cwd=ROOT,
        env={**os.environ, "OPENSSL_BIN": openssl},
    )

    feed = json.loads(output.read_text(encoding="utf-8"))
    artifact = feed["artifacts"][0]
    assert artifact["size"] == dmg.stat().st_size
    assert artifact["sha256"] == hashlib.sha256(dmg.read_bytes()).hexdigest()
    assert len(base64.b64decode(artifact["signature"])) == 64
    assert len(base64.b64decode(artifact["public_key"])) == 32
