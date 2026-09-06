#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/summitworkbench-update-test.XXXXXX")"
trap 'rm -rf "$TEST_ROOT"' EXIT

SWIFT_SOURCES=(
  "$REPO_ROOT/native/SummitWorkbench/Models.swift"
  "$REPO_ROOT/native/SummitWorkbench/PrivacyRedactor.swift"
  "$REPO_ROOT/native/SummitWorkbench/StructuredLogger.swift"
  "$REPO_ROOT/native/SummitWorkbench/UpdateCoordinator.swift"
  "$REPO_ROOT/native/tests/UpdateCoordinatorTests.swift"
)
xcrun swiftc -O -target arm64-apple-macosx13.0 \
  -framework AppKit -framework CryptoKit \
  "${SWIFT_SOURCES[@]}" -o "$TEST_ROOT/UpdateCoordinatorTests"

TEST_HOME="$TEST_ROOT/home"
mkdir -p "$TEST_HOME"
HOME="$TEST_HOME" WB_PANEL_MODE=production "$TEST_ROOT/UpdateCoordinatorTests"
