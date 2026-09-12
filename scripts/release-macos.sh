#!/usr/bin/env bash
# 构建仅供 M2+ Apple Silicon 内部使用的可审计 macOS DMG。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$REPO_ROOT/.venv/bin/python"
ARCH="${ARCH:-$(uname -m)}"
BUILD_NUMBER="${BUILD_NUMBER:-}"
FINAL_ROOT="${RELEASE_OUTPUT_DIR:-$REPO_ROOT/dist/releases}"
UPDATE_FEED_URL="${UPDATE_FEED_URL:-}"
UPDATE_DOWNLOAD_URL="${UPDATE_DOWNLOAD_URL:-}"
UPDATE_SIGNING_KEY_PATH="${UPDATE_SIGNING_KEY_PATH:-}"
OPENSSL_BIN="${OPENSSL_BIN:-openssl}"
REQUIRE_SIGNED_UPDATE="${REQUIRE_SIGNED_UPDATE:-false}"

case "$ARCH" in
  arm64) ;;
  *) echo "✗ 本产品仅支持 arm64 Apple Silicon（M2 及以上）：$ARCH" >&2; exit 1 ;;
esac
[[ "$BUILD_NUMBER" =~ ^[1-9][0-9]*$ ]] || {
  echo "✗ 请显式提供 BUILD_NUMBER（CI run 或发布参数）" >&2
  exit 1
}
[[ -x "$PYTHON" ]] || { echo "✗ 找不到项目 Python：$PYTHON" >&2; exit 1; }
command -v hdiutil >/dev/null || { echo "✗ 需要 hdiutil" >&2; exit 1; }
command -v shasum >/dev/null || { echo "✗ 需要 shasum" >&2; exit 1; }
if [[ -n "$UPDATE_SIGNING_KEY_PATH" ]]; then
  [[ -n "$UPDATE_FEED_URL" ]] || { echo "✗ 提供更新 feed 私钥时必须同时提供 UPDATE_FEED_URL" >&2; exit 1; }
  [[ -n "$UPDATE_DOWNLOAD_URL" ]] || { echo "✗ 提供更新 feed 私钥时必须同时提供 UPDATE_DOWNLOAD_URL" >&2; exit 1; }
  [[ -f "$UPDATE_SIGNING_KEY_PATH" ]] || { echo "✗ 找不到更新 feed 私钥：$UPDATE_SIGNING_KEY_PATH" >&2; exit 1; }
  UPDATE_PUBLIC_KEY="$($OPENSSL_BIN pkey -in "$UPDATE_SIGNING_KEY_PATH" -pubout -outform DER \
    | tail -c 32 | base64 | tr -d '\n')"
  OPENSSL_VERSION="$($OPENSSL_BIN version)"
  [[ "$OPENSSL_VERSION" == OpenSSL\ 3.* ]] || {
    echo "✗ 签名发布必须使用 OpenSSL 3，当前为：$OPENSSL_VERSION" >&2
    exit 1
  }
elif [[ "$REQUIRE_SIGNED_UPDATE" == true ]]; then
  echo "✗ tag 发布必须提供受保护的 UPDATE_SIGNING_KEY_PATH" >&2
  exit 1
fi

VERSION="$($PYTHON - "$REPO_ROOT/pyproject.toml" <<'PY'
import sys
import tomllib
from pathlib import Path

print(tomllib.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["project"]["version"])
PY
)"

# A release artifact must be backed by the same local gates that are reported
# in its manifest. CI may be unavailable (for example, account billing), but
# a release command must never silently replace those checks with a label.
RUFF="$REPO_ROOT/.venv/bin/ruff"
MYPY="$REPO_ROOT/.venv/bin/mypy"
PYTEST="$REPO_ROOT/.venv/bin/pytest"
[[ -x "$RUFF" && -x "$MYPY" && -x "$PYTEST" ]] || {
  echo "✗ 缺少本地质量门工具，请先安装项目 dev 依赖" >&2
  exit 1
}
"$RUFF" format --check src tests scripts
"$RUFF" check src tests scripts
"$MYPY" src
"$PYTEST" tests/unit -q
"$PYTHON" "$REPO_ROOT/scripts/update-web-route-contract.py"
"$PYTEST" tests/contract/test_web_route_contract.py -q
npm --prefix "$REPO_ROOT/web" run test:frontend

