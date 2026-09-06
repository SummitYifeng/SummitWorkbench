#!/usr/bin/env python3
"""扫描源码/发布元数据中的高置信度凭据特征（P1-06）。"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA|EC|OPENSSH|DSA) PRIVATE KEY-----"),
    re.compile(r"(?i)\bbearer\s+(?!\[redacted\])[A-Za-z0-9._~+/=-]{20,}"),
    re.compile(
        r"(?i)\b(?:api[_-]?key|refresh[_-]?token|password)\s*[:=]\s*['\"]"
        r"[A-Za-z0-9._~+/=-]{12,}"
        r"['\"]"
    ),
    re.compile(r"(?i)https?://[^/\s:@]+:[^@\s]+@"),
)
_BINARY_SUFFIXES = {".png", ".icns", ".dylib", ".so", ".bin", ".zip", ".dmg"}


def scan_text(text: str, *, source: str = "<text>") -> list[str]:
    findings: list[str] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if any(pattern.search(line) for pattern in _PATTERNS):
            findings.append(f"{source}:{line_number}")
    return findings


def scan_paths(paths: list[Path]) -> list[str]:
    findings: list[str] = []
    for path in paths:
        if path.suffix.lower() in _BINARY_SUFFIXES or not path.is_file():
            continue
        try:
            data = path.read_bytes()
            if b"\0" in data:
                continue
            text = data.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        findings.extend(scan_text(text, source=str(path)))
    return findings


def tracked_paths(root: Path) -> list[Path]:
    output = subprocess.check_output(
        ["git", "-C", str(root), "ls-files", "-z"], stderr=subprocess.STDOUT
    )
    return [root / item for item in output.decode().split("\0") if item]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths", nargs="*", type=Path, help="要扫描的路径；缺省扫描 Git tracked 文件"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    paths = [root / path if not path.is_absolute() else path for path in args.paths]
    findings = scan_paths(paths or tracked_paths(root))
    if findings:
        print("secret scan failed:", file=sys.stderr)
        print("\n".join(findings), file=sys.stderr)
        return 1
    print("secret scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
