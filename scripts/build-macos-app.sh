#!/usr/bin/env bash
# 把本地 Web 面板打包成 macOS .app（原生 Dock 图标，双击启动）。
#
# 双击 App → 启动 `wb web`（前台，App 存活=服务存活）→ 在独立应用窗口打开面板
# （优先 Chrome app 模式，退化到默认浏览器）。退出 App（Cmd-Q / Dock 退出）即关服务。
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

# 原生启动器：编译 Swift（AppKit 生命周期）。
# 脚本型主程序会造成 Dock 图标无限弹跳（前台）或 macOS 报「应用无响应」（LSUIElement）；
# 原生主程序注册正常的应用生命周期，根治两者，并保持「无 Dock 图标 + 网页退出」体验。
TMP_SWIFT="$(mktemp -d)/summit_launcher.swift"
sed -e "s|__WB_BIN__|$WB_BIN|g" \
    -e "s|__PORT__|$PORT|g" \
    -e "s|__WORK_ROOT__|$WORK_ROOT|g" \
  "$REPO_ROOT/scripts/summit_launcher.swift" > "$TMP_SWIFT"
if ! xcrun swiftc -O "$TMP_SWIFT" -o "$APP/Contents/MacOS/SummitWorkbench" 2>"$TMP_SWIFT.err"; then
  echo "✗ Swift 编译失败（需要 Xcode 命令行工具：xcode-select --install）" >&2
  head -5 "$TMP_SWIFT.err" >&2
  rm -rf "$(dirname "$TMP_SWIFT")"
  exit 1
fi
chmod +x "$APP/Contents/MacOS/SummitWorkbench"
rm -rf "$(dirname "$TMP_SWIFT")"

echo "✓ 已构建 $APP"
echo "  wb=$WB_BIN  WORK_ROOT=$WORK_ROOT  端口=$PORT"
echo "  安装：拖到 /Applications，或  open \"$APP\""
echo "  提示：首次打开若被 Gatekeeper 拦，右键→打开，或 xattr -dr com.apple.quarantine \"$APP\""