# 内部/个人自用不需要 Developer ID 或 notarization；使用 ad-hoc 签名并明确标识用途。
DISTRIBUTION="INTERNAL-DEV"
SIGN_IDENTITY="-"
SUFFIX="-INTERNAL-DEV"

RELEASE_TMP="$(mktemp -d "${TMPDIR:-/tmp}/summitworkbench-release.XXXXXX")"
cleanup() { rm -rf "$RELEASE_TMP"; }
trap cleanup EXIT
mkdir -p "$RELEASE_TMP/package"
# App bundle 使用稳定名称，拖入 Applications 时覆盖旧版本，避免相同 bundle id 的旧/新 App 并存，
# 从而让 SMAppService 能唯一解析 Contents/Library/LoginItems 下的 helper。
APP="$RELEASE_TMP/package/SummitWorkbench.app"

ARCH="$ARCH" BUILD_NUMBER="$BUILD_NUMBER" RELEASE_BUILD=true \
  UPDATE_FEED_URL="$UPDATE_FEED_URL" UPDATE_PUBLIC_KEY="${UPDATE_PUBLIC_KEY:-}" \
  OUTPUT_APP="$APP" SIGNING_IDENTITY="$SIGN_IDENTITY" \
  REQUIRE_BUNDLED_FEISHU="${REQUIRE_BUNDLED_FEISHU:-false}" \
  WB_FEISHU_APP_ID="${WB_FEISHU_APP_ID:-}" \
  WB_FEISHU_APP_SECRET="${WB_FEISHU_APP_SECRET:-}" \
  WB_FEISHU_REDIRECT_URI="${WB_FEISHU_REDIRECT_URI:-}" \
  "$REPO_ROOT/scripts/build-macos-app.sh"
# 内部 ad-hoc 包只执行本地 bundle/离线验证，不访问 Apple 在线发布服务。
REQUIRE_BUNDLED_FEISHU="${REQUIRE_BUNDLED_FEISHU:-false}" \
  SKIP_APPLE_ONLINE=true "$REPO_ROOT/scripts/verify-macos-release.sh" "$APP"
WB_PACKAGED_APP="$APP" "$PYTEST" "$REPO_ROOT/tests/integration/test_packaged_app.py" -m integration -q

DMG_STAGE="$RELEASE_TMP/dmg-stage"
mkdir -p "$DMG_STAGE"
cp -R "$APP" "$DMG_STAGE/"
ln -s /Applications "$DMG_STAGE/Applications"
DMG_NAME="SummitWorkbench-$VERSION-$ARCH${SUFFIX}.dmg"
DMG_TMP="$RELEASE_TMP/$DMG_NAME"
hdiutil create -volname "SummitWorkbench $VERSION ($ARCH)" -srcfolder "$DMG_STAGE" \
  -format UDZO -ov "$DMG_TMP" >/dev/null

UPDATE_FEED_NAME=""
if [[ -n "$UPDATE_SIGNING_KEY_PATH" ]]; then
  UPDATE_FEED_NAME="update-feed.json"
  "$PYTHON" "$REPO_ROOT/scripts/generate-update-feed.py" \
    --output "$RELEASE_TMP/package/$UPDATE_FEED_NAME" \
    --private-key "$UPDATE_SIGNING_KEY_PATH" --version "$VERSION" --build "$BUILD_NUMBER" \
    --architecture "$ARCH" --minimum-macos "13.0" --download-url "$UPDATE_DOWNLOAD_URL" \
    --dmg "$DMG_TMP" --release-notes "SummitWorkbench $VERSION 内部更新" \
    --workspace-schema-version "2" --workspace-min-reader-version "$VERSION" \
    --workspace-min-writer-version "$VERSION" --require-openssl3
else
  echo "ℹ 未配置独立更新 feed 私钥：本次内部包不发布可验证更新 feed" >&2
fi

printf '{"status":"not-applicable","reason":"internal arm64 M2+ distribution; no Apple Developer ID/notarization required"}\n' \
  > "$RELEASE_TMP/notary-log.json"
"$REPO_ROOT/scripts/verify-macos-release.sh" "$APP" "$DMG_TMP"

