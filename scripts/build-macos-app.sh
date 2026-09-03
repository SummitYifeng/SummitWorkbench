#!/usr/bin/env bash
# 构建自包含的 macOS SummitWorkbench.app。
#
# 生产路径：bundle 内 server + bundle 内静态资源 + WKWebView 原生壳。
# Chrome 仅在显式 WB_RENDERER=chrome 的开发回滚构建中保留。
# 构建先完成临时 bundle、签名与 smoke test，最后才替换 dist 产物。
# 用法：scripts/build-macos-app.sh [PORT 默认 8787]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${1:-8787}"
WORK_ROOT="${WORK_ROOT:-$HOME/Documents/Work}"
WB_BIN="${WB_BIN:-$REPO_ROOT/.venv/bin/wb}"
PYTHON="$REPO_ROOT/.venv/bin/python"
STATIC_DIR="$REPO_ROOT/src/summit_workbench/webapp/static"
FINAL_APP="$REPO_ROOT/dist/SummitWorkbench.app"
SIGNING_IDENTITY="${SIGNING_IDENTITY:--}"

[[ -x "$PYTHON" ]] || { echo "✗ 找不到 Python：$PYTHON" >&2; exit 1; }
[[ -f "$STATIC_DIR/build-meta.json" ]] || { echo "✗ 缺少 build-meta.json，请先构建 web" >&2; exit 1; }
command -v npm >/dev/null || { echo "✗ 需要 npm" >&2; exit 1; }
command -v xcrun >/dev/null || { echo "✗ 需要 Xcode 命令行工具" >&2; exit 1; }
command -v codesign >/dev/null || { echo "✗ 需要 codesign" >&2; exit 1; }
"$PYTHON" -m PyInstaller --version >/dev/null || {
  echo "✗ 缺少 PyInstaller，请先 uv sync --extra web --extra packaging" >&2
  exit 1
}

# 先生成并验证唯一的前端构建身份，再打包 server；两者共享同一个 build-meta。
npm --prefix "$REPO_ROOT/web" run build
node "$REPO_ROOT/web/scripts/verify-build.mjs" "$STATIC_DIR"
"$PYTHON" -m pytest -q \
  "$REPO_ROOT/tests/unit/test_webapi.py" \
  "$REPO_ROOT/tests/unit/test_native_panel_contract.py"

FRONTEND_BUILD="$($PYTHON -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["frontend_build"])' "$STATIC_DIR/build-meta.json")"
BUILD_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/summitworkbench-build.XXXXXX")"
trap 'rm -rf "$BUILD_ROOT"' EXIT
APP="$BUILD_ROOT/SummitWorkbench.app"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/web/static" \
  "$APP/Contents/Resources/server" "$APP/Contents/Resources/prompts" \
  "$APP/Contents/Resources/templates"

# PyInstaller onedir：业务包全部进入 server，自包含运行时不依赖仓库 .venv。
"$PYTHON" -m PyInstaller --clean --noconfirm \
  --distpath "$BUILD_ROOT/server-dist" \
  --workpath "$BUILD_ROOT/server-work" \
  "$REPO_ROOT/packaging/SummitWorkbenchServer.spec"
cp -R "$BUILD_ROOT/server-dist/SummitWorkbenchServer/." "$APP/Contents/Resources/server/"

cp -R "$STATIC_DIR/." "$APP/Contents/Resources/web/static/"
cp -R "$REPO_ROOT/prompts/." "$APP/Contents/Resources/prompts/"
cp -R "$REPO_ROOT/templates/." "$APP/Contents/Resources/templates/"

# 图标：使用系统自带 sips + iconutil 生成 AppIcon.icns。
ICON_KEY=""
SRC_ICON="$REPO_ROOT/assets/icon-1024.png"
if [[ -f "$SRC_ICON" ]] && command -v iconutil >/dev/null && command -v sips >/dev/null; then
  ICONSET="$BUILD_ROOT/AppIcon.iconset"
  mkdir -p "$ICONSET"
  for size in 16 32 128 256 512; do
    sips -z "$size" "$size" "$SRC_ICON" --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
    double=$((size * 2))
    sips -z "$double" "$double" "$SRC_ICON" --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
  done
  iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/AppIcon.icns"
  ICON_KEY="  <key>CFBundleIconFile</key><string>AppIcon</string>"
fi

# 原生壳从 Resources/server 与 Resources/web/static 的相对路径启动服务。
TMP_SWIFT="$BUILD_ROOT/swift"
mkdir -p "$TMP_SWIFT"
SWIFT_SOURCES=()
if [[ "${WB_RENDERER:-webview}" == "chrome" ]]; then
  source="$REPO_ROOT/scripts/summit_launcher.swift"
  target="$TMP_SWIFT/$(basename "$source")"
  sed -e "s|__WB_BIN__|$WB_BIN|g" -e "s|__PORT__|$PORT|g" \
      -e "s|__WORK_ROOT__|$WORK_ROOT|g" "$source" > "$target"
  SWIFT_SOURCES+=("$target")
