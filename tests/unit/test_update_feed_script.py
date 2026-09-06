from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_generator_emits_sha256_size_signature_and_public_key(tmp_path: Path) -> None:
    key = tmp_path / "update-key.pem"
    dmg = tmp_path / "SummitWorkbench.dmg"
    output = tmp_path / "update-feed.json"
    dmg.write_bytes(b"offline-dmg-fixture")
    generated = subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(key)])
    if generated.returncode != 0:
        pytest.skip("当前离线工具链的 openssl 不提供 Ed25519；发布机需使用支持 Ed25519 的 openssl")

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
    )

    feed = json.loads(output.read_text(encoding="utf-8"))
    artifact = feed["artifacts"][0]
    assert artifact["size"] == dmg.stat().st_size
    assert artifact["sha256"] == hashlib.sha256(dmg.read_bytes()).hexdigest()
    assert len(base64.b64decode(artifact["signature"])) == 64
    assert len(base64.b64decode(artifact["public_key"])) == 32
