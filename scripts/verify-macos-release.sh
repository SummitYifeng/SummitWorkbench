#!/usr/bin/env bash
# 验证 App/DMG 的签名、清单、隐私卫生和离线服务启动；内部包跳过 Apple 在线门。
set -euo pipefail

APP="${1:-}"
DMG="${2:-}"
REQUIRE_BUNDLED_FEISHU="${REQUIRE_BUNDLED_FEISHU:-true}"
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
# 显式例外：Contents/Resources/feishu-defaults.json 是**有意**内置的飞书应用级凭据——
# 飞书令牌端点强制要求 client_secret，分发包没有可代持秘密的后端，而同事必须零预置就能
# 授权（见 docs/RELEASING.md「内置飞书凭据」）。该文件从通用扫描中排除，改由下方结构化
# 校验负责；校验只检查结构，绝不打印凭据值。
if find "$APP/Contents" -type f \( -name '*.json' -o -name '*.plist' -o -name '*.md' -o -name '*.txt' \) \
  -not -name 'feishu-defaults.json' \
  -exec grep -HnE '/Users/[^/]+/|/home/[^/]+/|BEGIN (RSA|EC|OPENSSH) PRIVATE KEY|api[_-]?key[=:]|refresh[_-]?token[=:]|password[=:]' {} +; then
  echo "✗ bundle 元数据命中开发路径或秘密特征" >&2
  exit 1
fi

# 内置飞书凭据：发布构建必须带上，否则同事拿到 DMG 也无法完成授权。
FEISHU_DEFAULTS="$APP/Contents/Resources/feishu-defaults.json"
if [[ "$REQUIRE_BUNDLED_FEISHU" == "true" && ! -f "$FEISHU_DEFAULTS" ]]; then
  echo "✗ REQUIRE_BUNDLED_FEISHU=true 但包内缺少 feishu-defaults.json" >&2
  exit 1
fi
if [[ -f "$FEISHU_DEFAULTS" ]]; then
  if ! python3 - "$FEISHU_DEFAULTS" <<'PY'
import json
import sys

payload = json.loads(open(sys.argv[1], encoding="utf-8").read())
missing = [
    key
    for key in ("app_id", "app_secret", "redirect_uri")
    if not isinstance(payload.get(key), str) or not payload[key].strip()
]
if missing:
    sys.exit(f"missing or empty keys: {', '.join(missing)}")
PY
  then
    echo "✗ 内置飞书凭据结构不正确（需非空 app_id / app_secret / redirect_uri）" >&2
    exit 1
  fi
  echo "✓ 内置飞书凭据结构正确（值不打印）"
fi

python3 - "$MANIFEST" "$REQUIRE_BUNDLED_FEISHU" <<'PY'
import json
import sys

manifest = json.loads(open(sys.argv[1], encoding="utf-8").read())
required = sys.argv[2] == "true"
credentials = manifest.get("feishu_credentials")
if not isinstance(credentials, dict):
    sys.exit("missing feishu_credentials manifest metadata")
if required and credentials.get("complete") is not True:
    sys.exit("manifest does not confirm complete bundled Feishu credentials")
PY

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
