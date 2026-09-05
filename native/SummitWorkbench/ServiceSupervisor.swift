import Foundation
import Security

final class ServiceSupervisor {
    let configuration: AppConfiguration
    let logger: StructuredLogger
    private let client: ServiceClient
    let sessionToken: String
    private(set) var state: SupervisorState = .idle
    private(set) var identity: ServiceIdentity?
    private var process: Process?
    private var desiredStop = false
    private var ensureInFlight = false
    private var waiters: [(ServiceIdentity?) -> Void] = []
    private var failures: [Date] = []
    private var restartWork: DispatchWorkItem?
    var onStateChange: ((SupervisorState) -> Void)?
    /// 服务在**无进行中 ensureReady 周期**的后台恢复中到达 ready 时回调（如崩溃重启、
    /// 服务实例变化），供生命周期层重新装载面板。初始启动由 ensureReady 的 completion
    /// 负责，此处不重复触发。
    var onIdentityChange: ((ServiceIdentity) -> Void)?

    init(configuration: AppConfiguration, logger: StructuredLogger) {
        self.configuration = configuration
        self.logger = logger
        self.sessionToken = Self.newSessionToken()
        self.client = ServiceClient(port: 0, sessionToken: sessionToken)
    }

    func ensureReady(completion: @escaping (ServiceIdentity?) -> Void) {
        waiters.append(completion)
        guard !ensureInFlight else {
            logger.log("reopen_coalesced")
            return
        }
        ensureInFlight = true
        setState(.probing)
        logger.log("service_probe_started")
        client.probe { [weak self] result in
            guard let self else { return }
            switch result {
            case .valid(let identity): self.accept(identity)
            case .httpError:
                self.failConflict("端口被其他服务占用或服务协议不兼容")
            case .unavailable:
                if self.configuration.mode == .developmentExternal {
                    self.identity = nil
                    self.setState(.degraded)
                    self.finish(nil)
                } else {
                    self.startOwnedService()
                }
            }
        }
    }

