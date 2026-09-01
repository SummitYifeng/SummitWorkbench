# 桌面 App（macOS）

把本地 Web 面板包成一个原生 `.app`：Dock 有图标，双击启动 `wb web` 并在独立应用窗口
（Chrome app 模式，无 Chrome 时退化为默认浏览器）打开面板；退出 App 即关服务。

不需要 Rust/Tauri，只用系统自带工具，复用整套 FastAPI 面板。

## 构建

```bash
uv sync --extra web           # 确保 web 依赖已装
scripts/build-macos-app.sh    # 产物在 dist/SummitWorkbench.app（可选：PORT 作第 1 参数）
```

构建时若 `assets/icon-1024.png` 存在，会用系统自带 `sips + iconutil` 生成 `AppIcon.icns`
并写入 bundle（Dock/访达显示雪山图标）。源图已随仓库提供；如需改图重跑：

```bash
uv run --with pillow python scripts/make-icon.py assets/icon-1024.png
scripts/build-macos-app.sh
```

`wb` 路径与 `WORK_ROOT` 在构建时烘焙进 App（同 launchd 安装方式）。仓库迁移后重跑脚本即可。

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

- App 前台运行 uvicorn，**App 存活 = 服务存活**；Cmd-Q / Dock 退出即停服务。
- 端口已被占用（例如已在别处 `wb web`）时，App 只打开窗口、不重复起服务。
- 日志：`~/Library/Logs/summitworkbench-panel.log`。
- 图标：雪山主题，源图 `assets/icon-1024.png`（由 `scripts/make-icon.py` 用 Pillow 生成），
  构建时转 `.icns` 注入 bundle。换新图后 Dock 若仍显旧图标，是系统图标缓存，重登录或
  `killall Dock` 可刷新。
- 想要真正的原生窗口壳（非浏览器）可后续上 Tauri，但需安装 Rust 工具链；当前方案零额外依赖。
