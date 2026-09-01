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
  <key>LSUIElement</key><false/>
</dict></plist>
PLIST

# 启动器：前台跑 wb web（App 存活=服务存活），后台延时开面板窗口。
cat > "$APP/Contents/MacOS/SummitWorkbench" <<LAUNCHER
#!/usr/bin/env bash
export WORK_ROOT="$WORK_ROOT"
PORT="$PORT"
URL="http://127.0.0.1:\$PORT/"
LOG="\$HOME/Library/Logs/summitworkbench-panel.log"

open_panel() {
  for _ in \$(seq 1 40); do
    if curl -sf "\$URL" -o /dev/null 2>/dev/null; then break; fi
    sleep 0.25
  done
  CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
  if [[ -x "\$CHROME" ]]; then
    "\$CHROME" --app="\$URL" \\
      --user-data-dir="\$HOME/Library/Application Support/SummitWorkbench/browser" \\
      >/dev/null 2>&1 &
  else
    open "\$URL"
  fi
}

# 端口已被占用（服务已在跑）→ 只开窗口，保持本进程存活以维持 Dock 图标。
if curl -sf "\$URL" -o /dev/null 2>/dev/null; then
  open_panel
  # 无自有服务可 exec，睡眠维持 App 存活直至用户退出。
  while true; do sleep 3600; done
fi

open_panel &
exec "$WB_BIN" web --port "\$PORT" >>"\$LOG" 2>&1
LAUNCHER
chmod +x "$APP/Contents/MacOS/SummitWorkbench"

echo "✓ 已构建 $APP"
echo "  wb=$WB_BIN  WORK_ROOT=$WORK_ROOT  端口=$PORT"
echo "  安装：拖到 /Applications，或  open \"$APP\""
echo "  提示：首次打开若被 Gatekeeper 拦，右键→打开，或 xattr -dr com.apple.quarantine \"$APP\""
