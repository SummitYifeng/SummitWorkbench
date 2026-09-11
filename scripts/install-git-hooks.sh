#!/usr/bin/env bash
# 把本地质量门安装为 git pre-push hook。
#
# .git/hooks/ 不进入版本控制，所以每个克隆都需要显式执行一次：
#   scripts/install-git-hooks.sh
#
# 临时绕过（确实需要时）：git push --no-verify
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK_DIR="$REPO_ROOT/.git/hooks"
HOOK="$HOOK_DIR/pre-push"

if [ ! -d "$HOOK_DIR" ]; then
  echo "✗ 未找到 $HOOK_DIR（不是 git 仓库？）" >&2
  exit 1
fi

cat > "$HOOK" <<'HOOK_BODY'
#!/usr/bin/env bash
# 由 scripts/install-git-hooks.sh 生成：push 前跑本地质量门。
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
exec "$REPO_ROOT/scripts/pre-push-gate.sh"
HOOK_BODY

chmod +x "$HOOK"
echo "✓ 已安装 pre-push 门禁：$HOOK"
echo "  绕过（不推荐）：git push --no-verify"
