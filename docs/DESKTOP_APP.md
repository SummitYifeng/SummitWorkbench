# 桌面 App（macOS）

当前生产路径是自包含的 Swift/AppKit + WebKit 壳：App 先验证 `/api/version`，服务 ready 后才创建页面导航，随后由唯一的 WKWebView 加载带 build identity 的 canonical URL。Chrome 已不再是运行或构建依赖。

原生壳使用 `LSUIElement`，不显示 Dock 图标。窗口关闭只隐藏窗口，不停止服务；网页顶栏「退出」通过 native bridge 请求监督器停止自己管理的服务。重复打开 App 会复用同一个窗口：服务和 build 一致时只把窗口带到前台，不重建 WebView。

## 构建

```bash
uv sync --extra web --extra dev --extra packaging
npm --prefix web run build
scripts/build-macos-app.sh
```

产物为 `dist/SummitWorkbench.app`。构建脚本会构建前端、用 PyInstaller onedir 打包
`SummitWorkbenchServer`，把 static/prompts/templates 与 server 放入 Resources，再用系统 Swift
编译 `native/SummitWorkbench/*.swift`，链接 AppKit 与 WebKit。构建结束前会完成 ad-hoc/指定身份签名、
签名校验和不依赖仓库 Python 的 server smoke test。

可选参数：`scripts/build-macos-app.sh 8787` 指定端口。`WORK_ROOT`、`WB_SERVER_BINARY`、
`WB_STATIC_DIR` 可在直接运行原生壳的开发场景中覆盖默认配置，不影响生产 bundle 的默认路径。

安装已验证的 bundle：

```bash
scripts/install-macos-app.sh dist/SummitWorkbench.app
```

安装脚本先校验签名与 manifest，再复制到临时目录并替换 `/Applications/SummitWorkbench.app`；旧包保留为
`/Applications/SummitWorkbench.app.previous` 以便恢复。检测到运行中的 runtime record 时默认停止，只有明确传入
`--replace-running` 才会按记录中的严格 PID/命令行尝试结束旧实例。

## 服务监督

生产 App 通过 `/api/version` 验证产品 ID、协议和 frontend build，不以 TCP 可连接作为 ready 判据。
无法识别的端口占用不会终止未知进程。由当前 App 启动的服务写入
`~/Library/Application Support/SummitWorkbench/runtime.json`，监督器依据 PID、启动时间和可执行路径识别自有服务。

服务从 `Contents/Resources/server/SummitWorkbenchServer` 启动，静态资源从
`Contents/Resources/web/static` 读取；生产 App 不依赖仓库 `.venv`、仓库路径或终端。

自有服务异常退出时按 0/1/2/4/8 秒退避重启，连续失败进入 crash-loop 状态并保留 App 窗口供用户重试；开发外部服务模式只等待服务恢复，不自行拉起服务。

## 页面与诊断

- WKWebView 使用默认 website data store，保留现有 localStorage 问答历史，不清空整套网站数据。
- 主框架只允许 `http://127.0.0.1:<configured-port>`；其他 HTTP/HTTPS 链接交给默认浏览器。
- 页面通过 `wbLifecycle` bridge 上报 `clientReady`，并可请求退出或复制诊断信息；bridge 不接受 shell 命令、路径或 PID。
- 页面右上角显示前端 build、服务版本和同步状态；更新、服务重启和 Web 内容进程恢复均由 App 与 SPA 自动处理。
- 结构化生命周期日志：`~/Library/Logs/summitworkbench-panel.log`，达到 5 MB 自动轮转并保留 3 份。

用户无需清缓存、打开 DevTools 或手动强制刷新。重新构建得到的新 App 应通过
`tests/integration/test_packaged_app.py` 的 `WB_PACKAGED_APP=...` smoke test 后再安装。
