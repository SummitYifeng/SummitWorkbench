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

RUNTIME_ROOT="$HOME/Library/Application Support/SummitWorkbench"

# runtime record 有两个合法落点，必须都查（与 native/SummitWorkbench/RuntimeRecord.swift 的
# candidateURLs 同口径）：
#   1. <app_support>/runtime.json              —— 打包 App 走这条：原生启动器把它作为
#      WB_RUNTIME_RECORD 交给 bundle server（ServiceSupervisor.swift）；
#   2. <app_support>/profiles/*/runtime/runtime.json —— `wb web` CLI 走这条。
# 只查第 2 条会造成两个真问题（2026-09-13 装 build 35 时实测踩到）：把正在运行的 App 当成没在跑
# 而直接替换；以及服务其实已就绪却在 readiness 窗口结束后误报失败、把 .previous 留在原地。
runtime_records() {
  if [[ -f "$RUNTIME_ROOT/runtime.json" ]]; then
    printf '%s\n' "$RUNTIME_ROOT/runtime.json"
  fi
  find "$RUNTIME_ROOT/profiles" -path '*/runtime/runtime.json' -type f 2>/dev/null || true
}

if [[ "$REPLACE_RUNNING" != true && -n "$(runtime_records)" ]]; then
  echo "✗ 检测到 SummitWorkbench runtime record；请先退出 App，或明确传入 --replace-running" >&2
  exit 1
fi

# Phase 2 旧启动器没有 runtime record；按完整可执行路径识别它，避免新旧 App 同时争用端口。
# 用 comm（可执行文件路径）做「精确相等」比较，而不是对整条命令行做正则匹配：
# 后者会匹配到本命令自己的 awk 进程（其命令行里含有同一个 target 字符串），造成随机的误报。
LEGACY_LAUNCHER_PID="$(ps -ww -axo pid=,comm= | awk -v target="$DEST_APP/Contents/MacOS/SummitWorkbench" \
  '{ pid=$1; sub(/^[[:space:]]*[0-9]+[[:space:]]+/, ""); if ($0 == target) { print pid; exit } }' || true)"
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

if [[ "$REPLACE_RUNNING" == true ]]; then
  while IFS= read -r RUNTIME_FILE; do
    [[ -n "$RUNTIME_FILE" ]] || continue
    read -r SERVICE_PID < <("$REPO_ROOT/.venv/bin/python" - "$RUNTIME_FILE" <<'PY'
import json
import sys
from pathlib import Path

record = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(record.get("pid", ""))
PY
    )
    for pid in "$SERVICE_PID"; do
      if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
        command_line="$(ps -p "$pid" -o command= 2>/dev/null || true)"
        if [[ "$command_line" == *"SummitWorkbench"* ]]; then kill -TERM "$pid"; fi
      fi
    done
    for _ in {1..40}; do
      if ! kill -0 "${SERVICE_PID:-0}" 2>/dev/null; then break; fi
      sleep 0.25
    done
  done < <(runtime_records)
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
for _ in {1..40}; do
  while IFS= read -r RUNTIME_FILE; do
    [[ -n "$RUNTIME_FILE" ]] || continue
    PORT="$($REPO_ROOT/.venv/bin/python - "$RUNTIME_FILE" <<'PY'
import json
import sys
print(json.loads(open(sys.argv[1], encoding="utf-8").read())["port"])
PY
    )"
    # Production API routes require the App-owned session token, which is not
    # available to this installer.  The runtime record binds this port to the
    # launched workspace service; the native App separately verifies /api/version
    # with its token before navigating.  Probe the public shell here only for
    # HTTP readiness, rather than treating an expected 401 as a startup failure.
    if [[ "$PORT" =~ ^[0-9]+$ ]] && curl -fsS --max-time 1 "http://127.0.0.1:$PORT/" >/dev/null 2>&1; then
      # 安装成功即不再保留本轮备份（被替换的旧版），下次安装无需手动清理。
      rm -rf "$BACKUP_APP" || true
      echo "✓ 已安装并启动 ${DEST_APP}（runtime record：${RUNTIME_FILE}）"
      exit 0
    fi
  done < <(runtime_records)
  sleep 0.25
done
echo "✗ App 已安装但服务未在 readiness 窗口内启动；旧 App 保留在 $BACKUP_APP" >&2
exit 1
