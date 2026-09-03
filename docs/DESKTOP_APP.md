# 桌面 App（macOS）

把本地 Web 面板包成一个原生 `.app`：双击启动 `wb web` 并在独立应用窗口
（Chrome app 模式，无 Chrome 时退化为默认浏览器）打开面板。

主程序是**原生 Swift/AppKit 启动器**（`scripts/summit_launcher.swift`，构建时 `swiftc`
编译）——脚本型主程序无法向 LaunchServices 报告「启动完成」，前台形态会 Dock 图标
无限弹跳、后台形态会报「应用无响应」；原生主程序注册正常的应用生命周期，根治两者。
App 以 **LSUIElement（后台代理）** 形态运行，**不占程序坞**，退出面板用网页顶栏的
「退出」按钮（调用 `/api/shutdown`，服务停止后启动器自动退出）。

不需要 Rust/Tauri，只需系统自带工具（含 Xcode 命令行工具 `xcode-select --install`）。

## 构建

```bash
uv sync --extra web           # 确保 web 依赖已装
scripts/build-macos-app.sh    # 产物在 dist/SummitWorkbench.app（可选：PORT 作第 1 参数）
```

构建时若 `assets/icon-1024.png` 存在，会用系统自带 `sips + iconutil` 生成 `AppIcon.icns`
并写入 bundle（访达/启动台显示雪山图标）。源图已随仓库提供；如需改图重跑：

```bash
uv run --with pillow python scripts/make-icon.py assets/icon-1024.png
scripts/build-macos-app.sh
```

`wb` 路径、`WORK_ROOT` 与端口在构建时烘焙进启动器（同 launchd 安装方式）。仓库迁移后
重跑脚本即可。

## 安装 / 打开（正式位置：/Applications）

**App 只装在 `/Applications`**（不放桌面、不复制到别处）；它烘焙的 `wb` 路径指向仓库
`.venv`（editable），因此**与仓库代码自动链接**——仓库每次改造只需重建前端 + 重启 App，
无需重新安装或重新链接。

```bash
scripts/build-macos-app.sh                          # 产物在 dist/SummitWorkbench.app
rm -rf /Applications/SummitWorkbench.app
cp -R dist/SummitWorkbench.app /Applications/
xattr -dr com.apple.quarantine /Applications/SummitWorkbench.app   # 首次打开免 Gatekeeper 拦
open /Applications/SummitWorkbench.app              # 从「应用程序」/ 启动台打开
```

首次打开若仍被 Gatekeeper 拦（未签名），右键 →「打开」即可。

> 提示：旧的「桌面副本」做法已弃用（桌面的 SummitWorkbench.app 已移入废纸篓）。
> 日常请统一从「应用程序」或启动台打开 `/Applications/SummitWorkbench.app`。

## 更新（换新版本 / 改了前端没生效？）

- **用户日常只打开 App / 浏览器面板，不用 CLI**（见 README 与 WEB_WORKBENCH §7）。App 只是
  Swift 启动器：烘焙 `$REPO_ROOT/.venv/bin/wb`（uv sync **editable** 安装），服务运行时直接
  读仓库 `src/summit_workbench/webapp/static/` 下的前端产物——**这就是「自动链接到项目」**：
  只要仓库还是这个路径，改完代码重建后重启 App 就是新版。
- **Web 界面更新 = `cd web && npm run build` + 重启面板服务**，**不需要重装 /Applications 里
  的 .app**（只有 `wb` 路径 / `WORK_ROOT` / 端口 / 仓库路径变了才重跑
  `scripts/build-macos-app.sh` + 重新安装）。重启方式：退出正在运行的面板（网页顶栏
  「退出」），再从「应用程序」打开 App 重新拉起；或直接重跑 `wb web`。
- 改了版本仍看到旧界面，按序排查：① 服务是否在构建后重启过；② 浏览器缓存了旧 `index.html`
  （引用的旧哈希资源已删）→ **⌘⇧R 强刷**；③ 打开的是不是本仓库构建的 App——`/Applications`
  里的 `SummitKnowledge.app` / `SummitServerAI.app` 是**历史遗留旧产品**（内嵌冻结的旧前端
  runtime），不是本仓库产物；请打开 `/Applications/SummitWorkbench.app`（安装命令见上）。

## 说明

- 启动器拉起 `wb web` 子进程并打开面板窗口，**App 进程存活 = 服务存活**；启动器周期
  探测 `/api/state`，服务停止后自动退出。退出面板用网页顶栏「退出」按钮（POST
  `/api/shutdown`，带 `X-WB-Shutdown` 头防任意网页误关），服务优雅退出并关窗。
- 已运行时再次双击/打开 App → 重新弹出面板窗口（不重复起服务）；端口已被占用（例如
  已在别处 `wb web`）时同样只开窗口。
- 日志：`~/Library/Logs/summitworkbench-panel.log`。
- 图标：雪山主题，源图 `assets/icon-1024.png`（由 `scripts/make-icon.py` 用 Pillow 生成），
  构建时转 `.icns` 注入 bundle。换新图后若仍显旧图标（访达/启动台），是系统图标缓存，
  重登录或 `killall Dock` 可刷新。
- 想要真正的原生窗口壳（非浏览器）可后续上 Tauri，但需安装 Rust 工具链；当前方案仅
  依赖系统自带工具。
