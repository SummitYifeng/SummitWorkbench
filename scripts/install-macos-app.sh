#!/usr/bin/env bash
# 校验并原子安装一个已构建的 SummitWorkbench.app。
# 默认不触碰正在运行的实例；--replace-running 只终止 runtime record 严格匹配的进程。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE_APP="${1:-$REPO_ROOT/dist/SummitWorkbench.app}"
DEST_APP="${WB_INSTALL_DEST:-/Applications/SummitWorkbench.app}"
REPLACE_RUNNING=false
if [[ "${2:-}" == "--replace-running" ]]; then REPLACE_RUNNING=true; fi

[[ -d "$SOURCE_APP" ]] || { echo "✗ 找不到 App：$SOURCE_APP" >&2; exit 1; }
command -v codesign >/dev/null || { echo "✗ 需要 codesign" >&2; exit 1; }
codesign --verify --deep --strict "$SOURCE_APP"
MANIFEST="$SOURCE_APP/Contents/Resources/build-manifest.json"
SERVER="$SOURCE_APP/Contents/Resources/server/SummitWorkbenchServer"
STATIC="$SOURCE_APP/Contents/Resources/web/static"
[[ -f "$MANIFEST" && -x "$SERVER" && -f "$STATIC/build-meta.json" ]] || {
  echo "✗ App 缺少 manifest、bundle server 或静态资源" >&2
  exit 1
}

if [[ "$REPLACE_RUNNING" != true && -f "$HOME/Library/Application Support/SummitWorkbench/runtime.json" ]]; then
  echo "✗ 检测到 SummitWorkbench runtime record；请先退出 App，或明确传入 --replace-running" >&2
  exit 1
fi

if [[ "$REPLACE_RUNNING" == true && -f "$HOME/Library/Application Support/SummitWorkbench/runtime.json" ]]; then
  read -r LAUNCHER_PID SERVICE_PID < <("$REPO_ROOT/.venv/bin/python" - "$HOME/Library/Application Support/SummitWorkbench/runtime.json" <<'PY'
import json
import sys
from pathlib import Path

record = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(record.get("launcher_pid", ""), record.get("service_pid", ""))
PY
  )
  for pid in "$LAUNCHER_PID" "$SERVICE_PID"; do
    if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
      command_line="$(ps -p "$pid" -o command= 2>/dev/null || true)"
      if [[ "$command_line" == *"SummitWorkbench"* ]]; then kill -TERM "$pid"; fi
    fi
  done
  for _ in {1..40}; do
    if ! kill -0 "${LAUNCHER_PID:-0}" 2>/dev/null && ! kill -0 "${SERVICE_PID:-0}" 2>/dev/null; then break; fi
    sleep 0.25
  done
fi

INSTALL_ROOT="$(mktemp -d "/tmp/summitworkbench-install.XXXXXX")"
trap 'rm -rf "$INSTALL_ROOT"' EXIT
STAGED_APP="$INSTALL_ROOT/SummitWorkbench.app"
cp -R "$SOURCE_APP" "$STAGED_APP"
codesign --verify --deep --strict "$STAGED_APP"

mkdir -p "$(dirname "$DEST_APP")"
BACKUP_APP="$DEST_APP.previous"
if [[ -e "$BACKUP_APP" ]]; then
  echo "✗ 已存在旧备份：$BACKUP_APP，请先处理后重试" >&2
  exit 1
fi
if [[ -d "$DEST_APP" ]]; then mv "$DEST_APP" "$BACKUP_APP"; fi
if ! mv "$STAGED_APP" "$DEST_APP"; then
  if [[ -d "$BACKUP_APP" ]]; then mv "$BACKUP_APP" "$DEST_APP"; fi
  echo "✗ 原子安装失败，已恢复旧 App" >&2
  exit 1
fi

open "$DEST_APP"
PORT="$($REPO_ROOT/.venv/bin/python - "$DEST_APP/Contents/Resources/build-manifest.json" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["port"])
PY
)"
for _ in {1..40}; do
  if curl -fsS --max-time 1 "http://127.0.0.1:$PORT/api/version" >/dev/null 2>&1; then
    echo "✓ 已安装并启动 $DEST_APP"
    exit 0
  fi
  sleep 0.25
done
echo "✗ App 已安装但服务未在 readiness 窗口内启动；旧 App 保留在 $BACKUP_APP" >&2
exit 1
