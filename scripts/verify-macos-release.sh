#!/usr/bin/env bash
# 验证 App/DMG 的签名、清单、隐私卫生和离线服务启动；内部包跳过 Apple 在线门。
set -euo pipefail

APP="${1:-}"
DMG="${2:-}"
[[ -d "$APP" ]] || { echo "✗ 用法：verify-macos-release.sh APP [DMG]" >&2; exit 1; }
SERVER="$APP/Contents/Resources/server/SummitWorkbenchServer"
STATIC="$APP/Contents/Resources/web/static"
MANIFEST="$APP/Contents/Resources/build-manifest.json"
[[ -x "$SERVER" && -f "$STATIC/build-meta.json" && -f "$MANIFEST" ]] || {
  echo "✗ App 缺少自包含 server、static 或 manifest" >&2
  exit 1
}

codesign --verify --strict "$APP"
codesign --verify --deep --strict "$APP"
SIGNATURE="$(codesign -dv --verbose=4 "$APP" 2>&1 || true)"
if grep -qE 'INTERNAL-DEV|UNSIGNED-DEV' "$MANIFEST" || grep -q 'Signature=adhoc' <<<"$SIGNATURE"; then
  echo "✓ 内部 ad-hoc 包：跳过 spctl/stapler 在线签名门"
elif [[ "${SKIP_APPLE_ONLINE:-false}" == true ]]; then
  echo "↻ notarization 前跳过 spctl/stapler，待 staple 后复验"
else
  spctl --assess --type execute --verbose=2 "$APP"
  xcrun stapler validate "$APP"
fi

FILE_LIST="$(mktemp "${TMPDIR:-/tmp}/summitworkbench-files.XXXXXX")"
SMOKE_HOME="$(mktemp -d "${TMPDIR:-/tmp}/summitworkbench-smoke-home.XXXXXX")"
SMOKE_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/summitworkbench-smoke-root.XXXXXX")"
SMOKE_RECORD="$SMOKE_HOME/runtime.json"
SMOKE_LOG="$SMOKE_HOME/server.log"
SMOKE_PID=""
cleanup() {
  if [[ "$SMOKE_PID" =~ ^[0-9]+$ ]] && kill -0 "$SMOKE_PID" 2>/dev/null; then
    kill "$SMOKE_PID" 2>/dev/null || true
    wait "$SMOKE_PID" 2>/dev/null || true
  fi
  rm -f "$FILE_LIST"
  rm -rf "$SMOKE_HOME" "$SMOKE_ROOT"
}
trap cleanup EXIT
find "$APP" -type f -print | sort > "$FILE_LIST"
[[ -s "$FILE_LIST" ]] || { echo "✗ bundle 文件清单为空" >&2; exit 1; }

# 只扫描可读文本元数据，避免把编译后的第三方二进制误判成源码路径；这是发布 secret scan。
if find "$APP/Contents" -type f \( -name '*.json' -o -name '*.plist' -o -name '*.md' -o -name '*.txt' \) \
  -exec grep -HnE '/Users/[^/]+/|/home/[^/]+/|BEGIN (RSA|EC|OPENSSH) PRIVATE KEY|api[_-]?key[=:]|refresh[_-]?token[=:]|password[=:]' {} +; then
  echo "✗ bundle 元数据命中开发路径或秘密特征" >&2
  exit 1
fi

TOKEN="offline-release-smoke-token"
HOME="$SMOKE_HOME" WB_PANEL_MODE=production WB_SESSION_TOKEN="$TOKEN" \
  "$SERVER" --host 127.0.0.1 --port 0 --work-root "$SMOKE_ROOT" \
  --runtime-record "$SMOKE_RECORD" --static-dir "$STATIC" >"$SMOKE_LOG" 2>&1 &
SMOKE_PID=$!
READY=false
for _ in {1..80}; do
  if [[ -f "$SMOKE_RECORD" ]]; then
    PORT="$(python3 - "$SMOKE_RECORD" <<'PY'
import json
import sys
print(json.loads(open(sys.argv[1], encoding="utf-8").read())["port"])
PY
    )"
    if curl -fsS --max-time 1 -H "X-WB-Session-Token: $TOKEN" \
      "http://127.0.0.1:$PORT/api/version" >/dev/null 2>&1; then
      READY=true
      break
    fi
  fi
  sleep 0.25
done
[[ "$READY" == true ]] || { echo "✗ 离线 server smoke 失败" >&2; cat "$SMOKE_LOG" >&2; exit 1; }
kill "$SMOKE_PID" 2>/dev/null || true
wait "$SMOKE_PID" 2>/dev/null || true
SMOKE_PID=""

if [[ -n "$DMG" ]]; then
  [[ -f "$DMG" ]] || { echo "✗ 找不到 DMG：$DMG" >&2; exit 1; }
  shasum -a 256 "$DMG" >/dev/null
fi
echo "✓ release 验证通过：$(basename "$APP")"
