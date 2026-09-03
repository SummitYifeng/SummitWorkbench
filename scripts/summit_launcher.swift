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
import Darwin
import Foundation

// 烘焙值（构建时替换）
let kWbBin: String = "__WB_BIN__"
let kPort: String = "__PORT__"
let kWorkRoot: String = "__WORK_ROOT__"

private struct VersionPayload: Decodable {
    let product_id: String
    let api_protocol: Int
    let frontend_build: String
}

final class Launcher: NSObject, NSApplicationDelegate {
    private var server: Process?
    private var serverLog: FileHandle?
    private var wasUp = false
    private var failCount = 0
    private var timer: Timer?
    private var loggedUp = false
    private var loggedDown = false
    private var readinessInFlight = false
    private var readinessCompletions: [(VersionPayload) -> Void] = []
    private var migrationInFlight = false

    private var panelURL: URL { URL(string: "http://127.0.0.1:\(kPort)/")! }
    private var panelProfilePath: String {
        NSHomeDirectory() + "/Library/Application Support/SummitWorkbench/browser"
    }
    private var migrationMarkerURL: URL {
        URL(fileURLWithPath: NSHomeDirectory())
            .appendingPathComponent("Library/Application Support/SummitWorkbench/migrations")
            .appendingPathComponent("chrome-window-refresh-v1.done")
    }
    private var logPath: String {
        NSHomeDirectory() + "/Library/Logs/summitworkbench-panel.log"
    }
    private var chromePath: String {
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        startServerIfNeeded { [weak self] version in
            self?.migrateAndOpenPanel(version)
        }
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
        log("收到 reopen，先验证服务版本")
        startServerIfNeeded { [weak self] version in
            self?.migrateAndOpenPanel(version)
        }
        return false
    }

    private func openPanel(_ version: VersionPayload) {
        var components = URLComponents(url: panelURL, resolvingAgainstBaseURL: false)!
        components.queryItems = [URLQueryItem(name: "build", value: version.frontend_build)]
        let targetURL = components.url!
        if FileManager.default.isExecutableFile(atPath: chromePath) {
            let p = Process()
            p.executableURL = URL(fileURLWithPath: chromePath)
            p.arguments = [
                "--app=\(targetURL.absoluteString)",
                "--user-data-dir=\(panelProfilePath)",
            ]
            do {
                try p.run()
                log("已打开 Chrome panel build=\(version.frontend_build)")
            } catch {
                log("Chrome 启动失败：\(error.localizedDescription)")
            }
        } else {
            NSWorkspace.shared.open(targetURL)
            log("未找到 Chrome，已交给默认浏览器打开 build=\(version.frontend_build)")
        }
    }

    private func startServerIfNeeded(completion: @escaping (VersionPayload) -> Void) {
        readinessCompletions.append(completion)
        if readinessInFlight {
            log("readiness 请求进行中，合并重复启动请求")
            return
        }
        readinessInFlight = true
        requestVersion { [weak self] version in
            guard let self else { return }
            if let version {
                self.wasUp = true
                self.log("服务身份已验证 build=\(version.frontend_build)")
                self.finishReadiness(version)
                return
            }
            self.spawnServer()
            self.waitForReady { [weak self] ready in
                self?.finishReadiness(ready)
            }
        }
    }

    private func finishReadiness(_ version: VersionPayload?) {
        readinessInFlight = false
        let completions = readinessCompletions
        readinessCompletions.removeAll()
        guard let version else {
            log("readiness 失败，未打开面板")
            return
        }
        completions.forEach { $0(version) }
    }

