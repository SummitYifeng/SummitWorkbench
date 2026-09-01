#!/usr/bin/env bash
# 安装/更新 SummitWorkbench 的 launchd 定时任务（M2-7）。
#
# 用法：
#   scripts/install-launchd.sh            # 安装晨间简报（每日 08:00）
#   WB_BIN=/path/to/wb scripts/install-launchd.sh
#
# 幂等：重复运行会先 bootout 旧任务再重新载入。不硬编码用户名/路径（NFR-3），
# 全部从环境与 `command -v wb` 推导。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WB_BIN="${WB_BIN:-$(command -v wb || true)}"
WORK_ROOT="${WORK_ROOT:-$HOME/Documents/Work}"
LA_DIR="$HOME/Library/LaunchAgents"

if [[ -z "$WB_BIN" ]]; then
  echo "✗ 找不到 wb 可执行文件。请先 uv tool install，或用 WB_BIN=/abs/path/wb 指定。" >&2
  exit 1
fi

mkdir -p "$LA_DIR" "$HOME/Library/Logs"

install_one() {
  local label="$1" template="$2"
  local dest="$LA_DIR/$label.plist"
  sed -e "s#__WB_BIN__#$WB_BIN#g" \
      -e "s#__WORK_ROOT__#$WORK_ROOT#g" \
      -e "s#__USER_HOME__#$HOME#g" \
      "$template" > "$dest"
  # 幂等重载（bootout 可能因未加载而非零，忽略）。
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$dest"
  echo "✓ 已安装 $label → $dest"
}

install_one "com.summitworkbench.brief" "$REPO_ROOT/deploy/launchd/com.summitworkbench.brief.plist"

echo ""
echo "wb 路径：$WB_BIN"
echo "WORK_ROOT：$WORK_ROOT"
echo "日志：$HOME/Library/Logs/summitworkbench-brief.log"
echo "手动触发验证：launchctl kickstart -k gui/$(id -u)/com.summitworkbench.brief"
