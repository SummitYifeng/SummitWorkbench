#!/usr/bin/env bash
# 把本地 Web 面板打包成 macOS .app（原生 Dock 图标，双击启动）。
#
# 双击 App → 原生 WKWebView 壳监督 `wb web` → 等待 /api/version readiness
# → 以 canonical build URL 加载唯一面板窗口。Chrome 仅在显式的开发回滚构建中保留。
#
# 不需要 Rust/Tauri，只用系统自带工具。wb 路径在构建时烘焙进去（同 launchd 安装）；
# 仓库若迁移，重跑本脚本即可。产物在 dist/（已 gitignore）。
#
# 用法：scripts/build-macos-app.sh   [PORT 默认 8787]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WB_BIN="${WB_BIN:-$REPO_ROOT/.venv/bin/wb}"
WORK_ROOT="${WORK_ROOT:-$HOME/Documents/Work}"
PORT="${1:-8787}"
APP="$REPO_ROOT/dist/SummitWorkbench.app"

if [[ ! -x "$WB_BIN" ]]; then
  echo "✗ 找不到 wb：$WB_BIN（先 uv sync --extra web，或用 WB_BIN= 指定）" >&2
  exit 1
fi

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

# 图标：若有源图 assets/icon-1024.png，用系统自带 sips + iconutil 生成 AppIcon.icns。
ICON_KEY=""
SRC_ICON="$REPO_ROOT/assets/icon-1024.png"
if [[ -f "$SRC_ICON" ]] && command -v iconutil >/dev/null && command -v sips >/dev/null; then
  ICONSET="$(mktemp -d)/AppIcon.iconset"
  mkdir -p "$ICONSET"
  for s in 16 32 128 256 512; do
    sips -z "$s" "$s" "$SRC_ICON" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
    d=$((s * 2))
    sips -z "$d" "$d" "$SRC_ICON" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
  done
  iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/AppIcon.icns"
  ICON_KEY="  <key>CFBundleIconFile</key><string>AppIcon</string>"
  echo "✓ 已生成应用图标 AppIcon.icns"
else
  echo "ℹ 未找到 assets/icon-1024.png（或缺 sips/iconutil），使用系统默认图标"
  echo "  可先运行：uv run --with pillow python scripts/make-icon.py assets/icon-1024.png"
fi

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>SummitWorkbench</string>
  <key>CFBundleDisplayName</key><string>SummitWorkbench</string>
  <key>CFBundleIdentifier</key><string>com.summitworkbench.panel</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>SummitWorkbench</string>
$ICON_KEY
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>LSUIElement</key><true/>
  <key>LSMultipleInstancesProhibited</key><true/>
</dict></plist>
PLIST

# 原生启动器：编译 Swift 多文件（AppKit + WebKit、服务监督、WKWebView 生命周期）。
# `WB_RENDERER=chrome` 仅供开发回滚，生产默认永远走 WKWebView。
TMP_ROOT="$(mktemp -d)"
if [[ "${WB_RENDERER:-webview}" == "chrome" ]]; then
  source="$REPO_ROOT/scripts/summit_launcher.swift"
  target="$TMP_ROOT/$(basename "$source")"
  sed -e "s|__WB_BIN__|$WB_BIN|g" \
      -e "s|__PORT__|$PORT|g" \
      -e "s|__WORK_ROOT__|$WORK_ROOT|g" \
    "$source" > "$target"
  SWIFT_SOURCES=("$target")
else
  SWIFT_SOURCES=()
  for source in "$REPO_ROOT"/native/SummitWorkbench/*.swift; do
    target="$TMP_ROOT/$(basename "$source")"
    sed -e "s|__WB_BIN__|$WB_BIN|g" \
        -e "s|__PORT__|$PORT|g" \
        -e "s|__WORK_ROOT__|$WORK_ROOT|g" \
      "$source" > "$target"
    SWIFT_SOURCES+=("$target")
  done
fi
SWIFT_ERR="$TMP_ROOT/swift.err"
if ! xcrun swiftc -O -target "$(uname -m)-apple-macosx13.0" \
    -framework AppKit -framework WebKit "${SWIFT_SOURCES[@]}" \
    -o "$APP/Contents/MacOS/SummitWorkbench" 2>"$SWIFT_ERR"; then
  echo "✗ Swift 编译失败（需要 Xcode 命令行工具：xcode-select --install）" >&2
  head -20 "$SWIFT_ERR" >&2
  rm -rf "$TMP_ROOT"
  exit 1
fi
chmod +x "$APP/Contents/MacOS/SummitWorkbench"

# manifest 与已经提交的静态构建绑定；Phase 4 再把静态资源和 server 搬入 bundle。
FRONTEND_BUILD="$($REPO_ROOT/.venv/bin/python -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["frontend_build"])' "$REPO_ROOT/src/summit_workbench/webapp/static/build-meta.json")"
cat > "$APP/Contents/Resources/build-manifest.json" <<MANIFEST
{
  "schema_version": 1,
  "product_id": "com.summitworkbench.panel",
  "frontend_build": "$FRONTEND_BUILD",
  "port": $PORT
}
MANIFEST
rm -rf "$TMP_ROOT"

echo "✓ 已构建 $APP"
echo "  wb=$WB_BIN  WORK_ROOT=$WORK_ROOT  端口=$PORT"
echo "  安装：拖到 /Applications，或  open \"$APP\""
echo "  提示：首次打开若被 Gatekeeper 拦，右键→打开，或 xattr -dr com.apple.quarantine \"$APP\""
