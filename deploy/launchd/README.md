# launchd 定时（M2-7）

Mac Studio 上的自动调度。晨间简报每日 08:00，周复盘每周一 07:30（后者随 M2-10 交付）。

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

当日 `_vault/daily/YYYY-MM-DD.md` 应出现简报区块，且 vault 里多出一条
`chore(brief): 晨间简报 …` 提交。

## 卸载

```bash
launchctl bootout gui/$(id -u)/com.summitworkbench.brief
rm ~/Library/LaunchAgents/com.summitworkbench.brief.plist
```

## 说明

- `wb brief --commit --push` 只暂存并提交**简报自己写的文件**（当日笔记 + 信号快照），
  不会波及 vault 里你的其它未提交改动；落后远端时不推送，交由 `wb sync` 合并。
- 主机在 08:00 处于休眠时，launchd 会在下次唤醒补跑一次。
- 简报生成时若健康度非「正常」（采集源失败/排序降级/当日无信号），会发一条 macOS 通知。