else
  for source in "$REPO_ROOT"/native/SummitWorkbench/*.swift; do
    target="$TMP_SWIFT/$(basename "$source")"
    sed -e "s|__WB_BIN__|$WB_BIN|g" -e "s|__PORT__|$PORT|g" \
        -e "s|__WORK_ROOT__|$WORK_ROOT|g" "$source" > "$target"
    SWIFT_SOURCES+=("$target")
  done
fi
xcrun swiftc -O -target "$(uname -m)-apple-macosx13.0" \
  -framework AppKit -framework WebKit "${SWIFT_SOURCES[@]}" \
  -o "$APP/Contents/MacOS/SummitWorkbench"
chmod +x "$APP/Contents/MacOS/SummitWorkbench"

SHORT_VERSION="$(date +%Y.%-m.%-d)"
BUNDLE_VERSION="$(date +%Y%m%d%H%M)"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0//EN" >
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>SummitWorkbench</string>
  <key>CFBundleDisplayName</key><string>SummitWorkbench</string>
  <key>CFBundleIdentifier</key><string>com.summitworkbench.panel</string>
  <key>CFBundleShortVersionString</key><string>$SHORT_VERSION</string>
  <key>CFBundleVersion</key><string>$BUNDLE_VERSION</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>SummitWorkbench</string>
$ICON_KEY
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>LSUIElement</key><true/>
  <key>LSMultipleInstancesProhibited</key><true/>
</dict></plist>
PLIST
cat > "$APP/Contents/Resources/build-manifest.json" <<MANIFEST
{
  "schema_version": 1,
  "product_id": "com.summitworkbench.panel",
  "frontend_build": "$FRONTEND_BUILD",
  "port": $PORT,
  "server_build": "$FRONTEND_BUILD"
}
MANIFEST

# 先签名嵌套 server，再签名 App；没有开发者证书时使用 ad-hoc 签名。
codesign --force --sign "$SIGNING_IDENTITY" "$APP/Contents/Resources/server/SummitWorkbenchServer"
codesign --force --sign "$SIGNING_IDENTITY" "$APP"
codesign --verify --deep --strict "$APP"

# 不依赖仓库 .venv 的 bundle server smoke：直接运行嵌套 server 与 bundle static。
SMOKE_PORT="$((PORT + 1))"
SMOKE_ROOT="$BUILD_ROOT/smoke-work"
mkdir -p "$SMOKE_ROOT"
SMOKE_SERVER="$APP/Contents/Resources/server/SummitWorkbenchServer"
WORK_ROOT="$SMOKE_ROOT" WB_PANEL_MODE=production \
  WB_STATIC_DIR="$APP/Contents/Resources/web/static" \
  WB_PROMPTS_DIR="$APP/Contents/Resources/prompts" \
  "$SMOKE_SERVER" --host 127.0.0.1 --port "$SMOKE_PORT" --work-root "$SMOKE_ROOT" \
  --static-dir "$APP/Contents/Resources/web/static" >"$BUILD_ROOT/smoke.log" 2>&1 &
SMOKE_PID=$!
for attempt in {1..40}; do
  if curl -fsS --max-time 1 "http://127.0.0.1:$SMOKE_PORT/api/version" >"$BUILD_ROOT/version.json" 2>/dev/null; then break; fi
  sleep 0.25
done
"$PYTHON" - "$BUILD_ROOT/version.json" "$FRONTEND_BUILD" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert payload["product_id"] == "com.summitworkbench.panel"
assert payload["frontend_build"] == sys.argv[2]
assert payload["api_protocol"] >= 2
PY
kill "$SMOKE_PID" 2>/dev/null || true
wait "$SMOKE_PID" 2>/dev/null || true

mkdir -p "$(dirname "$FINAL_APP")"
PREVIOUS_APP="$BUILD_ROOT/previous.app"
if [[ -d "$FINAL_APP" ]]; then mv "$FINAL_APP" "$PREVIOUS_APP"; fi
if ! mv "$APP" "$FINAL_APP"; then
  if [[ -d "$PREVIOUS_APP" ]]; then mv "$PREVIOUS_APP" "$FINAL_APP"; fi
  echo "✗ 原子替换 dist App 失败" >&2
  exit 1
fi

echo "✓ 已构建并验证 $FINAL_APP"
echo "  frontend=$FRONTEND_BUILD  port=$PORT  server=self-contained"
echo "  安装：scripts/install-macos-app.sh $FINAL_APP"
