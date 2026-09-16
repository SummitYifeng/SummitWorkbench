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
    private var launchGeneration = UUID()
    private var stopInFlight = false
    private var stopCompletions: [() -> Void] = []
    private var unfinishedOperationID: String?
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
        if let completion { stopCompletions.append(completion) }
        guard !stopInFlight else { return }
        stopInFlight = true
        desiredStop = true
        restartWork?.cancel()
        let executorID = launchGeneration.uuidString
        launchGeneration = UUID()
        setState(.stopping)
        logger.log("user_quit_requested")
        guard let process else {
            finishStop(processPID: nil)
            return
        }
        guard process.isRunning else {
            finishStop(processPID: process.processIdentifier)
            return
        }
        let processPID = process.processIdentifier
        let operationID = "service-termination-\(processPID)"
        unfinishedOperationID = operationID
        UnfinishedOperationRecord(
            operationID: operationID,
            executorID: executorID,
            kind: "service",
            startedAt: Date()
        ).save()
        BoundedProcessTerminator.stop(
            process,
            owns: { [weak self, weak process] in
                guard let self, let process else { return false }
                return self.ownsCurrentProcess(process)
            }
        ) { [weak self, weak process] in
            DispatchQueue.main.async {
                guard let self else { return }
                if process?.isRunning == false {
                    RuntimeRecord.remove(forPID: processPID)
                } else {
                    self.logger.log("service_shutdown_unconfirmed", level: "error",
                                    fields: ["pid": String(processPID)])
                }
                self.finishStop(processPID: processPID)
            }
        }
    }

    /// Onboarding changes the active workspace while this server is still the
    /// restricted control plane. Restart the owned child so the next process
    /// resolves the new active profile and exposes the full workbench routes.
    func restartForWorkspaceChange(completion: @escaping (ServiceIdentity?) -> Void) {
        desiredStop = true
        restartWork?.cancel()
        stop { [weak self] in
            guard let self else { completion(nil); return }
            self.desiredStop = false
            self.ensureReady(completion: completion)
        }
    }

    /// App 进程终止时的同步收尾：取消重启、终止自管服务并清理 runtime record。
    /// 不做等待（进程即将退出），与用户主动 quit 的异步 stop() 语义区分。
    func shutdownForApplicationTermination() {
        logger.log("service_shutdown_for_termination")
        stop()
    }

    private func ownsCurrentProcess(_ process: Process) -> Bool {
        if let record = RuntimeRecord.load(forPID: process.processIdentifier) {
            return record.owns(process) && record.ownsServer(at: configuration.wbBinary)
        }
        // If the child removed its runtime record during shutdown, the exact
        // Process handle created by this supervisor remains the trusted
        // identity.  Never fall back to PID-only or process-name matching.
        let expected = URL(fileURLWithPath: configuration.wbBinary).standardizedFileURL.path
        let actual = process.executableURL?.standardizedFileURL.path
        return process.isRunning && actual == expected
    }

    private func finishStop(processPID: Int32?) {
        if let processPID, process?.isRunning == false {
            RuntimeRecord.remove(forPID: processPID)
            process = nil
            if let unfinishedOperationID {
                UnfinishedOperationRecord.remove(ifOperationID: unfinishedOperationID)
                self.unfinishedOperationID = nil
            }
        }
        setState(.stopped)
        stopInFlight = false
        let completions = stopCompletions
        stopCompletions.removeAll()
        completions.forEach { $0() }
    }

    private func accept(_ identity: ServiceIdentity) {
        self.identity = identity
        logger.log("service_identity_verified", fields: ["server_instance": identity.serverInstance])
        if configuration.mode == .production && identity.frontendBuild != configuration.manifest.frontendBuild {
            if let process, let record = RuntimeRecord.load(forPID: process.processIdentifier),
               record.serverInstance == identity.serverInstance, record.owns(process) {
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
        if let record = RuntimeRecord.loadOwned(serverExecutable: configuration.wbBinary),
           record.terminateOwnedServer(at: configuration.wbBinary) {
            logger.log("orphan_service_termination", fields: ["pid": String(record.pid)])
            let work = DispatchWorkItem { [weak self] in self?.startOwnedService() }
            restartWork = work
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.25, execute: work)
            return
        }
        setState(.starting)
        let child = Process()
        child.executableURL = URL(fileURLWithPath: configuration.wbBinary)
        child.arguments = configuration.serverArguments
        var environment = ProcessInfo.processInfo.environment
        environment["WORK_ROOT"] = configuration.workRoot
        // 显式对齐 runtime 记录路径。服务端默认从 Path.home()（认 $HOME）推导，而本 App 从
        // NSHomeDirectory()（不认 $HOME）读取；正常启动下两者一致，但一旦 $HOME 与账户家目录
        // 不同（例如从终端以自定义 HOME 启动），服务端写下的记录就永远找不到，App 会一直重试到
        // readiness_timeout。显式传参消除这个隐式假设（服务端 --runtime-record 的默认值即本变量）。
        environment["WB_RUNTIME_RECORD"] = RuntimeRecord.url.path
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
            let generation = UUID()
            launchGeneration = generation
            logger.log("service_spawned", fields: ["pid": String(child.processIdentifier)])
            child.terminationHandler = { [weak self] child in
                DispatchQueue.main.async {
                    self?.serviceExited(child.processIdentifier, status: child.terminationStatus)
                }
            }
            waitForReadiness(attempt: 0, generation: generation)
        } catch {
            logger.log("service_exited", level: "error", fields: ["reason": error.localizedDescription])
            registerFailureAndMaybeRetry()
        }
    }

    private func waitForReadiness(attempt: Int, generation: UUID) {
        guard launchGeneration == generation else { return }
        if let record = RuntimeRecord.load(forPID: process?.processIdentifier ?? -1),
           record.productID == panelProductID, record.apiProtocol >= panelAPIProtocol {
            client.update(port: record.port)
        }
        client.probe { [weak self] result in
            guard let self else { return }
            guard self.launchGeneration == generation else { return }
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
                self.waitForReadiness(attempt: attempt + 1, generation: generation)
            }
        }
    }

    private func serviceExited(_ pid: Int32, status: Int32) {
        guard process?.processIdentifier == pid else { return }
        let exitedPID = process?.processIdentifier ?? -1
        process = nil
        RuntimeRecord.remove(forPID: exitedPID)
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
        RuntimeRecord.remove(forPID: child.processIdentifier)
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

}
