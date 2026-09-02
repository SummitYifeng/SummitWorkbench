// SummitWorkbench 原生启动器（AppKit 后台代理）。
//
// 为什么需要原生主程序：纯 bash 脚本作为 .app 主程序无法向 LaunchServices 报告
// 「启动完成」——前台形态会 Dock 图标无限弹跳，LSUIElement 形态则报「无响应」。
// 本文件用真正的 AppKit 生命周期解决该问题，并保持「无 Dock 图标 + 网页退出」的体验。
//
// 生命周期约定：
// - App 进程 = 面板服务生命周期。启动时若服务未在跑则拉起 `wb web` 子进程，并打开
//   Chrome app 模式窗口（无 Chrome 时退化为默认浏览器）。
// - 周期探测面板端口（TCP connect）：服务停止（例如网页「退出」按钮调 /api/shutdown）
//   后自动退出。
// - 已运行时再次双击/打开 → 重新弹出面板窗口（applicationShouldHandleReopen）。
//
// 构建时由 build-macos-app.sh 用 sed 替换 __WB_BIN__ / __PORT__ / __WORK_ROOT__ 后编译。

import AppKit
import Foundation

// 烘焙值（构建时替换）
let kWbBin: String = "__WB_BIN__"
let kPort: String = "__PORT__"
let kWorkRoot: String = "__WORK_ROOT__"

final class Launcher: NSObject, NSApplicationDelegate {
    private var server: Process?
    private var serverLog: FileHandle?
    private var wasUp = false
    private var failCount = 0
    private var timer: Timer?
    private var loggedUp = false
    private var loggedDown = false

    private var panelURL: URL { URL(string: "http://127.0.0.1:\(kPort)/")! }
    private var logPath: String {
        NSHomeDirectory() + "/Library/Logs/summitworkbench-panel.log"
    }
    private var chromePath: String {
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        openPanel()
        startServerIfNeeded()
        let t = Timer(timeInterval: 2.0, repeats: true) { [weak self] _ in
            self?.probe()
        }
        RunLoop.main.add(t, forMode: .common)
        timer = t
    }

    func applicationWillTerminate(_ notification: Notification) {
        if let server, server.isRunning {
            server.terminate()
        }
        serverLog = nil
    }

    /// 已运行时再次打开（双击图标 / open）→ 重新弹面板窗口。
    func applicationShouldHandleReopen(
        _ sender: NSApplication, hasVisibleWindows flag: Bool
    ) -> Bool {
        openPanel()
        return true
    }

    private func openPanel() {
        if FileManager.default.isExecutableFile(atPath: chromePath) {
            let p = Process()
            p.executableURL = URL(fileURLWithPath: chromePath)
            p.arguments = [
                "--app=\(panelURL.absoluteString)",
                "--user-data-dir=\(NSHomeDirectory())/Library/Application Support/SummitWorkbench/browser",
            ]
            try? p.run()
        } else {
            NSWorkspace.shared.open(panelURL)
        }
    }

    private func startServerIfNeeded() {
        if serverUp() {
            wasUp = true
            return
        }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: kWbBin)
        p.arguments = ["web", "--host", "127.0.0.1", "--port", kPort]
        // 烘焙的 WORK_ROOT 传入子进程（与旧启动器 export 行为一致）。
        var env = ProcessInfo.processInfo.environment
        env["WORK_ROOT"] = kWorkRoot
        p.environment = env
        // 服务日志追加到 ~/Library/Logs/summitworkbench-panel.log（与旧启动器一致）。
        let fm = FileManager.default
        if !fm.fileExists(atPath: logPath) {
            fm.createFile(atPath: logPath, contents: nil)
        }
        if let fh = FileHandle(forWritingAtPath: logPath) {
            fh.seekToEndOfFile()
            p.standardOutput = fh
            p.standardError = fh
            serverLog = fh
        } else {
            p.standardOutput = FileHandle.nullDevice
            p.standardError = FileHandle.nullDevice
        }
        do {
            try p.run()
            server = p
        } catch {
            // 启动失败：靠周期探测超时后退出，面板窗口会显示连接失败。
        }
    }

    /// 服务是否存活：TCP 端口探测（loopback 即时返回，无 HTTP/URLSession 假阴性）。
    private func serverUp() -> Bool {
        let port = UInt16(kPort) ?? 8787
        let fd = socket(AF_INET, SOCK_STREAM, 0)
        guard fd >= 0 else { return false }
        defer { close(fd) }
        var addr = sockaddr_in()
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = port.bigEndian
        addr.sin_addr.s_addr = inet_addr("127.0.0.1")
        return withUnsafePointer(to: &addr) { ptr in
            ptr.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.connect(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) == 0
            }
        }
    }

    /// 状态转换写进面板日志（仅记录 up/down/exiting 变化，不刷屏）。
    private func log(_ line: String) {
        guard let fh = FileHandle(forWritingAtPath: logPath) else { return }
        defer { try? fh.close() }
        fh.seekToEndOfFile()
        let stamp = DateFormatter.localizedString(from: Date(), dateStyle: .short, timeStyle: .medium)
        let data = Data("[launcher \(stamp)] \(line)\n".utf8)
        try? fh.write(contentsOf: data)
    }

    private func probe() {
        let up = serverUp()
        if up {
            wasUp = true
            failCount = 0
            if !loggedUp { log("面板服务在线"); loggedUp = true }
            loggedDown = false
            return
        }
        if !loggedDown { log("面板服务不可达，等待退出确认…"); loggedDown = true }
        failCount += 1
        // 首次启动给 20s 缓冲（uvicorn 预热）；成功过之后 8s 判定服务已停止。
        let graceSeconds: Double = wasUp ? 8.0 : 20.0
        if Double(failCount) * 2.0 >= graceSeconds {
            log("面板服务已停止，退出")
            NSApp.terminate(nil)
        }
    }
}

let app = NSApplication.shared
let delegate = Launcher()
app.delegate = delegate
app.run()
