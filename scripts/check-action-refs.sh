#!/usr/bin/env bash
# 预检 workflow 中每个 `uses:` 引用的 action ref 是否真实存在。
#
# 动机：setup-uv 自 v8 起不再发布滚动 major tag，把 `astral-sh/setup-uv@v10`
# 推上去只会在 CI 的 "Set up job" 阶段失败，本地完全看不出来。这个预检把
# 这类错误提前到 push 之前。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKFLOW_DIR="$REPO_ROOT/.github/workflows"

if ! command -v gh >/dev/null 2>&1; then
  echo "⚠ 未安装 gh，跳过 action ref 预检" >&2
  exit 0
fi

specs="$(grep -rhoE 'uses: [^ ]+' "$WORKFLOW_DIR" | sed 's/uses: //' | sort -u)"
if [ -z "$specs" ]; then
  echo "⚠ 未发现任何 uses: 引用" >&2
  exit 0
fi

status=0
while IFS= read -r spec; do
  [ -n "$spec" ] || continue
  repo="${spec%@*}"
  ref="${spec#*@}"
  if gh api "repos/$repo/contents/action.yml?ref=$ref" --jq '.name' >/dev/null 2>&1 ||
    gh api "repos/$repo/contents/action.yaml?ref=$ref" --jq '.name' >/dev/null 2>&1; then
    echo "✓ $spec"
  else
    echo "✗ $spec —— ref 不存在，CI 会在 Set up job 阶段失败" >&2
    status=1
  fi
done <<< "$specs"

exit "$status"
