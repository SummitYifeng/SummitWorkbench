#!/usr/bin/env bash
# 构建自包含的 macOS SummitWorkbench.app。
#
# 生产路径：bundle 内 server + bundle 内静态资源 + WKWebView 原生壳。
# 构建先完成临时 bundle、签名与 smoke test，最后才替换 dist 产物。
# 用法：ARCH=arm64 BUILD_NUMBER=123 scripts/build-macos-app.sh [smoke port；默认动态端口]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${1:-0}"
PYTHON="$REPO_ROOT/.venv/bin/python"
STATIC_DIR="$REPO_ROOT/src/summit_workbench/webapp/static"
ARCH="${ARCH:-$(uname -m)}"
OUTPUT_APP="${OUTPUT_APP:-$REPO_ROOT/dist/SummitWorkbench.app}"
FINAL_APP="$OUTPUT_APP"
SIGNING_IDENTITY="${SIGNING_IDENTITY:--}"
BUILD_NUMBER="${BUILD_NUMBER:-0}"
RELEASE_BUILD="${RELEASE_BUILD:-false}"
UPDATE_FEED_URL="${UPDATE_FEED_URL:-}"
UPDATE_PUBLIC_KEY="${UPDATE_PUBLIC_KEY:-}"
REQUIRE_BUNDLED_FEISHU="${REQUIRE_BUNDLED_FEISHU:-true}"
ALLOW_INCOMPLETE_FEISHU_DEV="${ALLOW_INCOMPLETE_FEISHU_DEV:-false}"

case "$ARCH" in
  arm64) ;;
  *) echo "✗ 本产品仅支持 arm64 Apple Silicon（M2 及以上）：$ARCH" >&2; exit 1 ;;
esac
[[ "$ARCH" == "$(uname -m)" ]] || {
  echo "✗ 构建架构必须与 macOS runner 架构一致：runner=$(uname -m) requested=$ARCH" >&2
  exit 1
}
if [[ "$RELEASE_BUILD" == true && "$BUILD_NUMBER" == 0 ]]; then
  echo "✗ 正式/候选构建必须显式提供 BUILD_NUMBER（CI run 或发布参数）" >&2
  exit 1
fi
if [[ "$RELEASE_BUILD" == true ]]; then
  REQUIRE_BUNDLED_FEISHU=true
elif [[ "$ALLOW_INCOMPLETE_FEISHU_DEV" == true ]]; then
  REQUIRE_BUNDLED_FEISHU=false
fi
if [[ "$REQUIRE_BUNDLED_FEISHU" != true && "$ALLOW_INCOMPLETE_FEISHU_DEV" != true && "$RELEASE_BUILD" != true ]]; then
  echo "✗ 开发构建缺少飞书默认凭据；如确需不完整开发包，请显式设置 ALLOW_INCOMPLETE_FEISHU_DEV=true" >&2
  exit 1
fi

[[ -x "$PYTHON" ]] || { echo "✗ 找不到 Python：$PYTHON" >&2; exit 1; }
command -v npm >/dev/null || { echo "✗ 需要 npm" >&2; exit 1; }
command -v xcrun >/dev/null || { echo "✗ 需要 Xcode 命令行工具" >&2; exit 1; }
command -v codesign >/dev/null || { echo "✗ 需要 codesign" >&2; exit 1; }
"$PYTHON" -m PyInstaller --version >/dev/null || {
  echo "✗ 缺少 PyInstaller，请先 uv sync --extra web --extra packaging" >&2
  exit 1
}
PROJECT_VERSION="$($PYTHON - "$REPO_ROOT/pyproject.toml" <<'PY'
import sys
import tomllib
from pathlib import Path

print(tomllib.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["project"]["version"])
PY
)"

# 先生成并验证唯一的前端构建身份，再打包 server；两者共享同一个 build-meta。
npm --prefix "$REPO_ROOT/web" run build
node "$REPO_ROOT/web/scripts/verify-build.mjs" "$STATIC_DIR"
"$PYTHON" -m pytest -q \
  "$REPO_ROOT/tests/unit/test_webapi.py" \
  "$REPO_ROOT/tests/unit/test_native_panel_contract.py"

