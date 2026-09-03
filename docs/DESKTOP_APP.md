# 桌面 App（macOS）

当前生产路径是原生 Swift/AppKit + WebKit 壳：App 先验证 `/api/version`，服务 ready 后才创建页面导航，随后由唯一的 WKWebView 加载带 build identity 的 canonical URL。Chrome 不再是生产依赖；旧 Chrome 启动器仅通过隐藏的 `WB_RENDERER=chrome` 开发回滚构建保留。

原生壳使用 `LSUIElement`，不显示 Dock 图标。窗口关闭只隐藏窗口，不停止服务；网页顶栏「退出」通过 native bridge 请求监督器停止自己管理的服务。重复打开 App 会复用同一个窗口：服务和 build 一致时只把窗口带到前台，不重建 WebView。

## 构建

```bash
uv sync --extra web
npm --prefix web run build
scripts/build-macos-app.sh
```

产物为 `dist/SummitWorkbench.app`。构建脚本会把当前静态资源的 build identity 写入
`Contents/Resources/build-manifest.json`，并用系统 Swift 编译
`native/SummitWorkbench/*.swift`，链接 AppKit 与 WebKit。当前 Phase 3 的服务仍由构建时绑定的
仓库 `.venv/bin/wb` 启动；自包含 server 与安装替换属于后续 Phase 4。

可选参数：`scripts/build-macos-app.sh 8787` 指定端口；`WORK_ROOT` 和 `WB_BIN` 可在构建时覆盖。
普通生产构建不要设置 `WB_RENDERER=chrome`。

## 服务监督

生产 App 通过 `/api/version` 验证产品 ID、协议和 frontend build，不以 TCP 可连接作为 ready 判据。
无法识别的端口占用不会终止未知进程。由当前 App 启动的服务写入
`~/Library/Application Support/SummitWorkbench/runtime.json`，监督器依据 PID、启动时间和可执行路径识别自有服务。

自有服务异常退出时按 0/1/2/4/8 秒退避重启，连续失败进入 crash-loop 状态并保留 App 窗口供用户重试；开发外部服务模式只等待服务恢复，不自行拉起服务。

## 页面与诊断

- WKWebView 使用默认 website data store，保留现有 localStorage 问答历史，不清空整套网站数据。
- 主框架只允许 `http://127.0.0.1:<configured-port>`；其他 HTTP/HTTPS 链接交给默认浏览器。
- 页面通过 `wbLifecycle` bridge 上报 `clientReady`，并可请求退出或复制诊断信息；bridge 不接受 shell 命令、路径或 PID。
- 页面右上角显示前端 build、服务版本和同步状态；更新、服务重启和 Web 内容进程恢复均由 App 与 SPA 自动处理。
- 结构化生命周期日志：`~/Library/Logs/summitworkbench-panel.log`，达到 5 MB 自动轮转并保留 3 份。

用户无需清缓存、打开 DevTools 或手动强制刷新。最终生产自包含后端、原子打包和安装验收不在本阶段范围内。
