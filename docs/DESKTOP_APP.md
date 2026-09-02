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

## 安装 / 打开

```bash
open dist/SummitWorkbench.app           # 直接打开
# 或拖到 /Applications 后从启动台/访达打开
```

首次打开若被 Gatekeeper 拦（未签名），右键 →「打开」，或：

```bash
xattr -dr com.apple.quarantine dist/SummitWorkbench.app
```

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