FRONTEND_BUILD="$($PYTHON -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["frontend_build"])' "$STATIC_DIR/build-meta.json")"
BUILD_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/summitworkbench-build.XXXXXX")"
SMOKE_PID=""
cleanup() {
  if [[ "$SMOKE_PID" =~ ^[0-9]+$ ]] && kill -0 "$SMOKE_PID" 2>/dev/null; then
    kill "$SMOKE_PID" 2>/dev/null || true
    wait "$SMOKE_PID" 2>/dev/null || true
  fi
  rm -rf "$BUILD_ROOT"
}
trap cleanup EXIT
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
# editable 安装元数据只服务于开发环境，不能把本机仓库路径带进可分发 bundle。
find "$APP/Contents/Resources/server" -name direct_url.json -type f -delete

cp -R "$STATIC_DIR/." "$APP/Contents/Resources/web/static/"
cp -R "$REPO_ROOT/prompts/." "$APP/Contents/Resources/prompts/"
cp -R "$REPO_ROOT/templates/." "$APP/Contents/Resources/templates/"

# 内置飞书默认凭据：让同事装完点一下「授权飞书」即可，无需任何本机预置。
# 飞书 v2 令牌端点强制要求 client_secret（PKCE 不能替代），分发包又没有可代持秘密的
# 后端，因此这里把 app_id / app_secret 写进包内资源；必须写在**签名之前**（见下方 sign）。
# 密钥只从环境变量取，绝不进仓库（repo 内不存在该文件，见 .gitignore 的 build/ 与 dist/）。
FEISHU_DEFAULTS="$APP/Contents/Resources/feishu-defaults.json"
FEISHU_BUNDLED=false
if [[ -n "${WB_FEISHU_APP_ID:-}" || -n "${WB_FEISHU_APP_SECRET:-}" ]]; then
  [[ -n "${WB_FEISHU_APP_ID:-}" && -n "${WB_FEISHU_APP_SECRET:-}" ]] || {
    echo "✗ WB_FEISHU_APP_ID 与 WB_FEISHU_APP_SECRET 必须同时提供（只给其一无法授权）" >&2
    exit 1
  }
  (
    umask 077
    WB_FEISHU_REDIRECT_URI="${WB_FEISHU_REDIRECT_URI:-http://localhost:8765/callback}" \
      "$PYTHON" -c '
import json, os, sys
sys.stdout.write(json.dumps({
    "app_id": os.environ["WB_FEISHU_APP_ID"],
    "app_secret": os.environ["WB_FEISHU_APP_SECRET"],
    "redirect_uri": os.environ["WB_FEISHU_REDIRECT_URI"],
}, ensure_ascii=False, indent=2) + "\n")
' > "$FEISHU_DEFAULTS"
  )
  chmod 600 "$FEISHU_DEFAULTS"
  FEISHU_BUNDLED=true
  echo "✓ 已内置飞书默认凭据：app_id=${WB_FEISHU_APP_ID} redirect_uri=${WB_FEISHU_REDIRECT_URI:-http://localhost:8765/callback}"
elif [[ "$REQUIRE_BUNDLED_FEISHU" == "true" ]]; then
  echo "✗ REQUIRE_BUNDLED_FEISHU=true 但缺少 WB_FEISHU_APP_ID / WB_FEISHU_APP_SECRET：" >&2
  echo "  发布包必须内置飞书默认凭据，否则同事无法完成授权。" >&2
  exit 1
else
  echo "⚠ 未提供 WB_FEISHU_APP_ID / WB_FEISHU_APP_SECRET：本次构建不含内置飞书凭据（仅开发用）"
