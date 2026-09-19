# launchd 定时（M2-7）

Mac Studio 上的自动调度。晨间简报每日 08:00（`com.summitworkbench.brief`），
周复盘每周一 07:30（`com.summitworkbench.weekly`，复盘上一自然周）。
两者都**不写知识库**（自 2026-09-19 起落本机程序目录），因此不再需要提交/推送步骤。

## 安装

```bash
scripts/install-launchd.sh
```

脚本会：从 `command -v wb` 推导可执行路径（可用 `WB_BIN=/abs/path/wb` 覆盖），
用 `WORK_ROOT`（默认 `~/Documents/Work`）与 `$HOME` 填充 plist 模板，写入
`~/Library/LaunchAgents/` 并 `launchctl bootstrap` 载入。重复运行幂等（先 bootout 再载入）。

## 校验

```bash
# 立即触发一次（不等到 08:00）
launchctl kickstart -k gui/$(id -u)/com.summitworkbench.brief
# 看日志
tail -n 40 ~/Library/Logs/summitworkbench-brief.log
```

简报应出现在本机程序目录
`~/Library/Application Support/SummitWorkbench/profiles/<workspace_id>/briefs/YYYY-MM-DD.md`
（**不再**写 `_vault/daily/`，库内也不应出现新的提交）。

## 卸载

```bash
launchctl bootout gui/$(id -u)/com.summitworkbench.brief
launchctl bootout gui/$(id -u)/com.summitworkbench.weekly
rm ~/Library/LaunchAgents/com.summitworkbench.brief.plist ~/Library/LaunchAgents/com.summitworkbench.weekly.plist
```

## 说明

- 简报/周复盘不在知识库内（落本机程序目录），`wb brief --commit --push` /
  `wb weekly --commit --push` 是**显式无操作**（参数保留只为兼容既有装机 plist）。
  模板已不再传这两个参数。
- 主机在 08:00 处于休眠时，launchd 会在下次唤醒补跑一次。
- 简报生成时若健康度非「正常」（采集源失败/排序降级/当日无信号），会发一条 macOS 通知。
