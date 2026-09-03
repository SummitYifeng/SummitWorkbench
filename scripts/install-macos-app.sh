#!/usr/bin/env bash
# 校验并原子安装一个已构建的 SummitWorkbench.app。
# 默认不触碰正在运行的实例；--replace-running 只终止 runtime record 严格匹配的进程。
# 备份自动处理：安装前清理遗留 .previous，安装成功后不再保留备份（失败回滚仍用
# 本轮 mv 出的备份），下次安装无需任何手动步骤。
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

# Phase 2 旧启动器没有 runtime record；按完整可执行路径识别它，避免新旧 App 同时争用端口。
LEGACY_LAUNCHER_PID="$(ps -ww -axo pid=,command= | awk -v target="$DEST_APP/Contents/MacOS/SummitWorkbench" \
  '$0 ~ target { sub(/^[[:space:]]+/, ""); split($0, fields, /[[:space:]]+/); print fields[1]; exit }' || true)"
if [[ -n "$LEGACY_LAUNCHER_PID" && "$REPLACE_RUNNING" != true ]]; then
  echo "✗ 检测到运行中的 SummitWorkbench：请先退出 App，或明确传入 --replace-running" >&2
  exit 1
fi

if [[ "$REPLACE_RUNNING" == true && -n "$LEGACY_LAUNCHER_PID" ]]; then
  LEGACY_SERVER_PID="$(ps -ww -axo pid=,ppid=,command= | awk -v parent="$LEGACY_LAUNCHER_PID" \
    '$2 == parent && $0 ~ /wb web --host 127\.0\.0\.1 --port/ { print $1; exit }' || true)"
  for pid in "$LEGACY_SERVER_PID" "$LEGACY_LAUNCHER_PID"; do
    if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then kill -TERM "$pid"; fi
  done
  for _ in {1..40}; do
    launcher_alive=false
    server_alive=false
    if [[ "$LEGACY_LAUNCHER_PID" =~ ^[0-9]+$ ]] && kill -0 "$LEGACY_LAUNCHER_PID" 2>/dev/null; then launcher_alive=true; fi
    if [[ "$LEGACY_SERVER_PID" =~ ^[0-9]+$ ]] && kill -0 "$LEGACY_SERVER_PID" 2>/dev/null; then server_alive=true; fi
    if [[ "$launcher_alive" == false && "$server_alive" == false ]]; then break; fi
    sleep 0.25
  done
  if [[ "$launcher_alive" == true || "$server_alive" == true ]]; then
    echo "✗ 旧 SummitWorkbench 实例未在 10 秒内退出，取消安装" >&2
    exit 1
  fi
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
# 旧备份自动清理：.previous 只会来自上一轮安装留下的「被替换版本」；本轮即将用
# $SOURCE_APP 原子替换 $DEST_APP，旧 .previous 无保留价值（回滚用的是本轮 mv 出的备份），
# 直接清掉，避免阻塞下次安装。
if [[ -e "$BACKUP_APP" ]]; then
  echo "↻ 清理上次安装的旧备份：$BACKUP_APP"
  rm -rf "$BACKUP_APP"
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
    # 安装成功即不再保留本轮备份（被替换的旧版），下次安装无需手动清理。
    rm -rf "$BACKUP_APP" || true
    echo "✓ 已安装并启动 $DEST_APP"
    exit 0
  fi
  sleep 0.25
done
echo "✗ App 已安装但服务未在 readiness 窗口内启动；旧 App 保留在 $BACKUP_APP" >&2
exit 1
