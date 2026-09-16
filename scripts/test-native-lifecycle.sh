#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/summitworkbench-native-lifecycle-test.XXXXXX")"
trap 'rm -rf "$TEST_ROOT"' EXIT

xcrun swiftc -O -target arm64-apple-macosx13.0 \
  "$REPO_ROOT/native/SummitWorkbench/ProcessTermination.swift" \
  "$REPO_ROOT/native/tests/ServiceSupervisorTests.swift" \
  -o "$TEST_ROOT/ServiceSupervisorTests"

"$TEST_ROOT/ServiceSupervisorTests"

xcrun swiftc -O -target arm64-apple-macosx13.0 \
  "$REPO_ROOT/native/SummitWorkbench/Models.swift" \
  "$REPO_ROOT/native/SummitWorkbench/RuntimeRecord.swift" \
  "$REPO_ROOT/native/tests/RuntimeRecoveryRecordTests.swift" \
  -o "$TEST_ROOT/RuntimeRecoveryRecordTests"

HOME="$TEST_ROOT/home" "$TEST_ROOT/RuntimeRecoveryRecordTests"
