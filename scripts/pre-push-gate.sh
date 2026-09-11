#!/usr/bin/env bash
# 本地质量门：在 push 之前跑完远端 CI 会跑的全部检查。
#
# 动机：2026-09-11 有两次「本地绿、CI 红」——workflow 引用了不存在的 action tag，
# 以及升级 action 后没有同步版本契约测试。这个脚本把 CI 的检查前置到本地。
#
# 用法：
#   scripts/pre-push-gate.sh            # 全量（含前端）
#   WB_GATE_FAST=1 scripts/pre-push-gate.sh   # 跳过前端（未装 node_modules 时自动跳过）
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

BIN="$REPO_ROOT/.venv/bin"
if [ ! -x "$BIN/python" ]; then
  echo "✗ 未找到 $BIN/python；请先运行 uv sync --extra dev" >&2
  exit 1
fi

step() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }

step "actionlint（workflow 语法）"
bash scripts/verify-workflows.sh

step "action ref 预检（ref 是否真实存在）"
bash scripts/check-action-refs.sh

step "ruff lint"
"$BIN/ruff" check .

step "ruff format"
"$BIN/ruff" format --check .

step "mypy（strict）"
"$BIN/mypy"

step "pytest + 覆盖率门"
"$BIN/python" -m pytest --cov=summit_workbench --cov-report=term-missing \
  --cov-fail-under=80 -q

if [ "${WB_GATE_FAST:-0}" != "1" ] && [ -d "$REPO_ROOT/web/node_modules" ]; then
  step "TypeScript（未使用声明）"
  (cd web && ./node_modules/.bin/tsc --noEmit)

  step "前端契约与纯渲染测试"
  npm --prefix web run test:frontend
else
  step "前端检查（已跳过）"
  echo "· WB_GATE_FAST=1 或未安装 web/node_modules"
fi

step "git diff --check（空白错误）"
git diff --check

printf '\n\033[32m✓ 本地门禁全部通过\033[0m\n'
