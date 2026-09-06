#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ACTIONLINT_BIN="${ACTIONLINT_BIN:-actionlint}"
command -v "$ACTIONLINT_BIN" >/dev/null || {
  echo "✗ 缺少 actionlint；请安装后再运行 workflow 质量门" >&2
  exit 1
}
"$ACTIONLINT_BIN" -color "$REPO_ROOT"/.github/workflows/*.yml
echo "✓ GitHub Actions workflow 校验通过"
