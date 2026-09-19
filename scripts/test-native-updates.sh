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
# **丢掉外部注入的 `SDKROOT`**（`env -u`）：macOS 的 git 包装器在跑钩子时会导出
# `SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk`，而该 SDK 可能比当前编译器新
# （2026-09-19 真机：CLT SDK 是 MacOSX27.0/Swift 6.4，编译器是 6.3.3）⇒ `xcrun swiftc` 报
# "this SDK is not supported by the compiler"，于是 `git push` 的 pre-push 门禁必挂，
# 而同一个脚本在前台**单独跑必过**——这个"钩子里挂、外面过"的偶发失败就是这么来的。
# 本步骤只做行为测试、编译目标固定为 macosx13.0，没有理由听凭环境变量改 SDK；
# 去掉后由 `xcrun` 按当前工具链正常解析（CLT-only 的机器同样成立）。
env -u SDKROOT xcrun swiftc -O -target arm64-apple-macosx13.0 \
  -framework AppKit -framework CryptoKit \
  "${SWIFT_SOURCES[@]}" -o "$TEST_ROOT/UpdateCoordinatorTests"

TEST_HOME="$TEST_ROOT/home"
mkdir -p "$TEST_HOME"
HOME="$TEST_HOME" WB_PANEL_MODE=production "$TEST_ROOT/UpdateCoordinatorTests"
