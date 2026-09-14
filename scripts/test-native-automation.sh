#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/summitworkbench-native-test.XXXXXX")"
trap 'rm -rf "$TEST_ROOT"' EXIT

SWIFT_SOURCES=(
  "$REPO_ROOT/native/SummitWorkbench/Models.swift"
  "$REPO_ROOT/native/SummitWorkbench/PrivacyRedactor.swift"
  "$REPO_ROOT/native/SummitWorkbench/StructuredLogger.swift"
  "$REPO_ROOT/native/SummitWorkbench/AutomationServicePolicy.swift"
  "$REPO_ROOT/native/SummitWorkbench/AutomationServiceManager.swift"
  "$REPO_ROOT/native/tests/AutomationServiceManagerTests.swift"
)
xcrun swiftc -O -target arm64-apple-macosx13.0 \
  -framework Security -framework ServiceManagement \
  "${SWIFT_SOURCES[@]}" -o "$TEST_ROOT/AutomationServiceManagerTests"

TEST_HOME="$TEST_ROOT/home"
mkdir -p "$TEST_HOME"
HOME="$TEST_HOME" WB_PANEL_MODE=production "$TEST_ROOT/AutomationServiceManagerTests"

# 给使用者看的文案（更新提示 / 服务状态中文名）。它们都是短中文字面量，Swift 的
# small-string 优化会把它们内联进代码 ⇒ 二进制里搜不到，只能在这里做**功能**单测。
UICOPY_SOURCES=(
  "$REPO_ROOT/native/SummitWorkbench/Models.swift"
  "$REPO_ROOT/native/SummitWorkbench/UICopy.swift"
  "$REPO_ROOT/native/tests/UICopyTests.swift"
)
xcrun swiftc -O -target arm64-apple-macosx13.0 \
  "${UICOPY_SOURCES[@]}" -o "$TEST_ROOT/UICopyTests"
"$TEST_ROOT/UICopyTests"