    func stop(completion: (() -> Void)? = nil) {
        desiredStop = true
        restartWork?.cancel()
        setState(.stopping)
        logger.log("user_quit_requested")
        guard let process, process.isRunning else {
            RuntimeRecord.remove()
            setState(.stopped)
            completion?()
            return
        }
        process.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async {
                RuntimeRecord.remove()
                self?.setState(.stopped)
                completion?()
            }
        }
        process.terminate()
        DispatchQueue.global(qos: .utility).asyncAfter(deadline: .now() + 2.0) { [weak process] in
            guard let process, process.isRunning else { return }
            guard let record = RuntimeRecord.load(), record.pid == process.processIdentifier,
                  record.owns(process) else { return }
            kill(process.processIdentifier, SIGTERM)
        }
    }

    /// App 进程终止时的同步收尾：取消重启、终止自管服务并清理 runtime record。
    /// 不做等待（进程即将退出），与用户主动 quit 的异步 stop() 语义区分。
    func shutdownForApplicationTermination() {
        desiredStop = true
        restartWork?.cancel()
        logger.log("service_shutdown_for_termination")
        if let process, process.isRunning {
            process.terminationHandler = nil
            process.terminate()
        }
        RuntimeRecord.remove()
    }

    private func accept(_ identity: ServiceIdentity) {
        self.identity = identity
        logger.log("service_identity_verified", fields: ["server_instance": identity.serverInstance])
        if configuration.mode == .production && identity.frontendBuild != configuration.manifest.frontendBuild {
            if let record = RuntimeRecord.load(), record.serverInstance == identity.serverInstance,
               let process, record.owns(process) {
                logger.log("service_restart_scheduled", fields: ["reason": "frontend_build_mismatch"])
                stop { [weak self] in self?.desiredStop = false; self?.startOwnedService() }
            } else {
                failConflict("服务 build 与当前 App 不一致，且无法确认服务由本 App 管理")
            }
            return
        }
        setState(.ready)
        ready(with: identity)
        finish(identity)
    }

    private func startOwnedService() {
        guard !desiredStop else { finish(nil); return }
        setState(.starting)
        let child = Process()
        child.executableURL = URL(fileURLWithPath: configuration.wbBinary)
        child.arguments = configuration.serverArguments
        var environment = ProcessInfo.processInfo.environment
        environment["WORK_ROOT"] = configuration.workRoot
        environment["WB_PANEL_MODE"] = configuration.mode.rawValue
        environment["WB_LAUNCH_SESSION"] = UUID().uuidString
        environment["WB_SESSION_TOKEN"] = sessionToken
        if let staticDirectory = configuration.staticDirectory {
            environment["WB_STATIC_DIR"] = staticDirectory
        }
        if let promptsDirectory = configuration.promptsDirectory {
            environment["WB_PROMPTS_DIR"] = promptsDirectory
        }
        child.environment = environment
        let logURL = URL(fileURLWithPath: NSHomeDirectory())
            .appendingPathComponent("Library/Logs/summitworkbench-panel.log")
        try? FileManager.default.createDirectory(at: logURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        if let handle = try? FileHandle(forWritingTo: logURL) {
            handle.seekToEndOfFile()
            child.standardOutput = handle
            child.standardError = handle
        }
        do {
            try child.run()
            process = child
            logger.log("service_spawned", fields: ["pid": String(child.processIdentifier)])
            child.terminationHandler = { [weak self] child in
                DispatchQueue.main.async { self?.serviceExited(child.terminationStatus) }
            }
            waitForReadiness(attempt: 0)
        } catch {
            logger.log("service_exited", level: "error", fields: ["reason": error.localizedDescription])
            registerFailureAndMaybeRetry()
        }
    }

    private func waitForReadiness(attempt: Int) {
        if let record = RuntimeRecord.load(), record.productID == panelProductID,
           record.apiProtocol >= panelAPIProtocol, record.pid == process?.processIdentifier {
            client.update(port: record.port)
        }
        client.probe { [weak self] result in
            guard let self else { return }
            if case .valid(let identity) = result {
                self.identity = identity
                self.logger.log("service_ready", fields: ["server_instance": identity.serverInstance])
                self.setState(.ready)
                self.ready(with: identity)
                self.finish(identity)
                return
            }
            let delays: [Double] = [0, 0.1, 0.25, 0.5, 1, 1, 2, 2, 2, 2, 2]
            guard attempt < delays.count else {
                self.logger.log("service_exited", level: "error", fields: ["reason": "readiness_timeout"])
                self.terminateOwnedProcessBeforeRetry()
                self.registerFailureAndMaybeRetry()
                return
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + delays[attempt]) {
                self.waitForReadiness(attempt: attempt + 1)
            }
        }
    }

    private func serviceExited(_ status: Int32) {
        process = nil
        RuntimeRecord.remove()
        logger.log("service_exited", fields: ["status": String(status)])
        guard !desiredStop else { setState(.stopped); return }
        registerFailureAndMaybeRetry()
    }

    /// A child can remain alive when its readiness record is unreadable or a
    /// compatible response never arrives. Always stop that exact Process
    /// instance before scheduling another one, otherwise retries can leave
    /// orphan servers listening on random ports and collide on runtime.json.
    private func terminateOwnedProcessBeforeRetry() {
        guard let child = process, child.isRunning else {
            process = nil
            return
        }
        child.terminationHandler = nil
        child.terminate()
        process = nil
    }

    private func registerFailureAndMaybeRetry() {
        let now = Date()
        failures = failures.filter { now.timeIntervalSince($0) < 120 }
        failures.append(now)
        if failures.count >= 5 {
            setState(.crashLoop)
            logger.log("service_crash_loop", level: "error", fields: ["failures": String(failures.count)])
            finish(nil)
            return
        }
        let delay = min(pow(2.0, Double(max(0, failures.count - 1))), 30.0)
        setState(.restarting)
        logger.log("service_restart_scheduled", fields: ["delay_seconds": String(delay)])
        restartWork?.cancel()
        let work = DispatchWorkItem { [weak self] in self?.startOwnedService() }
        restartWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + delay, execute: work)
    }

    private func failConflict(_ message: String) {
        logger.log("service_conflict", level: "error", fields: ["message": message])
        setState(.conflict)
        finish(nil)
    }

    private func ready(with identity: ServiceIdentity) {
        // 进行中的 ensureReady 周期会经 completion 汇报 identity（含协调器自身的
        // 恢复流程），避免重复触发；仅后台自发恢复（崩溃重启等）时通知监听者。
        if !ensureInFlight {
            onIdentityChange?(identity)
        }
    }

    private func finish(_ identity: ServiceIdentity?) {
        ensureInFlight = false
        let callbacks = waiters
        waiters.removeAll()
        callbacks.forEach { $0(identity) }
    }

    private func setState(_ next: SupervisorState) {
        state = next
        onStateChange?(next)
    }

    private static func newSessionToken() -> String {
        var bytes = [UInt8](repeating: 0, count: 32)
        _ = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
        return Data(bytes).base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }

    private func processStartDate(_ pid: Int32) -> Date? {
        let ps = Process()
        let pipe = Pipe()
        ps.executableURL = URL(fileURLWithPath: "/bin/ps")
        ps.arguments = ["-p", String(pid), "-o", "lstart="]
        ps.standardOutput = pipe
        ps.standardError = FileHandle.nullDevice
        try? ps.run(); ps.waitUntilExit()
        guard let value = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) else { return nil }
        let formatter = DateFormatter(); formatter.locale = Locale(identifier: "en_US_POSIX"); formatter.dateFormat = "EEE MMM d HH:mm:ss yyyy"
        return formatter.date(from: value)
    }
}
