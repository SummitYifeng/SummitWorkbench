# 桌面 App（macOS）

把本地 Web 面板包成一个原生 `.app`：Dock 有图标，双击启动 `wb web` 并在独立应用窗口
（Chrome app 模式，无 Chrome 时退化为默认浏览器）打开面板；退出 App 即关服务。

不需要 Rust/Tauri，只用系统自带工具，复用整套 FastAPI 面板。

## 构建

```bash
uv sync --extra web           # 确保 web 依赖已装
scripts/build-macos-app.sh    # 产物在 dist/SummitWorkbench.app（可选：PORT 作第 1 参数）
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
- 图标暂用系统默认；如需自定义 `.icns` 放进 `Contents/Resources` 并在 Info.plist 加
  `CFBundleIconFile` 即可（后续可加）。
- 想要真正的原生窗口壳（非浏览器）可后续上 Tauri，但需安装 Rust 工具链；当前方案零额外依赖。
