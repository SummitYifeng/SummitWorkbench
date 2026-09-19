# 从 0 装机核对清单（Studio + Air · `0.4.9` / build `2026091925`）

> 用途：拿到本次交付包后，在两台 Mac 上从零装到「能用 + 双机同步通」的自检清单。
> 规格与背景见 [`docs/RELEASING.md`](../RELEASING.md)「用户安装与卸载」、
> [`DUAL-DEVICE-REHEARSAL.md`](DUAL-DEVICE-REHEARSAL.md) §A7（第二台接入）与 §A6（双机闭环）。
> 本清单只列动作与判据。**不要把「往真实 vault 里写测试内容」当成验证手段**——经 App 的写入会
> 自动 commit + push（见 `AGENTS.md` 的自动推送纪律）。

## 0 · 先核对包身份，再装机

| 项 | 值 |
| --- | --- |
| 版本 / build | `0.4.9` / **`2026091925`** |
| 源码提交 | **`e62d3a3`** |
| 前端身份 | **`v2026.09.19-d1a8ace7`** |
| DMG | `dist/releases/0.4.9/arm64/SummitWorkbench-0.4.9-arm64-INTERNAL-DEV.dmg` |
| **DMG SHA-256** | `6c31855d4f42c82fc247755c2d955a0354dd5ea58d6066015ffd0d1f42506243` |
| **App SHA-256** | `ca58c8466a7e195fe23a38d485fa1de0791771fa56610725815789619275557b` |

```bash
shasum -a 256 <DMG 路径>     # 必须与上表 DMG SHA-256 完全一致
```

- [ ] 两台机器都是 **Apple Silicon（M2 及以上）**、macOS **13.0+**（产品只支持 arm64，Intel 会被拒绝）
- [ ] DMG SHA-256 与上表一致——**认 SHA，不认文件名**（文件名里没有 build 号）

## 1 · 每台机器：安装（约 2 分钟）

- [ ] 双击 DMG → 把 `SummitWorkbench.app` 拖进 `/Applications`
- [ ] **第一次打开**：右键点图标 → 选「打开」→ 再点一次「打开」
      （内部包是 ad-hoc 签名，首次会被 Gatekeeper 拦；之后不再拦）
- [ ] 首次读到 vault 时会弹「"SummitWorkbench" 想访问「文稿」文件夹中的文件」→ 点**允许**
      - vault 建在 `~/Documents` 下，属于 macOS TCC 保护目录；ad-hoc 签名每次构建都不同，
        **每次重新装机/换包都会再弹一次**
      - **没点之前的现象是界面一直转圈**（服务本身是活的：`/api/version` 秒回，但读 vault 的接口会等）
      - 误点「不允许」：系统设置 → 隐私与安全性 → 文件与文件夹 → 给 SummitWorkbench 打开后重试
- [ ] Dock / 菜单栏图标出现；设置页版本状态条显示 `0.4.9 · build 2026091925`

## 2 · Studio（主设备）：接上工作台 + 两处凭据

向导只有三步：**新建/连接工作区 → 粘贴 DeepSeek API Key → 点「授权飞书」**。

- [ ] 向导第 1 步选「**连接已有工作台**」并指向既有 vault（`~/Documents/Work/_vault`）——沿用现有内容
      - 若要真的从零开新库：选「**新建我的工作台**」。新工作台**已自动纳入 git**（首个提交
        `wb: onboarding create`，撤销历史可用），但**没有远端**——接远端的办法见 §5 的 G2
- [ ] 模型：粘贴 DeepSeek API Key → 设置页「AI 模型」卡片显示可用
- [ ] 飞书：点「授权飞书」→ 浏览器里完成授权 → 回来显示已授权
      （包内**已内置**应用级默认凭据，**不需要**手填 `app_id`/`app_secret`）
- [ ] 设置 → **高级与维护 → Git 同步**：确认远端是 **HTTPS** 形式 + GitHub 用户名 + PAT，
      点「预览」通过（这一步会把 **workspace 级**凭据写进 Keychain，App 之后才能自己 fetch/push）
- [ ] 「今日」页能看到项目与「收件箱（N 条）」（数据来自 vault，说明读路径通了）

## 3 · Air（次设备）：用「从另一台 Mac 克隆」接入

- [ ] 向导第 1 步选「**从另一台 Mac 克隆**」（该选项只在空安装时出现）
- [ ] 填 vault 的 **HTTPS** 远端地址（`origin` + `upstream` 形状）+ GitHub 用户名 + PAT
      —— PAT 只进 **workspace 级** Keychain，不会覆盖你日常 `github.com` 的凭据条目
- [ ] 同样完成模型 Key 与飞书授权两步
- [ ] 克隆完成后「今日」页内容与 Studio 一致

## 4 · 双机同步闭环（约 10 分钟）

- [ ] Studio 写一条**日常手记** → 提交并推送成功；「撤销历史」里能看到对应的 `wb:` 提交
- [ ] Air 触发同步 → 拉到同一条内容；两侧 `git status` 干净、`ahead/behind = 0/0`
- [ ] **保护态**：让 Air 的 `/api/sync/status` 失败一次（关 Wi-Fi 或停本地服务）→ 横幅**不消失**、
      保留上次成功读取的状态，并出现「重新读取」；恢复后点它，错误行消失
- [ ] **分叉场景（可选，完整步骤见 `DUAL-DEVICE-REHEARSAL.md` §A6.2）**：Air 离线写 + Studio 写并推 →
      Air 重试进入 `diverged-protected` → 详情 → 选择 → 临时预检 → 确认恢复 →
      出现**双父提交** → 普通 push 成功 → Studio 下次同步是 **fast-forward**

## 5 · 已知边界（是已知项，不是故障）

- [ ] **G2（未关闭）**：界面没有「把已有本地工作台首次发布到新远端」的路径。全新库要接远端仍需手工：
      在 GitHub 建**空**私有仓库 → 本地 `git remote add origin/upstream <HTTPS>` → 首次 push →
      再回设置页点「预览 HTTPS 转换」（它本质是同一仓库的 SSH→HTTPS 规范化，需要 `origin`+`upstream` 已存在）。
- [ ] **D9（未修）**：冲突恢复提交后的 push 可能被误判为「非快进」。恢复后若横幅报非快进，
      点一次「立即重试」（或先在另一侧拉一次）即可，**不是数据丢失**。
- [ ] **卸载 App ≠ 删除数据**：profile 在 `~/Library/Application Support/SummitWorkbench`，
      日志在 `~/Library/Logs/`，vault 在你自己选的目录，Keychain 条目也不随卸载删除。
- [ ] **远端 CI 只在手动触发时运行**（`gh workflow run ci.yml --ref main`）；push 与 PR 不会自动跑。
      日常守门的是本地 `scripts/pre-push-gate.sh`。
- [ ] 若某台机器同步一直不 ready：先看「同步失败原因码」与
      `~/Library/Logs/summitworkbench-server.log`（只写原因码，不写你的文件内容或凭据）。