META="$RELEASE_TMP/package/release-metadata.json"
SBOM="$RELEASE_TMP/package/SBOM.json"
"$PYTHON" - "$META" "$SBOM" "$VERSION" "$BUILD_NUMBER" "$ARCH" "$DISTRIBUTION" \
  "$REPO_ROOT" "$APP" "$DMG_TMP" "$RELEASE_TMP/notary-log.json" "$UPDATE_FEED_NAME" <<'PY'
import hashlib
import importlib.metadata
import json
import subprocess
import sys
import tomllib
from pathlib import Path

meta_path, sbom_path, version, build, arch, distribution, repo, app, dmg, notary, update_feed = sys.argv[1:]
repo_path = Path(repo)
project = tomllib.loads((repo_path / "pyproject.toml").read_text(encoding="utf-8"))
commit = subprocess.check_output(["git", "-C", str(repo_path), "rev-parse", "HEAD"], text=True).strip()
components = []
for dist in sorted(importlib.metadata.distributions(), key=lambda item: (item.metadata["Name"] or "").lower()):
    name = dist.metadata["Name"]
    if name:
        components.append({"type": "library", "name": name, "version": dist.version})
Path(sbom_path).write_text(json.dumps({
    "bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1,
    "components": components,
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
metadata = {
    "product_id": "com.summitworkbench.panel", "version": version, "build": build,
    "architecture": arch, "minimum_macos": "13.0", "git_commit": commit,
    "distribution": distribution, "workspace_schema": {"min_reader": 1, "max_writer": 1},
    "app": Path(app).name, "dmg": Path(dmg).name, "sbom": Path(sbom_path).name,
    "notary_log": Path(notary).name,
    "pyproject_dependencies": project["project"].get("dependencies", []),
    "update_feed": update_feed,
    "sha256": {
        "app": "",
        "dmg": hashlib.sha256(Path(dmg).read_bytes()).hexdigest(),
    },
}
app_digest = hashlib.sha256()
for child in sorted(Path(app).rglob("*")):
    if child.is_file():
        app_digest.update(str(child.relative_to(app)).encode("utf-8"))
        app_digest.update(child.read_bytes())
metadata["sha256"]["app"] = app_digest.hexdigest()
Path(meta_path).write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
cp "$RELEASE_TMP/notary-log.json" "$RELEASE_TMP/package/notary-log.json"

# 把本次发布实际经过的离线/打包门写入产物，便于内部接收者复核而不依赖 CI 日志。
TEST_MANIFEST="$RELEASE_TMP/package/test-manifest.json"
"$PYTHON" - "$TEST_MANIFEST" "$VERSION" "$BUILD_NUMBER" "$ARCH" <<'PY'
import json
import sys
from pathlib import Path

path, version, build, arch = sys.argv[1:]
Path(path).write_text(json.dumps({
    "schema_version": 1,
    "product_version": version,
    "build": build,
    "architecture": arch,
    "status": "passed",
    "checks": [
        "Ruff format check",
        "Ruff lint",
        "mypy src",
        "pytest tests/unit",
        "web route contract",
        "frontend feature/render/browser contracts",
        "frontend build and verify-build",
        "Python packaged server build",
        "Swift arm64 app and automation helper compile",
        "bundle strict codesign verification",
        "offline dynamic-port server smoke",
        "packaged server integration smoke",
        "DMG checksum generation",
    ],
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
mv "$DMG_TMP" "$RELEASE_TMP/package/$DMG_NAME"
CHECKSUM_FILES=("$DMG_NAME" "release-metadata.json" "SBOM.json" "notary-log.json" "test-manifest.json")
if [[ -n "$UPDATE_FEED_NAME" ]]; then CHECKSUM_FILES+=("$UPDATE_FEED_NAME"); fi
(cd "$RELEASE_TMP/package" && shasum -a 256 "${CHECKSUM_FILES[@]}" > SHA256SUMS)

FINAL_DIR="$FINAL_ROOT/$VERSION/$ARCH"
if [[ -e "$FINAL_DIR" ]]; then
  echo "✗ 发布目录已存在，为避免覆盖请更换 RELEASE_OUTPUT_DIR：$FINAL_DIR" >&2
  exit 1
fi
mkdir -p "$(dirname "$FINAL_DIR")"
mv "$RELEASE_TMP/package" "$FINAL_DIR"
echo "✓ 已生成 $DISTRIBUTION 包：$FINAL_DIR/$DMG_NAME"
echo "  仅供 M2+ Apple Silicon 内部/个人自用，不支持 Intel/Windows。"