    private func spawnServer() {
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
            log("已启动面板服务，等待 /api/version readiness")
        } catch {
            log("面板服务启动失败：\(error.localizedDescription)")
        }
    }

    private func requestVersion(completion: @escaping (VersionPayload?) -> Void) {
        var request = URLRequest(url: panelURL.appendingPathComponent("api/version"))
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.timeoutInterval = 1.0
        URLSession.shared.dataTask(with: request) { data, response, _ in
            let version: VersionPayload?
            if let data,
               let http = response as? HTTPURLResponse,
               http.statusCode == 200,
               let decoded = try? JSONDecoder().decode(VersionPayload.self, from: data),
               decoded.product_id == "com.summitworkbench.panel",
               decoded.api_protocol >= 2 {
                version = decoded
            } else {
                version = nil
            }
            DispatchQueue.main.async {
                completion(version)
            }
        }.resume()
    }

    private func waitForReady(
        completion: @escaping (VersionPayload?) -> Void,
        attempt: Int = 0
    ) {
        requestVersion { [weak self] version in
            guard let self else { return }
            if let version {
                self.wasUp = true
                self.log("服务 ready build=\(version.frontend_build)")
                completion(version)
                return
            }
            let delays: [Double] = [0.1, 0.25, 0.5, 1, 1, 2, 2, 2, 2, 2]
            guard attempt < delays.count else {
                self.log("服务未在 readiness 窗口内就绪，未打开页面")
                completion(nil)
                return
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + delays[attempt]) {
                self.waitForReady(completion: completion, attempt: attempt + 1)
            }
        }
    }

    private func migrateAndOpenPanel(_ version: VersionPayload) {
        if FileManager.default.fileExists(atPath: migrationMarkerURL.path) {
            openPanel(version)
            return
        }
        if migrationInFlight {
            log("Chrome migration 进行中，合并重复 reopen")
            return
        }
        migrationInFlight = true
        migrateLegacyChrome { [weak self] migrated in
            guard let self else { return }
            self.migrationInFlight = false
            guard migrated else { return }
            self.openPanel(version)
            self.confirmMigration(version)
        }
    }

    private func confirmMigration(_ version: VersionPayload) {
        // Phase 1 的 SPA 会以 no-store 入口和 build 握手完成整页自愈；这里再次确认
        // 服务仍伺服同一 build 后写 marker，不通过 AppleScript/CDP 读取 Chrome 页面。
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) { [weak self] in
            self?.requestVersion { [weak self] current in
                guard let self, current?.frontend_build == version.frontend_build else {
                    self?.log("Chrome migration 未确认目标 build，保留 marker 供下次重试")
                    return
                }
                let directory = self.migrationMarkerURL.deletingLastPathComponent()
                try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
                try? Data("SummitWorkbench Chrome migration v1\n".utf8).write(to: self.migrationMarkerURL, options: .atomic)
                self.log("Chrome migration marker 已写入 build=\(version.frontend_build)")
            }
        }
    }

    private func migrateLegacyChrome(completion: @escaping (Bool) -> Void) {
        guard let pid = dedicatedChromePID() else {
            log("未找到严格匹配的 SummitWorkbench Chrome 主进程，跳过终止")
            completion(true)
            return
        }
        log("终止严格匹配的旧 Chrome 主进程 pid=\(pid)")
        guard kill(pid, SIGTERM) == 0 else {
            log("旧 Chrome 主进程 SIGTERM 失败，取消迁移")
            completion(false)
            return
        }
        waitForProcessExit(pid, completion: completion)
    }

    private func waitForProcessExit(
        _ pid: pid_t,
        startedAt: Date = Date(),
        completion: @escaping (Bool) -> Void
    ) {
        if kill(pid, 0) != 0 {
            completion(true)
            return
        }
        if Date().timeIntervalSince(startedAt) >= 5.0 {
            log("旧 Chrome 主进程 5 秒内未退出，取消迁移启动")
            completion(false)
            return
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) { [weak self] in
            self?.waitForProcessExit(pid, startedAt: startedAt, completion: completion)
        }
    }

    private func dedicatedChromePID() -> pid_t? {
        let ps = Process()
        let output = Pipe()
        ps.executableURL = URL(fileURLWithPath: "/bin/ps")
        ps.arguments = ["-ww", "-axo", "pid=,command="]
        ps.standardOutput = output
        ps.standardError = FileHandle.nullDevice
        do { try ps.run() } catch { return nil }
        ps.waitUntilExit()
        guard let text = String(data: output.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) else {
            return nil
        }
        for line in text.split(separator: "\n") {
            let columns = line.split(separator: " ", maxSplits: 1, omittingEmptySubsequences: true)
            guard columns.count == 2, let pid = pid_t(columns[0]) else { continue }
            let command = String(columns[1])
            guard (command == chromePath || command.hasPrefix(chromePath + " ")),
                  command.contains("--user-data-dir=\(panelProfilePath)"),
                  !command.contains("--type=") else { continue }
            return pid
        }
        return nil
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
