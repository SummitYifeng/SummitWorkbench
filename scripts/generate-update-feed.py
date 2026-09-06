#!/usr/bin/env python3
"""Generate a signed Ed25519 update feed without touching workspace data.

The private key is deliberately supplied by the release environment and is never
written to the repository or application bundle.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from summit_workbench.updates.feed import signing_payload

OPENSSL_BIN = os.environ.get("OPENSSL_BIN", "openssl")


def _run(*args: str, input_data: bytes | None = None) -> bytes:
    return subprocess.check_output((OPENSSL_BIN, *args), input=input_data)


def _public_key(private_key: Path) -> str:
    der = _run("pkey", "-in", str(private_key), "-pubout", "-outform", "DER")
    if len(der) < 32:
        raise ValueError("Ed25519 公钥 DER 无效")
    return base64.b64encode(der[-32:]).decode("ascii")


def _signature(private_key: Path, payload: bytes) -> str:
    with tempfile.NamedTemporaryFile() as raw:
        raw.write(payload)
        raw.flush()
        signature = _run(
            "pkeyutl",
            "-sign",
            "-rawin",
            "-inkey",
            str(private_key),
            "-in",
            raw.name,
        )
    return base64.b64encode(signature).decode("ascii")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--private-key", required=True, type=Path)
    parser.add_argument("--product-id", default="com.summitworkbench.panel")
    parser.add_argument("--version", required=True)
    parser.add_argument("--build", required=True)
    parser.add_argument("--architecture", default="arm64")
    parser.add_argument("--minimum-macos", default="13.0")
    parser.add_argument("--download-url", required=True)
    parser.add_argument("--dmg", required=True, type=Path)
    parser.add_argument("--release-notes", default="")
    parser.add_argument("--workspace-schema-version", type=int, default=2)
    parser.add_argument("--workspace-min-reader-version", default="0.4.1")
    parser.add_argument("--workspace-min-writer-version", default="0.4.1")
    parser.add_argument(
        "--require-openssl3",
        action="store_true",
        help="拒绝 LibreSSL/OpenSSL 1.x；发布门必须使用 OpenSSL 3",
    )
    args = parser.parse_args()

    if not args.private_key.is_file():
        parser.error(f"找不到更新 feed 私钥：{args.private_key}")
    if not args.dmg.is_file():
        parser.error(f"找不到 DMG：{args.dmg}")
    openssl_version = _run("version").decode("utf-8", errors="replace").strip()
    if args.require_openssl3 and not openssl_version.startswith("OpenSSL 3."):
        parser.error(f"签名发布必须使用 OpenSSL 3，当前为：{openssl_version}")
    digest = hashlib.sha256(args.dmg.read_bytes()).hexdigest()
    artifact = {
        "version": args.version,
        "build": args.build,
        "architecture": args.architecture,
        "minimum_macos": args.minimum_macos,
        "download_url": args.download_url,
        "sha256": digest,
        "size": args.dmg.stat().st_size,
        "release_notes": args.release_notes,
        "workspace_schema": {
            "schema_version": args.workspace_schema_version,
            "min_reader_version": args.workspace_min_reader_version,
            "min_writer_version": args.workspace_min_writer_version,
        },
    }
    artifact["signature"] = _signature(
        args.private_key, signing_payload(artifact, product_id=args.product_id)
    )
    artifact["public_key"] = _public_key(args.private_key)
    # 生成后立即用同一个 public key 做真实验签；只得到可解码的 64 字节签名不算通过。
    with (
        tempfile.NamedTemporaryFile() as signature_file,
        tempfile.NamedTemporaryFile() as raw,
        tempfile.NamedTemporaryFile() as public_key_file,
    ):
        signature_file.write(base64.b64decode(artifact["signature"], validate=True))
        signature_file.flush()
        raw.write(signing_payload(artifact, product_id=args.product_id))
        raw.flush()
        public_key_file.write(_run("pkey", "-in", str(args.private_key), "-pubout"))
        public_key_file.flush()
        verified = subprocess.run(
            (
                OPENSSL_BIN,
                "pkeyutl",
                "-verify",
                "-rawin",
                "-pubin",
                "-inkey",
                public_key_file.name,
                "-in",
                raw.name,
                "-sigfile",
                signature_file.name,
            ),
            capture_output=True,
            check=False,
        )
    if verified.returncode != 0:
        raise RuntimeError(
            "OpenSSL Ed25519 真实验签失败："
            + verified.stderr.decode("utf-8", errors="replace").strip()
        )
    payload = {
        "schema_version": 1,
        "product_id": args.product_id,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "artifacts": [artifact],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
