#!/usr/bin/env bash
# 构建仅供 M2+ Apple Silicon 内部使用的可审计 macOS DMG。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$REPO_ROOT/.venv/bin/python"
ARCH="${ARCH:-$(uname -m)}"
BUILD_NUMBER="${BUILD_NUMBER:-}"
FINAL_ROOT="${RELEASE_OUTPUT_DIR:-$REPO_ROOT/dist/releases}"

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

VERSION="$($PYTHON - "$REPO_ROOT/pyproject.toml" <<'PY'
import sys
import tomllib
from pathlib import Path

print(tomllib.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["project"]["version"])
PY
)"

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
  OUTPUT_APP="$APP" SIGNING_IDENTITY="$SIGN_IDENTITY" \
  "$REPO_ROOT/scripts/build-macos-app.sh"
# 内部 ad-hoc 包只执行本地 bundle/离线验证，不访问 Apple 在线发布服务。
SKIP_APPLE_ONLINE=true "$REPO_ROOT/scripts/verify-macos-release.sh" "$APP"

DMG_STAGE="$RELEASE_TMP/dmg-stage"
mkdir -p "$DMG_STAGE"
cp -R "$APP" "$DMG_STAGE/"
ln -s /Applications "$DMG_STAGE/Applications"
DMG_NAME="SummitWorkbench-$VERSION-$ARCH${SUFFIX}.dmg"
DMG_TMP="$RELEASE_TMP/$DMG_NAME"
hdiutil create -volname "SummitWorkbench $VERSION ($ARCH)" -srcfolder "$DMG_STAGE" \
  -format UDZO -ov "$DMG_TMP" >/dev/null

printf '{"status":"not-applicable","reason":"internal arm64 M2+ distribution; no Apple Developer ID/notarization required"}\n' \
  > "$RELEASE_TMP/notary-log.json"
"$REPO_ROOT/scripts/verify-macos-release.sh" "$APP" "$DMG_TMP"

META="$RELEASE_TMP/package/release-metadata.json"
SBOM="$RELEASE_TMP/package/SBOM.json"
"$PYTHON" - "$META" "$SBOM" "$VERSION" "$BUILD_NUMBER" "$ARCH" "$DISTRIBUTION" \
  "$REPO_ROOT" "$APP" "$DMG_TMP" "$RELEASE_TMP/notary-log.json" <<'PY'
import hashlib
import importlib.metadata
import json
import subprocess
import sys
import tomllib
from pathlib import Path

meta_path, sbom_path, version, build, arch, distribution, repo, app, dmg, notary = sys.argv[1:]
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
mv "$DMG_TMP" "$RELEASE_TMP/package/$DMG_NAME"
(cd "$RELEASE_TMP/package" && shasum -a 256 "$DMG_NAME" "release-metadata.json" "SBOM.json" > SHA256SUMS)

FINAL_DIR="$FINAL_ROOT/$VERSION/$ARCH"
if [[ -e "$FINAL_DIR" ]]; then
  echo "✗ 发布目录已存在，为避免覆盖请更换 RELEASE_OUTPUT_DIR：$FINAL_DIR" >&2
  exit 1
fi
mkdir -p "$(dirname "$FINAL_DIR")"
mv "$RELEASE_TMP/package" "$FINAL_DIR"
echo "✓ 已生成 $DISTRIBUTION 包：$FINAL_DIR/$DMG_NAME"
echo "  仅供 M2+ Apple Silicon 内部/个人自用，不支持 Intel/Windows。"