fi

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
SWIFT_SOURCES=()
for source in "$REPO_ROOT"/native/SummitWorkbench/*.swift; do
  [[ "$source" == *"/AutomationHelperMain.swift" ]] || SWIFT_SOURCES+=("$source")
done
xcrun swiftc -O -target "$ARCH-apple-macosx13.0" \
  -framework AppKit -framework WebKit -framework Security -framework ServiceManagement -framework CryptoKit \
  "${SWIFT_SOURCES[@]}" \
  -o "$APP/Contents/MacOS/SummitWorkbench"
chmod +x "$APP/Contents/MacOS/SummitWorkbench"

SHORT_VERSION="$PROJECT_VERSION"
BUNDLE_VERSION="$BUILD_NUMBER"
if [[ "$SIGNING_IDENTITY" == "-" ]]; then
  DISPLAY_NAME="SummitWorkbench (INTERNAL-DEV)"
  RELEASE_LABEL="INTERNAL-DEV"
else
  DISPLAY_NAME="SummitWorkbench"
  RELEASE_LABEL="SIGNED"
fi
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>$DISPLAY_NAME</string>
  <key>CFBundleDisplayName</key><string>$DISPLAY_NAME</string>
  <key>CFBundleIdentifier</key><string>com.summitworkbench.panel</string>
  <key>CFBundleShortVersionString</key><string>$SHORT_VERSION</string>
  <key>CFBundleVersion</key><string>$BUNDLE_VERSION</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>SummitWorkbench</string>
$ICON_KEY
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>LSUIElement</key><false/>
  <key>LSMultipleInstancesProhibited</key><true/>
</dict></plist>
PLIST
cat > "$APP/Contents/Resources/build-manifest.json" <<MANIFEST
{
  "schema_version": 2,
  "product_id": "com.summitworkbench.panel",
  "version": "$PROJECT_VERSION",
  "build": "$BUILD_NUMBER",
  "architecture": "$ARCH",
  "distribution": "$RELEASE_LABEL",
  "feishu_credentials": {
    "bundled": $FEISHU_BUNDLED,
    "keychain_fallback": true,
    "complete": $FEISHU_BUNDLED
  },
  "frontend_build": "$FRONTEND_BUILD",
  "api_protocol": 2,
  "update_feed_url": "$UPDATE_FEED_URL",
  "update_public_key": "$UPDATE_PUBLIC_KEY"
}
MANIFEST
/usr/bin/plutil -lint "$APP/Contents/Info.plist" >/dev/null
# 先签名 dylib/framework，再签名 PyInstaller executable，最后签名 App；内部包统一使用 ad-hoc。
ENTITLEMENTS="$REPO_ROOT/packaging/entitlements.plist"
[[ -f "$ENTITLEMENTS" ]] || { echo "✗ 缺少最小 entitlement：$ENTITLEMENTS" >&2; exit 1; }
SIGN_FLAGS=(--force --sign "$SIGNING_IDENTITY")
if [[ "$SIGNING_IDENTITY" == "-" ]]; then
  SIGN_FLAGS+=(--timestamp=none)
else
  SIGN_FLAGS+=(--options runtime --timestamp)
fi
sign_nested() { codesign "${SIGN_FLAGS[@]}" "$1"; }
while IFS= read -r nested; do sign_nested "$nested"; done < <(
  find "$APP/Contents/Resources" \( -name '*.dylib' -o -name '*.framework' \) -print | sort -r
)
sign_nested "$APP/Contents/Resources/server/SummitWorkbenchServer"
if [[ "$SIGNING_IDENTITY" == "-" ]]; then
  codesign --force --sign - --timestamp=none "$APP"
else
  codesign --force --sign "$SIGNING_IDENTITY" --options runtime --timestamp \
    --entitlements "$ENTITLEMENTS" "$APP"
fi
codesign --verify --strict "$APP"
codesign --verify --deep --strict "$APP"

# 不依赖仓库 .venv 的 bundle server smoke：直接运行嵌套 server 与 bundle static。
SMOKE_PORT="$PORT"
if [[ "$SMOKE_PORT" == 0 ]]; then
  SMOKE_PORT="$($PYTHON -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
fi
WB_SESSION_TOKEN="$($PYTHON -c 'import secrets; print(secrets.token_urlsafe(32))')"
SMOKE_ROOT="$BUILD_ROOT/smoke-work"
SMOKE_HOME="$BUILD_ROOT/smoke-home"
SMOKE_RECORD="$SMOKE_HOME/runtime.json"
mkdir -p "$SMOKE_ROOT" "$SMOKE_HOME"
SMOKE_SERVER="$APP/Contents/Resources/server/SummitWorkbenchServer"
HOME="$SMOKE_HOME" WORK_ROOT="$SMOKE_ROOT" WB_PANEL_MODE=production \
  WB_SESSION_TOKEN="$WB_SESSION_TOKEN" \
  WB_STATIC_DIR="$APP/Contents/Resources/web/static" \
  WB_PROMPTS_DIR="$APP/Contents/Resources/prompts" \
  "$SMOKE_SERVER" --host 127.0.0.1 --port "$SMOKE_PORT" --work-root "$SMOKE_ROOT" \
  --runtime-record "$SMOKE_RECORD" --static-dir "$APP/Contents/Resources/web/static" \
  >"$BUILD_ROOT/smoke.log" 2>&1 &
SMOKE_PID=$!
for attempt in {1..40}; do
  if curl -fsS --max-time 1 -H "X-WB-Session-Token: $WB_SESSION_TOKEN" "http://127.0.0.1:$SMOKE_PORT/api/version" >"$BUILD_ROOT/version.json" 2>/dev/null; then break; fi
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
SMOKE_PID=""

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
